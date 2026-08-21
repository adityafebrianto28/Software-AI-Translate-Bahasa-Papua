# -*- coding: utf-8 -*-
"""
Client jaringan langsung untuk Web-888/KiwiSDR.

Antarmuka kelas sengaja dipertahankan agar kompatibel dengan
app_faster_whisper_lokal.py dan frontend yang sudah ada. Perbaikan utama:
- parsing SND sesuai protokol KiwiSDR (header, endian, dan IMA-ADPCM);
- buffer audio terpisah dan dibatasi agar tidak terus membesar;
- soft-squelch untuk monitor live agar noise berkurang tanpa mematikan audio total;
- sample-rate audio mengikuti pesan server;
- waterfall memakai offset header dan skala byte resmi;
- koneksi lama tidak dapat hidup kembali saat restart cepat.
"""

from __future__ import annotations

from collections import deque
import math
import os
import socket
import struct
import sys
import threading
import time
from typing import Deque, Optional, Tuple

import numpy as np

try:
    import websocket  # pip install websocket-client
except Exception:
    websocket = None


KIWI_SND_STREAM = "SND"
KIWI_WF_STREAM = "W/F"
KIWI_AUDIO_RATE = 12000
KIWI_WF_BINS = 1024
KIWI_WF_MAX_ZOOM = 14

SND_FLAG_ADC_OVFL = 0x02
SND_FLAG_STEREO = 0x08
SND_FLAG_COMPRESSED = 0x10
SND_FLAG_LITTLE_ENDIAN = 0x80


_STEP_SIZE_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34,
    37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494,
    544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552,
    1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)
_INDEX_ADJUST_TABLE = (
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8,
)


class _ImaAdpcmDecoder:
    """Decoder IMA-ADPCM kontinu untuk frame SND terkompresi."""

    def __init__(self):
        self.index = 0
        self.prev = 0

    def preset(self, index: int, prev: int):
        self.index = max(0, min(int(index), len(_STEP_SIZE_TABLE) - 1))
        self.prev = max(-32768, min(int(prev), 32767))

    def _decode_nibble(self, code: int) -> int:
        step = _STEP_SIZE_TABLE[self.index]
        self.index = max(
            0,
            min(self.index + _INDEX_ADJUST_TABLE[code & 0x0F], len(_STEP_SIZE_TABLE) - 1),
        )
        difference = step >> 3
        if code & 1:
            difference += step >> 2
        if code & 2:
            difference += step >> 1
        if code & 4:
            difference += step
        if code & 8:
            difference = -difference
        self.prev = max(-32768, min(self.prev + difference, 32767))
        return self.prev

    def decode(self, data: bytes) -> np.ndarray:
        out = np.empty(len(data) * 2, dtype=np.int16)
        j = 0
        for byte in data:
            out[j] = self._decode_nibble(byte & 0x0F)
            out[j + 1] = self._decode_nibble((byte >> 4) & 0x0F)
            j += 2
        return out


class Web888Client:
    """Satu instance mewakili satu channel RX Web-888/KiwiSDR."""

    _MODE_MAP = {
        "fm": "nbfm",
        "nfm": "nbfm",
        "nbfm": "nbfm",
        "nnfm": "nnfm",
        "wfm": "nbfm",
    }

    def __init__(self):
        self.lock = threading.RLock()

        self.host = "127.0.0.1"
        self.port = 8073
        self.password = ""

        self.running = False
        self.connected_snd = False
        self.connected_wf = False
        self.audio_ready = False
        self.error: Optional[str] = None
        self._generation = 0

        self._ws_snd = None
        self._ws_wf = None
        self._thread_snd: Optional[threading.Thread] = None
        self._thread_wf: Optional[threading.Thread] = None

        self.freq_hz = 100_000_000
        self.mode = "nbfm"
        self.bandwidth_hz = 12500
        self.low_cut = -6000
        self.high_cut = 6000

        self.audio_sample_rate = float(KIWI_AUDIO_RATE)
        self.last_audio_ts = 0.0
        self._first_audio_frame = True
        self._decoder = _ImaAdpcmDecoder()
        self._pcm_endian_config = os.environ.get("WEB888_PCM_ENDIAN", "auto").strip().lower()
        self._selected_pcm_endian: Optional[str] = None
        self.voice_filter_enabled = (
            os.environ.get("WEB888_VOICE_FILTER", "1").strip() != "0"
        )

        self.latest_db: Optional[np.ndarray] = None
        self.latest_ts = 0.0

        self.wf_mindb = -110.0
        self.wf_maxdb = -10.0
        self.wf_cal_db = float(os.environ.get("WEB888_WF_CAL_DB", "0"))
        self.wf_span_hz = int(os.environ.get("WEB888_WF_SPAN_HZ", "40000000"))
        self.wf_max_freq_khz = float(os.environ.get("WEB888_MAX_FREQ_KHZ", "61440"))

        self._audio_chunks: Deque[np.ndarray] = deque()
        self._audio_lock = threading.Lock()
        self._audio_sample_count = 0

        self._monitor_chunks: Deque[np.ndarray] = deque()
        self._monitor_lock = threading.Lock()
        self._monitor_sample_count = 0

        # Buffer rekaman cukup panjang untuk menangkap satu transmisi, sedangkan
        # monitor live dijaga SEPENDEK MUNGKIN supaya latensinya tidak menumpuk.
        # Diperkecil dari 1.5s -> 0.4s: batas ini adalah jumlah MAKSIMUM audio
        # "basi" yang bisa tertahan di buffer server sebelum sampel terlama
        # dibuang -- makin kecil, makin kecil pula potensi delay saat terjadi
        # hambatan sesaat (jaringan/CPU). Konsekuensinya: kalau hambatan lebih
        # panjang dari 0.4s, bagian audio yang hilang akan terdengar sebagai
        # jeda diam sebentar, bukan delay yang menumpuk -- ini disengaja,
        # "gagal ke diam sebentar" jauh lebih baik daripada "gagal ke delay
        # yang terus tertimbun".
        self.audio_buffer_seconds = float(os.environ.get("WEB888_RECORD_BUFFER_SECONDS", "25"))
        self.monitor_buffer_seconds = float(os.environ.get("WEB888_MONITOR_BUFFER_SECONDS", "0.4"))

        self.current_rms = 0.0
        self.squelch_dbm = float(os.environ.get("WEB888_SQUELCH_DBM", "-100.0"))
        self.squelch_hysteresis_db = float(
            os.environ.get("WEB888_SQUELCH_HYSTERESIS_DB", "3.0")
        )
        self.current_smeter_dbm: Optional[float] = None
        self.squelch_open = False

        self.meter_floor_dbm = float(os.environ.get("WEB888_METER_FLOOR_DBM", "-110.0"))
        self.meter_ceil_dbm = float(os.environ.get("WEB888_METER_CEIL_DBM", "-20.0"))

        # Saat squelch tertutup, monitor tidak dimatikan total. Noise dilemahkan
        # kuat agar operator masih dapat men-tune dengan telinga tanpa hiss penuh.
        self.monitor_closed_gain = float(
            os.environ.get("WEB888_MONITOR_CLOSED_GAIN", "0.025")
        )
        self._monitor_gain = self.monitor_closed_gain

        self._server_version_major: Optional[int] = None
        self._server_version_minor: Optional[int] = None

    # ------------------------------------------------------------------
    # Status dan lifecycle
    # ------------------------------------------------------------------
    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "connected": bool(self.connected_snd or self.connected_wf),
                "connected_snd": self.connected_snd,
                "connected_wf": self.connected_wf,
                "audio_ready": self.audio_ready,
                "audio_sample_rate": self.audio_sample_rate,
                "error": self.error,
                "host": self.host,
                "port": self.port,
                "freq_hz": self.freq_hz,
                "mode": self.mode.upper(),
                "bandwidth_hz": self.bandwidth_hz,
                "sample_rate_hz": self.wf_span_hz,
                "squelch_dbm": self.squelch_dbm,
                "smeter_dbm": self.current_smeter_dbm,
                "squelch_open": self.squelch_open,
                "wf_span_hz": self.wf_span_hz,
            }

    @staticmethod
    def probe(host: str, port: int, timeout: float = 2.0) -> bool:
        if websocket is None:
            return False
        ts = int(time.time() * 1000) % 1_000_000
        url = f"ws://{host}:{int(port)}/kiwi/{ts}/{KIWI_WF_STREAM}"
        try:
            ws = websocket.create_connection(url, timeout=timeout)
            ws.close()
            return True
        except Exception:
            return False

    def start(
        self,
        host,
        port,
        password="",
        freq_hz=None,
        mode=None,
        bandwidth_hz=None,
        wf_span_hz=None,
    ):
        if websocket is None:
            raise RuntimeError(
                "Modul 'websocket-client' belum terpasang. "
                "Jalankan: pip install websocket-client"
            )

        # Pastikan thread koneksi sebelumnya benar-benar dimatikan sebelum
        # membuat generasi baru. Ini mencegah dua koneksi SND hidup bersamaan.
        self.stop()

        with self.lock:
            self.host = str(host)
            self.port = int(port)
            self.password = password or ""
            if freq_hz is not None:
                self.freq_hz = int(freq_hz)
            if mode:
                self.mode = self._normalize_mode(mode)
            if bandwidth_hz is not None:
                self._set_bandwidth_locked(int(bandwidth_hz))
            if wf_span_hz is not None:
                try:
                    self.wf_span_hz = max(int(wf_span_hz), 1)
                except (TypeError, ValueError):
                    pass

            self._generation += 1
            generation = self._generation
            self.running = True
            self.connected_snd = False
            self.connected_wf = False
            self.audio_ready = False
            self.error = None
            self._first_audio_frame = True
            self._selected_pcm_endian = None
            self._decoder = _ImaAdpcmDecoder()

        self.clear_audio()
        self.clear_monitor_audio()

        self._thread_snd = threading.Thread(
            target=self._run_snd, args=(generation,), daemon=True, name="web888-snd"
        )
        self._thread_wf = threading.Thread(
            target=self._run_wf, args=(generation,), daemon=True, name="web888-wf"
        )
        self._thread_snd.start()
        self._thread_wf.start()
        print(f"[WEB888] Menyambung ke {self.host}:{self.port} …", file=sys.stderr)

    def stop(self):
        with self.lock:
            self.running = False
            self._generation += 1
            ws_snd, ws_wf = self._ws_snd, self._ws_wf
            snd_thread, wf_thread = self._thread_snd, self._thread_wf
            self._ws_snd = None
            self._ws_wf = None

        for ws in (ws_snd, ws_wf):
            try:
                if ws:
                    ws.close()
            except Exception:
                pass

        current = threading.current_thread()
        for thread in (snd_thread, wf_thread):
            if thread and thread is not current and thread.is_alive():
                thread.join(timeout=1.0)

        with self.lock:
            self.connected_snd = False
            self.connected_wf = False
            self.audio_ready = False
            self._thread_snd = None
            self._thread_wf = None

        self.clear_audio()
        self.clear_monitor_audio()

    def _active(self, generation: int) -> bool:
        with self.lock:
            return self.running and self._generation == generation

    # ------------------------------------------------------------------
    # Pesan server dan setup SND
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_msg_text(data) -> Optional[str]:
        if isinstance(data, str):
            raw = data.encode("utf-8", errors="ignore")
        else:
            raw = bytes(data)
        if raw.startswith(b"MSG"):
            raw = raw[3:]
        if raw and raw[0] < 0x20:
            raw = raw[1:]
        try:
            return raw.decode("utf-8", errors="ignore").strip()
        except Exception:
            return None

    def _handle_msg_frame(self, data, stream: Optional[str] = None):
        text = self._decode_msg_text(data)
        if not text:
            return

        for token in text.split():
            if "=" in token:
                name, value = token.split("=", 1)
            else:
                name, value = token, None

            if name == "audio_rate" and value and stream != "wf":
                try:
                    rate = float(value)
                    if rate > 1000:
                        with self.lock:
                            self.audio_sample_rate = rate
                        self._send_ar_ok(rate)
                except ValueError:
                    pass
            elif name == "sample_rate" and value and stream != "wf":
                try:
                    rate = float(value)
                    if rate > 1000:
                        with self.lock:
                            self.audio_sample_rate = rate
                except ValueError:
                    pass
            elif name == "bandwidth" and value:
                try:
                    max_khz = float(value) / 1000.0
                    if max_khz > 0:
                        with self.lock:
                            self.wf_max_freq_khz = max_khz
                except ValueError:
                    pass
            elif name == "version_maj" and value:
                try:
                    self._server_version_major = int(value)
                except ValueError:
                    pass
            elif name == "version_min" and value:
                try:
                    self._server_version_minor = int(value)
                except ValueError:
                    pass
            elif name == "audio_adpcm_state" and value:
                try:
                    index, prev = value.split(",", 1)
                    self._decoder.preset(int(index), int(prev))
                except Exception:
                    pass
            elif name in {"too_busy", "down", "camp_disconnect"}:
                raise RuntimeError(f"Web-888 menolak koneksi: {name}={value}")
            elif name == "badp" and value not in (None, "0"):
                raise RuntimeError("Password Web-888 salah atau channel sedang penuh.")

    def _send_ar_ok(self, rate: float):
        with self.lock:
            ws = self._ws_snd
        if ws is None:
            return
        rate_i = max(int(round(rate)), 1000)
        try:
            # in=out menjaga sampel server tetap pada rate aslinya. Playback
            # browser dan Whisper memakai metadata rate yang sama.
            ws.send(f"SET AR OK in={rate_i} out={rate_i}")
        except Exception:
            pass

    def _send_snd_setup(self):
        with self.lock:
            ws = self._ws_snd
            rate = self.audio_sample_rate or KIWI_AUDIO_RATE
        if ws is None:
            return

        self._send_ar_ok(rate)
        self._send_tune()
        commands = (
            "SET compression=0",
            "SET squelch=0 max=0",
            "SET agc=1 hang=0 thresh=-100 slope=6 decay=1000 manGain=50",
            "SET genattn=0",
            "SET gen=0 mix=-1",
        )
        for command in commands:
            try:
                ws.send(command)
            except Exception:
                return

    def _run_snd(self, generation: int):
        backoff = 0.25
        while self._active(generation):
            with self.lock:
                host, port, password = self.host, self.port, self.password
            ts = int(time.time() * 1000) % 1_000_000
            url = f"ws://{host}:{port}/kiwi/{ts}/{KIWI_SND_STREAM}"
            ws = None
            try:
                ws = websocket.create_connection(url, timeout=5.0)
                ws.settimeout(1.0)
                if not self._active(generation):
                    ws.close()
                    return

                with self.lock:
                    self._ws_snd = ws
                    self.connected_snd = True
                    self.audio_ready = False
                    self.error = None

                ws.send(f"SET auth t=kiwi p={password}")
                self._send_snd_setup()
                print(f"[WEB888/SND] Tersambung ke {host}:{port}.", file=sys.stderr)

                backoff = 0.25
                last_keepalive = 0.0
                while self._active(generation):
                    now = time.time()
                    if now - last_keepalive >= 1.0:
                        try:
                            ws.send("SET keepalive")
                        except Exception:
                            break
                        last_keepalive = now
                    try:
                        opcode, payload = ws.recv_data()
                    except Exception as exc:
                        timeout_types = tuple(
                            t
                            for t in (
                                getattr(websocket, "WebSocketTimeoutException", None),
                                socket.timeout,
                            )
                            if isinstance(t, type)
                        )
                        if timeout_types and isinstance(exc, timeout_types):
                            continue
                        raise

                    if opcode == websocket.ABNF.OPCODE_BINARY:
                        if bytes(payload).startswith(b"SND"):
                            self._handle_snd_frame(bytes(payload))
                        elif bytes(payload).startswith(b"MSG"):
                            self._handle_msg_frame(payload, stream="snd")
                    elif opcode == websocket.ABNF.OPCODE_TEXT:
                        self._handle_msg_frame(payload, stream="snd")

            except Exception as exc:
                if self._active(generation):
                    with self.lock:
                        self.error = str(exc)
                    print(f"[WEB888/SND ERROR] {exc}", file=sys.stderr)
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 5.0)
            finally:
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
                with self.lock:
                    if self._generation == generation:
                        self.connected_snd = False
                        self.audio_ready = False
                        if self._ws_snd is ws:
                            self._ws_snd = None

    # ------------------------------------------------------------------
    # Tuning
    # ------------------------------------------------------------------
    @classmethod
    def _normalize_mode(cls, mode) -> str:
        value = str(mode or "nbfm").strip().lower()
        return cls._MODE_MAP.get(value, value)

    def _set_bandwidth_locked(self, bandwidth_hz: int):
        self.bandwidth_hz = max(int(bandwidth_hz), 200)
        half = max(self.bandwidth_hz // 2, 100)
        self.low_cut, self.high_cut = -half, half

    def _send_tune(self):
        with self.lock:
            ws = self._ws_snd
            if ws is None:
                return
            freq_khz = self.freq_hz / 1000.0
            mode, low, high = self.mode, self.low_cut, self.high_cut
        try:
            ws.send(
                f"SET mod={mode} low_cut={int(low)} "
                f"high_cut={int(high)} freq={freq_khz:.3f}"
            )
        except Exception as exc:
            print(f"[WEB888] Gagal kirim tuning: {exc}", file=sys.stderr)

    def set_frequency(self, hz):
        with self.lock:
            self.freq_hz = int(hz)
        # Buang audio lama agar transmisi pada frekuensi sebelumnya tidak
        # ikut terbaca sebagai ucapan baru.
        self.clear_audio()
        self._send_tune()
        self._send_wf_tune()

    def set_mode(self, mode, bandwidth_hz):
        with self.lock:
            self.mode = self._normalize_mode(mode)
            self._set_bandwidth_locked(int(bandwidth_hz))
        self.clear_audio()
        self._send_tune()

    def set_wf_span_hz(self, span_hz):
        """Ubah lebar rentang (span) waterfall secara LIVE.

        Ini beda dengan "zoom" di frontend yang lama (yang cuma memotong
        array 1024 bin yang sudah diterima lalu direntangkan ke lebar
        kotak -- jumlah data mentahnya tetap sama, jadi makin di-zoom
        makin blocky/kasar). Di sini kita betul-betul minta ULANG ke
        server KiwiSDR/Web-888 supaya 1024 bin barunya dihitung untuk
        span yang lebih sempit (lihat _send_wf_tune/_pick_zoom_for_span
        di atas) -- hasilnya resolusi Hz-per-bin ASLI naik, bukan cuma
        piksel yang di-stretch.
        """
        with self.lock:
            try:
                self.wf_span_hz = max(int(span_hz), 1000)
            except (TypeError, ValueError):
                return
        self._send_wf_tune()

    def set_squelch(self, squelch_dbm: float):
        with self.lock:
            self.squelch_dbm = float(squelch_dbm)

    # ------------------------------------------------------------------
    # Buffer audio
    # ------------------------------------------------------------------
    @staticmethod
    def _roughness(samples: np.ndarray) -> float:
        if samples.size < 2:
            return float("inf")
        x = samples.astype(np.float32, copy=False)
        rms = float(np.sqrt(np.mean(x * x))) + 1.0
        return float(np.mean(np.abs(np.diff(x)))) / rms

    def _decode_pcm(self, payload: bytes, flags: int) -> np.ndarray:
        if flags & SND_FLAG_COMPRESSED:
            return self._decoder.decode(payload).astype(np.float32) / 32768.0

        config = self._pcm_endian_config
        if config in {"little", "le", "<"}:
            endian = "<"
        elif config in {"big", "be", ">"}:
            endian = ">"
        elif flags & SND_FLAG_LITTLE_ENDIAN:
            endian = "<"
        elif self._selected_pcm_endian:
            endian = self._selected_pcm_endian
        else:
            # Protokol KiwiSDR normal memakai big-endian. Beberapa firmware
            # turunan pernah mengirim little-endian tanpa flag; pilih kandidat
            # yang lebih halus pada frame pertama lalu kunci hasilnya.
            be = np.frombuffer(payload, dtype=">i2")
            le = np.frombuffer(payload, dtype="<i2")
            endian = ">" if self._roughness(be) <= self._roughness(le) else "<"
            self._selected_pcm_endian = endian

        return np.frombuffer(payload, dtype=f"{endian}i2").astype(np.float32) / 32768.0

    def _voice_band_limit(self, samples: np.ndarray) -> np.ndarray:
        """Band-limit ringan 250–3600 Hz untuk menekan hiss FM pada monitor."""
        if not self.voice_filter_enabled or samples.size < 32:
            return samples.astype(np.float32, copy=False)

        sr = float(self.get_audio_sample_rate())
        nyq = sr * 0.5
        high_stop = min(4200.0, nyq * 0.96)
        high_pass = min(3400.0, high_stop)
        if high_stop <= 400.0:
            return samples.astype(np.float32, copy=False)

        spectrum = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(samples.size, d=1.0 / sr)
        weights = np.ones(freqs.shape, dtype=np.float32)

        # Smooth transition agar tidak menimbulkan ringing/klik antar-frame.
        weights[freqs <= 140.0] = 0.0
        low_transition = (freqs > 140.0) & (freqs < 280.0)
        weights[low_transition] = (
            (freqs[low_transition] - 140.0) / (280.0 - 140.0)
        ).astype(np.float32)

        weights[freqs >= high_stop] = 0.0
        high_transition = (freqs > high_pass) & (freqs < high_stop)
        if high_stop > high_pass:
            weights[high_transition] = (
                (high_stop - freqs[high_transition]) / (high_stop - high_pass)
            ).astype(np.float32)

        filtered = np.fft.irfft(spectrum * weights, n=samples.size)
        return filtered.astype(np.float32, copy=False)

    def _push_bounded_audio(self, samples: np.ndarray):
        max_samples = max(int(self.audio_sample_rate * self.audio_buffer_seconds), 1)
        with self._audio_lock:
            self._audio_chunks.append(samples)
            self._audio_sample_count += int(samples.size)
            while self._audio_sample_count > max_samples and self._audio_chunks:
                old = self._audio_chunks.popleft()
                self._audio_sample_count -= int(old.size)

    def _push_bounded_monitor(self, samples: np.ndarray):
        max_samples = max(int(self.audio_sample_rate * self.monitor_buffer_seconds), 1)
        with self._monitor_lock:
            self._monitor_chunks.append(samples)
            self._monitor_sample_count += int(samples.size)
            while self._monitor_sample_count > max_samples and self._monitor_chunks:
                old = self._monitor_chunks.popleft()
                self._monitor_sample_count -= int(old.size)

    @staticmethod
    def _drain(
        chunks: Deque[np.ndarray],
        sample_count_name: str,
        owner,
        max_samples: Optional[int] = None,
    ) -> np.ndarray:
        if not chunks:
            return np.array([], dtype=np.float32)

        arrays = []
        taken = 0
        limit = None if max_samples is None else max(int(max_samples), 1)
        while chunks and (limit is None or taken < limit):
            arr = chunks.popleft()
            if limit is not None and taken + arr.size > limit:
                cut = limit - taken
                if cut > 0:
                    arrays.append(arr[:cut])
                    chunks.appendleft(arr[cut:])
                    taken += cut
                break
            arrays.append(arr)
            taken += int(arr.size)

        setattr(owner, sample_count_name, max(getattr(owner, sample_count_name) - taken, 0))
        if not arrays:
            return np.array([], dtype=np.float32)
        return np.concatenate(arrays).astype(np.float32, copy=False)

    def clear_audio(self):
        with self._audio_lock:
            self._audio_chunks.clear()
            self._audio_sample_count = 0

    def clear_monitor_audio(self):
        with self._monitor_lock:
            self._monitor_chunks.clear()
            self._monitor_sample_count = 0

    def pop_audio(self, max_samples: Optional[int] = None) -> np.ndarray:
        with self._audio_lock:
            return self._drain(
                self._audio_chunks, "_audio_sample_count", self, max_samples=max_samples
            )

    def pop_monitor_audio(self, max_samples: Optional[int] = None) -> np.ndarray:
        with self._monitor_lock:
            return self._drain(
                self._monitor_chunks,
                "_monitor_sample_count",
                self,
                max_samples=max_samples,
            )

    def is_squelch_open(self) -> bool:
        with self._audio_lock:
            return bool(self.squelch_open)

    def get_audio_sample_rate(self) -> int:
        with self.lock:
            return max(int(round(self.audio_sample_rate)), 1000)

    def _handle_snd_frame(self, data: bytes):
        # total header: "SND"(3) + flags(1) + seq LE(4) + S-meter BE(2)
        if len(data) < 12 or data[0:3] != b"SND":
            return

        flags = data[3]
        try:
            smeter_raw = struct.unpack(">H", data[8:10])[0]
            smeter_dbm = (smeter_raw / 10.0) - 127.0
            payload = data[10:]
            if not payload:
                return
            samples = self._decode_pcm(payload, flags)
        except Exception as exc:
            with self.lock:
                self.error = f"Gagal decode audio Web-888: {exc}"
            return

        if flags & SND_FLAG_STEREO:
            # Untuk mode stereo/IQ, ambil rata-rata pasangan agar endpoint tetap
            # menghasilkan audio mono yang aman untuk Whisper.
            if samples.size >= 2:
                samples = samples[: samples.size - (samples.size % 2)]
                samples = samples.reshape(-1, 2).mean(axis=1)

        if samples.size == 0 or not np.all(np.isfinite(samples)):
            return

        # Frame pertama dapat berisi sisa buffer channel pengguna sebelumnya.
        if self._first_audio_frame:
            self._first_audio_frame = False
            with self._audio_lock:
                self.current_smeter_dbm = smeter_dbm
            return

        samples = np.clip(samples, -1.0, 1.0).astype(np.float32, copy=False)
        samples = samples - float(np.mean(samples))
        samples = self._voice_band_limit(samples)
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0

        with self.lock:
            threshold = self.squelch_dbm
            hysteresis = max(self.squelch_hysteresis_db, 0.0)

        with self._audio_lock:
            was_open = bool(self.squelch_open)
            close_threshold = threshold - hysteresis
            squelch_open = (
                smeter_dbm >= close_threshold if was_open else smeter_dbm >= threshold
            )
            self.current_smeter_dbm = smeter_dbm
            self.squelch_open = squelch_open
            self.current_rms = rms if squelch_open else 0.0

        if squelch_open:
            self._push_bounded_audio(samples)
            self.last_audio_ts = time.time()

        # Soft-squelch monitor dengan gain yang bergerak halus untuk mencegah klik.
        target_gain = 1.0 if squelch_open else max(
            0.0, min(self.monitor_closed_gain, 1.0)
        )
        smoothing = 0.45 if target_gain > self._monitor_gain else 0.18
        self._monitor_gain += (target_gain - self._monitor_gain) * smoothing
        monitor = (samples * self._monitor_gain).astype(np.float32, copy=False)
        self._push_bounded_monitor(monitor)

        with self.lock:
            self.audio_ready = True

    def get_meter_level(self) -> Tuple[float, float, Optional[float], bool]:
        with self._audio_lock:
            smeter_dbm = self.current_smeter_dbm
            squelch_open = bool(self.squelch_open)
        with self.lock:
            squelch_dbm = self.squelch_dbm
            floor_dbm = self.meter_floor_dbm
            ceil_dbm = self.meter_ceil_dbm

        span = max(ceil_dbm - floor_dbm, 1e-6)
        threshold_level = max(0.0, min(1.0, (squelch_dbm - floor_dbm) / span))
        if smeter_dbm is None:
            return 0.0, threshold_level, None, squelch_open
        level = max(0.0, min(1.0, (smeter_dbm - floor_dbm) / span))
        return level, threshold_level, smeter_dbm, squelch_open

    # ------------------------------------------------------------------
    # Waterfall
    # ------------------------------------------------------------------
    def _zoom_to_span_khz(self, zoom: int) -> float:
        return self.wf_max_freq_khz / (2**zoom)

    def _pick_zoom_for_span(self, desired_span_hz: float) -> int:
        desired_khz = max(float(desired_span_hz) / 1000.0, 1e-6)
        if self.wf_max_freq_khz <= 0:
            return 0
        zoom = int(round(math.log2(self.wf_max_freq_khz / desired_khz)))
        return max(0, min(KIWI_WF_MAX_ZOOM, zoom))

    def _start_counter(self, start_freq_khz: float, zoom: int) -> int:
        del zoom  # rumus counter lama tidak membutuhkan zoom secara eksplisit
        start_freq_khz = max(float(start_freq_khz), 0.0)
        if self.wf_max_freq_khz <= 0:
            return 0
        return int(
            round(
                start_freq_khz
                / self.wf_max_freq_khz
                * (2**KIWI_WF_MAX_ZOOM)
                * KIWI_WF_BINS
            )
        )

    def _send_wf_tune(self):
        with self.lock:
            ws = self._ws_wf
            if ws is None:
                return
            freq_khz = self.freq_hz / 1000.0
            zoom = self._pick_zoom_for_span(self.wf_span_hz)
            span_khz = self._zoom_to_span_khz(zoom)
            start_freq_khz = max(freq_khz - span_khz / 2.0, 0.0)
            counter = self._start_counter(start_freq_khz, zoom)

        try:
            # Format lama tetap dikirim untuk firmware turunan yang belum
            # mendukung cf=. Format modern dikirim terakhir dan menjadi sumber
            # kebenaran pada KiwiSDR/Web-888 baru.
            ws.send(f"SET zoom={zoom} start={counter}")
            ws.send(f"SET zoom={zoom} cf={freq_khz:.3f}")
            with self.lock:
                self.wf_span_hz = span_khz * 1000.0
        except Exception as exc:
            print(f"[WEB888] Gagal kirim zoom waterfall: {exc}", file=sys.stderr)

    def _run_wf(self, generation: int):
        backoff = 0.25
        while self._active(generation):
            with self.lock:
                host, port, password = self.host, self.port, self.password
            ts = int(time.time() * 1000) % 1_000_000
            url = f"ws://{host}:{port}/kiwi/{ts}/{KIWI_WF_STREAM}"
            ws = None
            try:
                ws = websocket.create_connection(url, timeout=5.0)
                ws.settimeout(1.0)
                if not self._active(generation):
                    ws.close()
                    return

                with self.lock:
                    self._ws_wf = ws
                    self.connected_wf = True
                    self.error = None

                ws.send(f"SET auth t=kiwi p={password}")
                self._send_wf_tune()
                ws.send(f"SET maxdb={self.wf_maxdb:.0f} mindb={self.wf_mindb:.0f}")
                ws.send("SET wf_speed=4")
                ws.send("SET wf_comp=0")
                ws.send("SET interp=13")
                print(f"[WEB888/W-F] Tersambung ke {host}:{port}.", file=sys.stderr)

                backoff = 0.25
                last_keepalive = 0.0
                while self._active(generation):
                    now = time.time()
                    if now - last_keepalive >= 1.0:
                        try:
                            ws.send("SET keepalive")
                        except Exception:
                            break
                        last_keepalive = now
                    try:
                        opcode, payload = ws.recv_data()
                    except Exception as exc:
                        timeout_types = tuple(
                            t
                            for t in (
                                getattr(websocket, "WebSocketTimeoutException", None),
                                socket.timeout,
                            )
                            if isinstance(t, type)
                        )
                        if timeout_types and isinstance(exc, timeout_types):
                            continue
                        raise

                    if opcode == websocket.ABNF.OPCODE_BINARY:
                        raw = bytes(payload)
                        if raw.startswith(b"W/F"):
                            self._handle_wf_frame(raw)
                        elif raw.startswith(b"MSG"):
                            self._handle_msg_frame(raw, stream="wf")
                    elif opcode == websocket.ABNF.OPCODE_TEXT:
                        self._handle_msg_frame(payload, stream="wf")

            except Exception as exc:
                if self._active(generation):
                    with self.lock:
                        self.error = str(exc)
                    print(f"[WEB888/W-F ERROR] {exc}", file=sys.stderr)
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 5.0)
            finally:
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
                with self.lock:
                    if self._generation == generation:
                        self.connected_wf = False
                        if self._ws_wf is ws:
                            self._ws_wf = None

    def _handle_wf_frame(self, data: bytes):
        # Total header protokol:
        # "W/F"(3) + byte reserved(1) + x_bin(4) + flags/zoom(4) + seq(4).
        if len(data) <= 16 or data[0:3] != b"W/F":
            return
        try:
            bins = data[16:]
            raw = np.frombuffer(bins, dtype=np.uint8).astype(np.float32)
            # Skala resmi: byte 55..255 mewakili sekitar -200..0 dBm.
            db = raw - 255.0 + self.wf_cal_db
        except Exception:
            return
        with self.lock:
            self.latest_db = db
            self.latest_ts = time.time()

    def get_latest(self):
        with self.lock:
            if self.latest_db is None:
                return None
            return {
                "db": self.latest_db.tolist(),
                "timestamp": self.latest_ts,
                "sample_rate_hz": self.wf_span_hz,
                "fft_size": int(self.latest_db.size),
                "center_freq_hz": self.freq_hz,
            }