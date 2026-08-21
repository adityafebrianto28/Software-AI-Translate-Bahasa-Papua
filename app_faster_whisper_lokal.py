#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ==========================================================
#  BOOTSTRAP: jalan di .venv dan install deps (sekali saja)
# ==========================================================
import os, sys, subprocess, venv, pathlib, gc
# Wajib sebelum import torch: membantu mengurangi fragmentasi VRAM CUDA
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Mode hemat VRAM untuk GPU kecil (4 GB): hanya 1 model besar aktif di GPU dalam satu waktu
LOW_VRAM_MODE = os.environ.get("YALI_LOW_VRAM_MODE", "1") == "1"
USE_FP16_CUDA = os.environ.get("YALI_USE_FP16_CUDA", "1") == "1"


BASE = pathlib.Path(__file__).resolve().parent
VENV = BASE / ".venv"

# RADIO dan UPLOAD pakai model CTranslate2
DEFAULT_WHISPER_MODEL_RADIO  = str(BASE / "whisper-ambai-v2-10epochs-faster-whisper")
DEFAULT_WHISPER_MODEL_UPLOAD = str(BASE / "whisper-ambai-v2-10epochs-faster-whisper")

DEFAULT_YALI_ID_MODEL = str(BASE / "best_bleu_ambai")

# ==========================================================
#  MULTI-BAHASA PAPUA: Ambai & Biak
# ==========================================================
# Dipilih user lewat dropdown "Pilih Bahasa Papua" (tab Auto Translate).
# Setiap bahasa punya folder model Whisper (faster-whisper/CTranslate2)
# dan folder model MT (best_bleu) masing-masing sendiri.
PAPUA_LANG_DEFAULT = "ambai"

WHISPER_MODEL_DIRS = {
    "ambai": str(BASE / "whisper-ambai-v2-10epochs-faster-whisper"),
    "biak":  str(BASE / "whisper-biak-v2-10epochs-faster-whisper"),
}

MT_MODEL_DIRS = {
    "ambai": str(BASE / "best_bleu_ambai"),
    "biak":  str(BASE / "best_bleu_biak"),
}

# ==========================================================
#  Kode bahasa mBART-50 untuk MT (perbaikan akurasi terjemahan)
# ==========================================================
# Base model MT (lihat adapter_config.json) adalah
# facebook/mbart-large-50-many-to-many-mmt -- model MULTIBAHASA yang WAJIB
# diberi tahu secara eksplisit bahasa sumber & bahasa target lewat
# tokenizer.src_lang dan forced_bos_token_id saat generate(). Kalau tidak,
# model bisa memilih bahasa keluaran yang salah / campur aduk, walaupun
# adapter LoRA-nya sudah benar.
#
# Karena Ambai/Biak bukan bahasa bawaan mBART-50, saat fine-tuning biasanya
# salah satu slot kode bahasa yang sudah ada "dipinjam" untuk mewakili
# bahasa Papua tsb (atau ditambahkan token baru ke tokenizer -- cek
# tokenizer_config.json / special_tokens_map.json di folder checkpoint
# untuk memastikan). NILAI DI BAWAH INI HARUS DISESUAIKAN dengan kode yang
# benar-benar dipakai saat training; "id_ID" hanya nilai default yang masuk
# akal (Indonesia = bahasa terdekat yang didukung mBART-50).
MT_SRC_LANG_CODE = {
    "ambai": "id_ID",  # TODO: sesuaikan dengan kode training asli kalau beda
    "biak":  "id_ID",  # TODO: sesuaikan dengan kode training asli kalau beda
}
MT_TGT_LANG_CODE = "id_ID"  # keluaran MT selalu bahasa Indonesia

# num_beams=1 (greedy) sebelumnya dipakai demi hemat VRAM, tapi kualitas
# beam search jauh lebih baik. Turunkan ke 1 lagi kalau VRAM benar-benar
# mepet (GPU kecil / sering OOM).
MT_NUM_BEAMS = 4
IN_VENV = (hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix) or bool(
    os.environ.get("VIRTUAL_ENV")
)


def _pip_install(args):
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + args)


def _has_nvidia_gpu() -> bool:
    """Deteksi kasar: apakah 'nvidia-smi' ada & bisa dijalankan (artinya driver NVIDIA terpasang)."""
    import shutil
    if not shutil.which("nvidia-smi"):
        return False
    try:
        subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _ensure_venv_and_reexec():
    """
    Jalankan aplikasi di .venv dan pasang HANYA dependency yang belum ada.

    Versi lama menandai YALI_BOOTSTRAPPED sebelum re-exec, lalu langsung
    keluar ketika Python .venv mulai. Pada instalasi baru dependency justru
    belum pernah dipasang. Pemeriksaan modul di bawah membuat bootstrap
    idempotent dan tetap cepat pada start berikutnya.
    """
    if not IN_VENV:
        if not (VENV / "Scripts/python.exe").exists() and not (VENV / "bin/python").exists():
            venv.create(str(VENV), with_pip=True)
        os.environ["YALI_BOOTSTRAPPED"] = "1"
        pyvenv = str(VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        os.execv(pyvenv, [pyvenv, __file__])

    import importlib.util

    module_packages = {
        "sounddevice": "sounddevice",
        "soundfile": "soundfile",
        "numpy": "numpy",
        "gtts": "gTTS",
        "pydub": "pydub",
        "tqdm": "tqdm",
        "scipy": "scipy",
        "transformers": "transformers",
        "requests": "requests",
        "flask": "flask",
        "faster_whisper": "faster-whisper",
        "ctranslate2": "ctranslate2",
        "websocket": "websocket-client",
        "noisereduce": "noisereduce",
        "peft": "peft",
        "sentencepiece": "sentencepiece",
    }
    missing = [
        package
        for module, package in module_packages.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        print(f"[BOOTSTRAP] Memasang dependency yang belum ada: {', '.join(missing)}", file=sys.stderr)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
        )
        _pip_install(missing)

    if importlib.util.find_spec("torch") is None:
        if _has_nvidia_gpu():
            print("[BOOTSTRAP] GPU NVIDIA terdeteksi, memasang torch CUDA (cu121)…", file=sys.stderr)
            _pip_install(
                [
                    "--index-url",
                    "https://download.pytorch.org/whl/cu121",
                    "torch",
                    "torchvision",
                    "torchaudio",
                ]
            )
        else:
            print("[BOOTSTRAP] Tidak ada GPU NVIDIA, memasang torch CPU…", file=sys.stderr)
            _pip_install(
                [
                    "--index-url",
                    "https://download.pytorch.org/whl/cpu",
                    "torch",
                    "torchvision",
                    "torchaudio",
                ]
            )


_ensure_venv_and_reexec()

# ======================
# IMPORTS UTAMA & KONST
# ======================
import io
import re
import base64
import hashlib
import socket
import struct
import threading
import time
import traceback
from collections import deque
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np
import sounddevice as sd
import soundfile as sf  # opsional untuk debug

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_file,
)

from gtts import gTTS
from gtts.tts import gTTSError
from pydub import AudioSegment
from pydub.silence import split_on_silence

from web888_client import Web888Client, KIWI_AUDIO_RATE

TARGET_SR = 16000
# ==========================================================
#  MT (translate): ukuran potongan teks per panggilan model
# ==========================================================
# CATATAN PENTING (perbaikan akurasi terjemahan):
# Sebelumnya nilai ini 10 kata dengan overlap 2 kata. Itu memaksa model
# menerjemahkan potongan kalimat yang sangat pendek TANPA konteks kalimat
# penuh, dan kata yang overlap ikut diterjemahkan dua kali lalu hasilnya
# digabung mentah-mentah dengan spasi -- menghasilkan output yang
# terpotong/duplikat/tidak nyambung.
#
# Sekarang: satu segmen (hasil split per titik) HANYA dipotong lagi kalau
# memang sangat panjang (>CHUNK_MAX_WORDS kata), dan potongannya TIDAK
# overlap lagi (CHUNK_OVERLAP = 0) supaya tidak ada kata yang diterjemahkan
# dua kali. Untuk kalimat normal, ini berarti seluruh kalimat diterjemahkan
# sekaligus dalam satu forward pass -- model dapat konteks penuh.
CHUNK_MAX_WORDS = 80
CHUNK_OVERLAP = 0
RMS_THRESHOLD = 2e-5     # ambang VOX radio SDR#
RADIO_SAMPLE_RATE = 44100
RADIO_BLOCKSIZE = 1024

# Gain tambahan setelah cleaning. Default 1.0 karena pipeline sudah melakukan
# normalisasi; gain 5x hanya memperbesar noise/kliping tanpa meningkatkan SNR.
GAIN_LINEAR = float(os.environ.get("YALI_AUDIO_GAIN", "1.0"))

# VOX dibuat stabil untuk trigger MULAI rekam: simpan sedikit audio sebelum
# trigger supaya huruf/kata pertama tidak terpotong.
VOX_PRE_ROLL_SECONDS = float(os.environ.get("YALI_VOX_PRE_ROLL_SECONDS", "0.35"))
VOX_TRIGGER_SECONDS = float(os.environ.get("YALI_VOX_TRIGGER_SECONDS", "0.08"))
# PERBAIKAN: VOX_RELEASE_SECONDS TIDAK LAGI menghentikan seluruh SESI rekam
# saat PTT dilepas -- "Rekam & Translate Audio" / "Rekam & Simpan Audio"
# sekarang bisa menangkap BANYAK ucapan (banyak siklus tekan-lepas PTT)
# dalam satu sesi, dan sesi itu sendiri hanya berhenti lewat stop manual di
# web (lihat cancel_event & endpoint /record-radio/stop). Nilai ini dipakai
# sebagai debounce untuk menutup SATU ucapan/segmen ketika rilis PTT
# terkonfirmasi, lalu backend otomatis kembali menunggu ucapan berikutnya --
# lihat record_radio_rms()/record_radio_web888(). Tiap segmen ditranskrip
# Whisper terpisah lalu digabung dengan tanda titik, sehingga PTT "aku"
# [lepas] PTT "kamu" [lepas] menjadi "Aku. Kamu." bukan "aku kamu"/"aku,
# kamu" yang ambigu. VOX_MIN_RECORD_SECONDS tidak dipakai, dibiarkan
# terdefinisi untuk kompatibilitas env var lama.
VOX_RELEASE_SECONDS = float(os.environ.get("YALI_VOX_RELEASE_SECONDS", "0.65"))
VOX_MIN_RECORD_SECONDS = float(os.environ.get("YALI_VOX_MIN_RECORD_SECONDS", "0.25"))

# ==========================================================
# REKAM RADIO: batas durasi & folder simpan lokal
# ==========================================================
# RECORD_MAX_SECONDS adalah batas aman untuk SATU ucapan/segmen (satu siklus
# tekan-lepas PTT) -- kalau operator menekan PTT tanpa dilepas sama sekali
# selama durasi ini, ucapan tersebut ditutup paksa jadi satu segmen supaya
# tidak menggantung selamanya. Sesi rekam secara keseluruhan TIDAK dibatasi
# durasi ini -- sesi bisa berisi banyak ucapan/segmen berturut-turut dan
# hanya berhenti lewat stop manual di web atau jeda tanpa PTT baru
# (LISTEN_MAX_SECONDS, lihat di bawah). Bisa diubah lewat env var
# YALI_RECORD_MAX_SECONDS tanpa mengubah kode.
RECORD_MAX_SECONDS = float(os.environ.get("YALI_RECORD_MAX_SECONDS", "30.0"))

# Batas "menunggu sinyal PTT" per panggilan /record-radio -- dipakai baik
# untuk menunggu ucapan PERTAMA maupun jeda menunggu ucapan BERIKUTNYA di
# antara dua PTT dalam satu sesi. Ini watchdog supaya request tidak
# memblokir Flask selamanya kalau user lupa menekan stop manual padahal
# sudah tidak ada PTT baru sama sekali. Tidak membatasi durasi satu ucapan
# (lihat RECORD_MAX_SECONDS di atas).
LISTEN_MAX_SECONDS = float(os.environ.get("YALI_LISTEN_MAX_SECONDS", "300.0"))

# Folder lokal tempat menyimpan file WAV hasil rekaman radio (dibuat kalau
# belum ada). Setiap siklus VOX yang berhasil menangkap suara akan disimpan
# di sini dengan nama file berisi timestamp, TERPISAH dari file sementara
# "last_audio.wav" (yang cuma untuk tombol Putar Audio Papua di UI).
RECORDINGS_DIR = BASE / "rekaman_radio"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# PERBAIKAN: penamaan file rekaman radio mengikuti format yang diminta:
# "radio_<tanggal>_<waktu>_ambai_<urutan>.wav" (mis.
# radio_20260728_110947_ambai_1.wav), bukan lagi "radioambai<urutan>_<tanggal>_<waktu>.wav".
# Nomor urut dihitung dari file "radio_*_<lang>_*" yang SUDAH ADA di
# RECORDINGS_DIR (jadi tetap berlanjut walau server di-restart), lalu
# dinaikkan 1 setiap rekaman baru berhasil disimpan. Aman dipakai bersamaan
# karena /record-radio sudah dilindungi pipeline.record_lock (hanya satu
# siklus rekam yang boleh berjalan dalam satu waktu).
# PERBAIKAN (multi-bahasa Papua): sebelumnya potongan "_ambai_" di nama file
# SELALU ditulis apa adanya, walau bahasa Papua yang sedang aktif adalah
# "biak" -- jadi rekaman bahasa Biak pun ikut tersimpan dengan nama
# "..._ambai_...". Sekarang segmen bahasa di nama file mengikuti
# pipeline.current_lang: "ambai" tetap "..._ambai_...", sedangkan "biak"
# menjadi "..._biak_..." (format & urutan lainnya tidak berubah). Nomor
# urut juga dihitung TERPISAH per bahasa, supaya urutan Ambai dan Biak
# tidak saling mendahului satu sama lain.
def _recording_seq_pattern(lang: str) -> re.Pattern:
    return re.compile(r"^radio_\d{8}_\d{6}_" + re.escape(lang) + r"_(\d+)\.wav$")

def _next_recording_seq(lang: str = "ambai") -> int:
    lang = (lang or "ambai").strip().lower()
    pattern = _recording_seq_pattern(lang)
    max_seq = 0
    for p in RECORDINGS_DIR.glob(f"radio_*_{lang}_*.wav"):
        m = pattern.match(p.name)
        if m:
            try:
                max_seq = max(max_seq, int(m.group(1)))
            except ValueError:
                pass
    return max_seq + 1

def pre_emphasis(signal, alpha=0.97):
    return np.append(signal[0], signal[1:] - alpha * signal[:-1])

def spectral_denoise(data: np.ndarray, sr: int) -> np.ndarray:
    """
    Reduksi noise dengan profil dari bagian TERHENING, bukan selalu 0,5 detik
    pertama. Saat PTT sudah ditekan di awal rekaman, potongan pertama berisi
    suara; memakai suara itu sebagai noise profile dapat menghapus ucapan.
    """
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if data.size < max(int(sr * 0.12), 32):
        return data

    try:
        import noisereduce as nr

        frame_len = max(int(sr * 0.10), 32)
        usable = (data.size // frame_len) * frame_len
        if usable >= frame_len:
            frames = data[:usable].reshape(-1, frame_len)
            rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
            quiet_count = max(1, min(len(frames), int(round(0.5 / 0.10))))
            quiet_idx = np.argsort(rms)[:quiet_count]
            noise_sample = frames[np.sort(quiet_idx)].reshape(-1)
        else:
            noise_sample = data[: min(data.size, int(0.35 * sr))]

        reduced = nr.reduce_noise(
            y=data,
            sr=sr,
            y_noise=noise_sample,
            stationary=True,
            prop_decrease=0.78,
        )
        reduced = np.nan_to_num(reduced, nan=0.0, posinf=0.0, neginf=0.0)
        return reduced.astype(np.float32, copy=False)
    except Exception as exc:
        print(f"[DENOISE] fallback tanpa noisereduce: {exc}", file=sys.stderr)
        return data.astype(np.float32, copy=False)

def remove_quotes(text: str) -> str:
    if not text:
        return text
    QUOTES = ['"', "'", "“", "”", "‘", "’", "«", "»", "`"]
    for q in QUOTES:
        text = text.replace(q, "")
    return text


# PERBAIKAN: satu sesi "Rekam & Translate Audio" / "Rekam & Simpan Audio"
# sekarang bisa berisi BEBERAPA ucapan (satu ucapan = satu siklus
# tekan-lepas PTT), lihat record_radio_rms()/record_radio_web888(). Dua
# helper di bawah ini dipakai di /record-radio untuk menggabungkan hasil
# per-ucapan itu dengan benar:
#   - join_segment_texts(): gabung TEKS hasil Whisper per ucapan dengan
#     tanda titik yang PASTI ada di setiap batas ucapan (bukan bergantung
#     pada tebakan Whisper soal panjang jeda) -- PTT "aku" [lepas] PTT
#     "kamu" [lepas] menjadi "Aku. Kamu." bukan "aku kamu"/"aku, kamu".
#   - concat_audio_segments(): gabung AUDIO mentah/bersih per ucapan untuk
#     keperluan simpan-ke-WAV & pemutaran ulang ("Putar Audio Papua"),
#     dengan jeda hening pendek di antaranya supaya enak didengar (tidak
#     terdengar "menempel" tiba-tiba).
def join_segment_texts(texts: List[str]) -> str:
    """Gabung teks hasil transkripsi tiap ucapan (segmen PTT) jadi satu
    paragraf, memastikan SETIAP ucapan diakhiri tanda baca kalimat (".")
    kalau Whisper belum memberinya sendiri (mis. "!" atau "?")."""
    parts: List[str] = []
    for raw in texts:
        t = (raw or "").strip()
        if not t:
            continue
        if t[-1] not in ".!?":
            t += "."
        parts.append(t)
    return " ".join(parts)


def concat_audio_segments(
    segments: List[np.ndarray], sr: int, gap_sec: float = 0.4
) -> np.ndarray:
    """Sambung beberapa segmen audio (satu segmen = satu ucapan/siklus PTT)
    jadi satu buffer, disisipi jeda hening pendek di antara tiap segmen
    supaya sambungannya terdengar wajar saat diputar ulang/disimpan."""
    segments = [np.asarray(s, dtype=np.float32).reshape(-1) for s in segments if s is not None and s.size]
    if not segments:
        return np.array([], dtype=np.float32)
    if len(segments) == 1:
        return segments[0]
    gap = np.zeros(max(0, int(gap_sec * sr)), dtype=np.float32)
    pieces: List[np.ndarray] = []
    for i, seg in enumerate(segments):
        if i > 0:
            pieces.append(gap)
        pieces.append(seg)
    return np.concatenate(pieces).astype(np.float32, copy=False)


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if sr == TARGET_SR:
        return audio.astype(np.float32, copy=False)
    try:
        from scipy.signal import resample_poly
        import math as _math

        g = _math.gcd(sr, TARGET_SR)
        up, down = TARGET_SR // g, sr // g
        return resample_poly(audio, up, down).astype(np.float32)
    except Exception:
        import librosa

        return (
            librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=TARGET_SR)
            .astype(np.float32)
        )


def split_text_into_chunks(
    text: str, max_words: int = CHUNK_MAX_WORDS, overlap: int = CHUNK_OVERLAP
) -> List[str]:
    words = text.strip().split()
    n = len(words)
    if n == 0:
        return []
    chunks: List[str] = []
    i = 0
    while i < n:
        j = min(n, i + max_words)
        chunk_words = words[i:j]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if j == n:
            break
        i = max(j - overlap, 0)
        if i <= 0 and j == max_words:
            i = j - overlap
    return chunks


def split_audio_by_silence_pydub(
    audio16: np.ndarray,
    sr: int = TARGET_SR,
    min_silence_ms: int = 600,
    keep_silence_ms: int = 200,
    silence_db_drop: float = 16.0,
) -> List[np.ndarray]:
    audio16 = np.asarray(audio16, dtype=np.float32)
    if audio16.size == 0:
        return []
    audio16 = np.clip(audio16, -1.0, 1.0)
    samples_int16 = (audio16 * 32767.0).astype(np.int16)

    seg = AudioSegment(
        samples_int16.tobytes(),
        frame_rate=sr,
        frame_width=2,
        sample_width=2,
        channels=1,
    )

    if seg.dBFS == float("-inf"):
        thresh = -50.0
    else:
        thresh = seg.dBFS - float(silence_db_drop)

    chunks = split_on_silence(
        seg,
        min_silence_len=min_silence_ms,
        silence_thresh=thresh,
        keep_silence=keep_silence_ms,
    )

    result: List[np.ndarray] = []
    for ch in chunks:
        arr = (
            np.array(ch.get_array_of_samples(), dtype=np.int16).astype(np.float32)
            / 32768.0
        )
        if ch.channels > 1:
            arr = arr.reshape((-1, ch.channels)).mean(axis=1)
        result.append(arr)

    return result


# ======================
# AUDIO CLEANING UTAMA
# ======================

def bandpass_voice(data: np.ndarray, sample_rate: int,
                   lowcut: float = 300.0, highcut: float = 3400.0) -> np.ndarray:
    """
    Band-pass dengan Butterworth 4th order (telepon band 300–3400 Hz).
    Kalau scipy tidak ada, fallback ke FFT masker.
    """
    if data.size == 0:
        return data.astype(np.float32)

    try:
        from scipy.signal import butter, filtfilt

        nyq = 0.5 * float(sample_rate)
        low = lowcut / nyq
        high = highcut / nyq
        if high >= 1.0:
            high = 0.99
        if low <= 0.0:
            low = 0.001

        b, a = butter(4, [low, high], btype="bandpass")
        filtered = filtfilt(b, a, data)
        return filtered.astype(np.float32)
    except Exception:
        # Fallback FFT band-pass
        spectrum = np.fft.rfft(data)
        freqs = np.fft.rfftfreq(len(data), 1.0 / float(sample_rate))
        mask = (freqs >= lowcut) & (freqs <= highcut)
        spectrum[~mask] *= 0.1
        filtered = np.fft.irfft(spectrum, n=len(data))
        return filtered.astype(np.float32)


def trim_last_seconds(data: np.ndarray, sample_rate: int, seconds: float = 1.0) -> np.ndarray:
    """
    Buang beberapa detik terakhir (default 1 dtk), misalnya untuk menghilangkan noise 'klik' saat matikan radio.
    """
    if data.size == 0:
        return data.astype(np.float32)
    cut_samples = int(sample_rate * seconds)
    if data.shape[0] > cut_samples:
        return data[:-cut_samples].astype(np.float32)
    return data.astype(np.float32)


def trim_silence_edges(data: np.ndarray, sample_rate: int,
                       rel_threshold: float = 0.04,
                       min_silence_ms: int = 200) -> np.ndarray:
    """
    Potong silence di awal & akhir.
    """
    if data.size == 0:
        return data.astype(np.float32)

    amp = np.abs(data)
    max_amp = float(np.max(amp) + 1e-9)
    thr = rel_threshold * max_amp

    above = np.where(amp >= thr)[0]
    if above.size == 0:
        return data.astype(np.float32)

    first = int(above[0])
    last = int(above[-1])

    pad = int(sample_rate * (min_silence_ms / 1000.0) * 0.5)
    start = max(first - pad, 0)
    end = min(last + pad + 1, data.shape[0])

    return data[start:end].astype(np.float32)


def clean_for_whisper(data: np.ndarray, sample_rate: int) -> np.ndarray:
    """Cleaning aman untuk ucapan radio sempit tanpa memotong kata terakhir."""
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if data.size == 0:
        return data

    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    data = data - float(np.mean(data))
    data = bandpass_voice(data, sample_rate, 280, 3400)
    if data.size == 0:
        return data.astype(np.float32)

    data = spectral_denoise(data, sample_rate)
    if data.size == 0:
        return data.astype(np.float32)

    # VOX sudah menyediakan pre-roll/tail. Trim ringan hanya membuang silence
    # berlebih, dengan padding cukup agar konsonan awal/akhir tetap utuh.
    data = trim_silence_edges(
        data, sample_rate, rel_threshold=0.018, min_silence_ms=360
    )
    if data.size == 0:
        return data.astype(np.float32)

    amp = np.abs(data)
    noise_floor = float(np.percentile(amp, 18))
    gate_thresh = max(noise_floor * 1.35, 1e-6)
    # Soft gate kontinu menghindari bunyi patah-patah pada suku kata pelan.
    gain = np.clip(amp / gate_thresh, 0.18, 1.0)
    data = data * gain

    data = np.tanh(data * 1.6)
    data = pre_emphasis(data)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1e-7:
        data = data / peak * 0.95

    return np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)

def clean_for_whisper_upload_no_trim(data: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    Cleaning khusus upload audio.
    Tidak memotong durasi akhir.
    Tidak trim silence awal/akhir.
    """
    if data.size == 0:
        return data.astype(np.float32)

    data = data.astype(np.float32)

    # 1. Remove DC offset
    data = data - np.mean(data)

    # 2. Bandpass voice
    data = bandpass_voice(data, sample_rate, 300, 3000)

    # 3. Spectral Noise Reduction
    data = spectral_denoise(data, sample_rate)

    # CATATAN:
    # Tidak pakai trim_last_seconds()
    # Tidak pakai trim_silence_edges()

    # 4. Soft noise gate
    amp = np.abs(data)
    noise_floor = np.percentile(amp, 20)
    gate_thresh = noise_floor * 1.2

    data[amp < gate_thresh] *= 0.1

    # 5. Compression
    data = np.tanh(data * 2.0)

    # 6. Normalize
    max_val = np.max(np.abs(data)) + 1e-9
    data = data / max_val * 0.99

    # 7. Pre-emphasis
    data = pre_emphasis(data)

    return data.astype(np.float32)

# ==========================
# Torch / Transformers Env
# ==========================
class TorchEnv:
    def __init__(self):
        self._torch = None
        self._transformers = None
        self._peft = None
        self.device = None

    def ensure_torch(self):
        if self._torch is not None:
            return self._torch
        import torch

        self._torch = torch
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        return self._torch

    def ensure_transformers(self):
        if self._transformers is not None:
            return self._transformers
        import transformers

        self._transformers = transformers
        return self._transformers

    def ensure_peft(self):
        if getattr(self, "_peft", None) is not None:
            return self._peft
        import peft

        self._peft = peft
        return self._peft


torch_env = TorchEnv()


def clear_torch_memory():
    """
    Bersihkan cache PyTorch setelah inference.
    Ini tidak menghapus model aktif, tapi membantu mencegah OOM berulang.
    """
    try:
        gc.collect()
        torch = torch_env.ensure_torch()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def is_cuda_device() -> bool:
    try:
        return str(torch_env.device) == "cuda"
    except Exception:
        return False


def cuda_model_dtype():
    """
    Untuk GPU kecil, pakai FP16 saat CUDA tersedia.
    """
    torch = torch_env.ensure_torch()
    if is_cuda_device() and USE_FP16_CUDA:
        return torch.float16
    return torch.float32

def faster_whisper_device_compute():
    """
    Device dan compute_type untuk faster-whisper.
    Untuk GPU kecil 4 GB, int8_float16 biasanya lebih hemat VRAM.
    """
    torch = torch_env.ensure_torch()

    if torch.cuda.is_available():
        return "cuda", "int8"

    return "cpu", "int8"


def should_swap_models_for_vram() -> bool:
    """
    Swap Whisper<->MT (lepas-muat ulang dari disk) HANYA masuk akal kalau
    kita jalan di GPU kecil yang VRAM-nya terbatas. Kalau device-nya CPU,
    tidak ada VRAM yang perlu dihemat -- swap di CPU cuma buang-buang waktu
    reload model dari disk setiap gantian Whisper/Translate, tanpa manfaat
    apa pun. Jadi LOW_VRAM_MODE hanya berlaku efektif saat CUDA aktif.
    """
    return LOW_VRAM_MODE and is_cuda_device()



# ==========================
# PIPELINE SERVICE (NO GUI)
# ==========================
class PipelineService:
    def __init__(self,
             model_dir_radio: str = DEFAULT_WHISPER_MODEL_RADIO,
             model_dir_upload: str = DEFAULT_WHISPER_MODEL_UPLOAD,
             model_dir_mt: str = DEFAULT_YALI_ID_MODEL):

        # RADIO
        self.model_dir_radio = model_dir_radio

        # UPLOAD
        self.model_dir_upload = model_dir_upload

        # MT
        self.model_dir_mt = model_dir_mt

        # Bahasa Papua yang sedang aktif ("ambai"/"biak"). Menentukan folder
        # model Whisper & MT (best_bleu) mana yang dipakai -- lihat
        # set_language() di bawah, dipanggil dari endpoint /set-lang,
        # /record-radio, /upload-audio, dan /translate-text.
        self.current_lang = PAPUA_LANG_DEFAULT

        # model cache
        self._whisper_model_radio = None
        self._whisper_model_upload = None

        self._tok_yali_id = None
        self._mdl_yali_id = None
        self._mt_forced_bos_token_id = None

        # state default untuk endpoint /rms dan audio playback
        self.current_rms = 0.0
        self.current_threshold = RMS_THRESHOLD
        self.current_phase = "idle"
        # PERBAIKAN: dulu UI hanya tahu 4 fase generik (idle/listening/
        # recording/processing) lewat current_phase, jadi pill status "Siap"
        # di frontend tidak pernah menampilkan APA yang sedang dikerjakan di
        # backend (mis. "Whisper radio" vs "menerjemahkan" vs "membuat TTS"
        # semuanya cuma muncul sebagai "Memproses…" generik, dan endpoint yang
        # tidak menyentuh current_phase sama sekali -- /translate-text,
        # /tts, /preview-upload-audio -- pill-nya diam total). current_label
        # ini diisi teks manusiawi di SETIAP titik current_phase berubah (di
        # seluruh file), lalu dikirim ke frontend lewat /rms supaya pill
        # selalu mengikuti keterangan asli dari backend, bukan tebakan lokal.
        self.current_label = "Siap"
        self.last_audio_clean = None
        self.last_audio_sr = 0
        self.last_saved_path = None
        self.last_audio_updated_at = 0.0
        # PERBAIKAN (kecepatan pemutaran "Putar Audio Papua"): sebelumnya
        # /last-audio.wav SELALU meng-encode ulang audio ke WAV dari nol
        # setiap kali diminta -- padahal isinya sering sama (user klik Play
        # dua kali, atau audio belum berubah sejak terakhir kali). Cache di
        # bawah dipakai supaya encoding WAV hanya diulang saat audio memang
        # berubah (ditandai lewat last_audio_updated_at), bukan setiap klik.
        self._last_audio_wav_cache: Optional[bytes] = None
        self._last_audio_wav_cache_at: float = -1.0

        # Satu perangkat audio/model tidak boleh dipakai oleh dua request
        # /record-radio bersamaan. Ini mencegah "device busy" dan bentrok VRAM.
        self.record_lock = threading.Lock()
        self.model_lock = threading.RLock()

        # Di-set true dari endpoint /record-radio/stop supaya rekaman yang
        # sedang berjalan berhenti SECEPATNYA (dicek tiap blok audio di
        # callback), bukan menunggu batas RECORD_MAX_SECONDS.
        self.cancel_event = threading.Event()

        # PERBAIKAN (kecepatan "Play TTS Indonesia"): gTTS memanggil layanan
        # online Google setiap kali dipanggil, walau teksnya persis sama
        # dengan permintaan sebelumnya -- itu sebabnya klik ulang kadang
        # terasa lambat (tergantung koneksi internet & respons server Google
        # saat itu). Cache di bawah menyimpan hasil MP3 per teks (key = hash
        # teks) di memori, supaya teks yang SAMA cukup di-generate sekali;
        # klik ulang berikutnya untuk teks yang sama langsung instan tanpa
        # memanggil Google lagi. Cache dibatasi jumlah entrinya (LRU sangat
        # sederhana) supaya tidak membengkak tanpa batas kalau banyak teks
        # berbeda-beda yang di-TTS-kan.
        self._tts_cache: dict[str, bytes] = {}
        self._tts_cache_order: deque = deque()
        self._tts_cache_lock = threading.Lock()
        self._tts_cache_max_entries = 50

        # Perangkat audio lokal terakhir yang dipakai user lewat dropdown UI
        # saat /record-radio dipanggil (index sounddevice, BUKAN nilai semu
        # Web-888). Dipakai AutoFreqScanner sebagai fallback untuk mengukur
        # level sinyal saat sumber aktifnya SDR++/rigctl (bukan Web-888),
        # supaya scanner bisa tahu "ada sinyal atau tidak" tanpa perlu field
        # baru apapun di UI.
        self.last_device_index = None

    # ---------- LOW VRAM HELPERS ----------
    def _unload_whisper_models(self):
        """
        Lepas model faster-whisper agar memori lebih lega untuk model translate.
        """
        changed = False

        if self._whisper_model_radio is not None:
            self._whisper_model_radio = None
            changed = True

        if self._whisper_model_upload is not None:
            self._whisper_model_upload = None
            changed = True

        if changed:
            print("[VRAM] faster-whisper model dilepas.", file=sys.stderr)
            gc.collect()
            clear_torch_memory()

    def _unload_mt_model(self):
        """
        Lepas model MT/best_bleu dari GPU agar VRAM cukup untuk Whisper.
        Tokenizer tetap disimpan karena kecil.
        """
        if self._mdl_yali_id is not None:
            try:
                self._mdl_yali_id.to("cpu")
            except Exception:
                pass
            self._mdl_yali_id = None
            print("[VRAM] MT model dilepas dari GPU.", file=sys.stderr)
            clear_torch_memory()

    # ---------- CACHE ENCODING WAV UNTUK "PUTAR AUDIO PAPUA" ----------
    def get_last_audio_wav_bytes(self) -> Optional[bytes]:
        """
        Encode self.last_audio_clean ke WAV (PCM16), tapi hanya kalau belum
        pernah di-encode untuk versi audio yang sama -- supaya klik "Putar
        Audio Papua" berulang kali TIDAK selalu meng-encode ulang dari nol
        (lebih cepat, terutama untuk audio yang panjang).
        """
        if self.last_audio_clean is None or self.last_audio_sr <= 0:
            return None

        if (
            self._last_audio_wav_cache is not None
            and self._last_audio_wav_cache_at == self.last_audio_updated_at
        ):
            return self._last_audio_wav_cache

        audio = np.asarray(self.last_audio_clean, dtype=np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        pcm16 = (audio * 32767.0).astype(np.int16)

        buf = io.BytesIO()
        sf.write(buf, pcm16, self.last_audio_sr, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        self._last_audio_wav_cache = wav_bytes
        self._last_audio_wav_cache_at = self.last_audio_updated_at
        return wav_bytes

    # ---------- GANTI BAHASA PAPUA (ambai / biak) ----------
    def set_language(self, lang: str) -> dict:
        """
        Ganti bahasa Papua aktif dan folder model yang dipakai:
          - Whisper (radio & upload)  -> WHISPER_MODEL_DIRS[lang]
          - MT/best_bleu              -> MT_MODEL_DIRS[lang]

        Model yang sedang dimuat di memori dilepas supaya request berikutnya
        memuat ulang model bahasa yang baru dari disk. Setiap hasil (berhasil
        maupun gagal) SELALU dicetak ke console/log backend supaya perubahan
        bahasa selalu terlihat jelas.
        """
        raw_lang = lang
        lang = (lang or "").strip().lower()

        if not lang:
            # Tidak ada bahasa dikirim -> pertahankan bahasa yang sedang aktif.
            return {"ok": True, "lang": self.current_lang, "changed": False}

        if lang not in WHISPER_MODEL_DIRS or lang not in MT_MODEL_DIRS:
            msg = (
                f"Bahasa Papua tidak dikenal: '{raw_lang}'. "
                f"Pilihan yang tersedia: {', '.join(WHISPER_MODEL_DIRS.keys())}."
            )
            print(f"[LANG] GAGAL — {msg}", file=sys.stderr)
            return {"ok": False, "error": msg, "lang": self.current_lang}

        whisper_dir = WHISPER_MODEL_DIRS[lang]
        mt_dir = MT_MODEL_DIRS[lang]

        missing = [p for p in (whisper_dir, mt_dir) if not Path(p).is_dir()]
        if missing:
            msg = (
                f"Gagal berganti ke bahasa '{lang}': folder model tidak ditemukan -> "
                + ", ".join(missing)
            )
            print(f"[LANG] GAGAL — {msg}", file=sys.stderr)
            return {"ok": False, "error": msg, "lang": self.current_lang}

        already_active = (
            lang == self.current_lang
            and self.model_dir_radio == whisper_dir
            and self.model_dir_upload == whisper_dir
            and self.model_dir_mt == mt_dir
        )
        if already_active:
            print(f"[LANG] Bahasa Papua sudah aktif: '{lang}' (tidak ada perubahan).", file=sys.stderr)
            return {"ok": True, "lang": lang, "changed": False}

        with self.model_lock:
            self.model_dir_radio = whisper_dir
            self.model_dir_upload = whisper_dir
            self.model_dir_mt = mt_dir
            self.current_lang = lang
            # Lepas model yang sedang aktif di memori supaya model bahasa
            # baru dimuat ulang dari disk saat benar-benar dipakai berikutnya.
            self._whisper_model_radio = None
            self._whisper_model_upload = None
            self._tok_yali_id = None
            self._mdl_yali_id = None
            self._mt_forced_bos_token_id = None
            clear_torch_memory()

        print(
            f"[LANG] BERHASIL berganti bahasa Papua ke '{lang}'. "
            f"Whisper: {whisper_dir} | MT/best_bleu: {mt_dir}",
            file=sys.stderr,
        )
        return {"ok": True, "lang": lang, "changed": True}

    # ---------- AUDIO RADIO (VOX RMS) ----------
    def record_radio_rms(
        self,
        device_index: int,
        threshold: float = RMS_THRESHOLD,
        blocksize: int = RADIO_BLOCKSIZE,
        sample_rate: int = RADIO_SAMPLE_RATE,
        max_sec: float = LISTEN_MAX_SECONDS,
        record_max_sec: float = RECORD_MAX_SECONDS,
    ) -> Tuple[List[np.ndarray], int]:
        """
        VOX/PTT dari input audio lokal (SDR++/VB-Cable/USB).

        Trigger harus bertahan singkat agar noise impulsif tidak memulai rekam.
        Pre-roll menyimpan awal ucapan.

        PERBAIKAN: satu sesi rekam sekarang bisa menangkap LEBIH DARI SATU
        ucapan (satu ucapan = satu siklus tekan-lepas PTT). Setiap kali PTT
        dilepas dan rilisnya terkonfirmasi (RMS di bawah ambang selama
        VOX_RELEASE_SECONDS), ucapan yang baru direkam ditutup sebagai SATU
        SEGMEN audio tersendiri dan backend kembali menunggu ucapan
        berikutnya -- TANPA PERNAH mengembalikan kontrol ke caller/web hanya
        karena PTT dilepas. Sesi baru benar-benar berakhir (fungsi return)
        kalau: (a) user menekan stop manual di web (cancel_event, lihat
        endpoint /record-radio/stop), atau (b) tidak ada PTT baru sama
        sekali selama max_sec sejak segmen terakhir berakhir (dianggap user
        lupa menekan stop).

        Tiap segmen dikembalikan APA ADANYA (belum digabung/dibersihkan)
        supaya pemanggil bisa men-transkrip Whisper PER SEGMEN lalu
        menggabung hasilnya dengan tanda titik di antaranya -- misal PTT
        "aku" [lepas] PTT "kamu" [lepas] [stop manual] akan menjadi teks
        "Aku. Kamu." yang jelas batas kalimatnya, bukan "aku kamu" yang
        ambigu bagi Whisper/terjemahan.
        """
        self.current_threshold = float(threshold)
        self.current_phase = "listening"
        self.current_label = "Mendengarkan sinyal radio (VOX)…"

        try:
            info = sd.query_devices(device_index, "input")
            sr = int(info.get("default_samplerate") or sample_rate)
        except Exception:
            sr = int(sample_rate)

        blocksize = max(int(blocksize), 128)
        max_listen_frames = max(1, int(max_sec * sr))
        max_record_frames = max(1, int(record_max_sec * sr))
        trigger_frames_needed = max(blocksize, int(VOX_TRIGGER_SECONDS * sr))
        release_frames_needed = max(blocksize, int(VOX_RELEASE_SECONDS * sr))
        pre_roll_blocks = max(1, int(np.ceil(VOX_PRE_ROLL_SECONDS * sr / blocksize)))

        is_recording = False
        current_blocks: List[np.ndarray] = []
        segments: List[np.ndarray] = []
        pre_roll = deque(maxlen=pre_roll_blocks)
        listen_frames = 0
        record_frames = 0
        above_frames = 0
        below_frames = 0
        should_stop = False
        noise_floor_rms: Optional[float] = None
        effective_threshold = float(threshold)
        adaptive_threshold_cap = max(
            float(os.environ.get("YALI_VOX_ADAPTIVE_MAX", "0.003")),
            float(threshold),
        )

        def finalize_segment(reason: str):
            """Tutup ucapan yang sedang direkam jadi satu segmen, lalu balik
            menunggu ucapan berikutnya (PTT ditekan lagi) -- sesi TIDAK
            berakhir di sini."""
            nonlocal current_blocks, is_recording, listen_frames, above_frames, below_frames
            if current_blocks:
                segments.append(np.concatenate(current_blocks).astype(np.float32, copy=False))
                seg_dur = segments[-1].size / sr
                print(f"[SEGMENT] Ucapan #{len(segments)} selesai ({seg_dur:.2f} dtk) -- {reason}.", file=sys.stderr)
            current_blocks = []
            is_recording = False
            listen_frames = 0
            above_frames = 0
            below_frames = 0
            pre_roll.clear()
            self.current_phase = "listening"
            self.current_label = f"Ucapan #{len(segments)} tersimpan, menunggu PTT berikutnya…"

        def callback(indata, frames, time_info, status):
            nonlocal is_recording, current_blocks, listen_frames, record_frames
            nonlocal above_frames, below_frames, should_stop
            nonlocal noise_floor_rms, effective_threshold

            if status:
                print(f"[PortAudio status] {status}", file=sys.stderr)
            if frames <= 0:
                return
            if self.cancel_event.is_set():
                should_stop = True
                return

            block = np.asarray(indata[:, 0], dtype=np.float32).copy()
            rms = float(np.sqrt(np.mean(block * block) + 1e-12)) if block.size else 0.0
            self.current_rms = rms

            if not is_recording:
                listen_frames += frames
                pre_roll.append(block)

                # Ambang adaptif mengikuti noise perangkat, tetapi dibatasi agar
                # PTT yang ditekan segera setelah tombol Play tetap terdeteksi.
                if noise_floor_rms is None:
                    noise_floor_rms = rms
                elif rms < effective_threshold * 1.25:
                    noise_floor_rms = 0.92 * noise_floor_rms + 0.08 * rms
                effective_threshold = min(
                    adaptive_threshold_cap,
                    max(float(threshold), float(noise_floor_rms) * 2.6),
                )
                self.current_threshold = effective_threshold
                above_frames = (
                    above_frames + frames if rms >= effective_threshold else 0
                )

                if above_frames >= trigger_frames_needed:
                    is_recording = True
                    self.current_phase = "recording"
                    seg_no = len(segments) + 1
                    self.current_label = f"Merekam ucapan #{seg_no} (berhenti manual di web)…"
                    current_blocks = list(pre_roll)
                    record_frames = sum(x.size for x in current_blocks)
                    below_frames = 0
                    print(f"[START] Rekam ucapan #{seg_no} (RMS={rms:.8e})", file=sys.stderr)
                elif listen_frames >= max_listen_frames:
                    should_stop = True
            else:
                current_blocks.append(block)
                record_frames += frames

                if rms < max(float(threshold), effective_threshold * 0.72):
                    below_frames += frames
                else:
                    below_frames = 0

                if record_frames >= max_record_frames:
                    finalize_segment(f"batas aman {record_max_sec:.0f} dtk tercapai")
                elif below_frames >= release_frames_needed:
                    finalize_segment(f"PTT dilepas ({below_frames / sr:.2f} dtk di bawah threshold)")

        try:
            with sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=sr,
                blocksize=blocksize,
                callback=callback,
                dtype="float32",
            ):
                while not should_stop:
                    sd.sleep(50)
        finally:
            self.current_rms = 0.0

        # Kalau berhenti manual/timeout SAAT MASIH merekam (PTT belum sempat
        # dilepas lagi), tetap simpan ucapan terakhir yang sedang berjalan
        # sebagai segmen -- jangan sampai ucapan terakhir hilang begitu saja.
        if is_recording and current_blocks:
            segments.append(np.concatenate(current_blocks).astype(np.float32, copy=False))
            print(f"[SEGMENT] Ucapan #{len(segments)} ditutup paksa (stop manual/timeout).", file=sys.stderr)

        if not segments:
            self.current_phase = "idle"
            self.current_label = "Siap"
            return [], sr

        total_dur = sum(seg.size for seg in segments) / sr
        print(
            f"[INFO] Sesi rekam radio selesai: {len(segments)} ucapan, total {total_dur:.2f} dtk @ {sr} Hz",
            file=sys.stderr,
        )
        return segments, sr

    # ---------- AUDIO RADIO LANGSUNG DARI WEB-888 (tanpa kabel/device lokal) ----------
    def record_radio_web888(
        self,
        client: "Web888Client",
        threshold: float = RMS_THRESHOLD,
        max_sec: float = LISTEN_MAX_SECONDS,
        record_max_sec: float = RECORD_MAX_SECONDS,
    ) -> Tuple[List[np.ndarray], int]:
        """
        VOX/PTT langsung dari Web-888. Buffer rekam terpisah dari monitor
        browser, sehingga Set Radio tetap dapat didengar saat Auto Translate
        aktif.

        PERBAIKAN: sama seperti record_radio_rms() -- satu sesi rekam bisa
        menangkap LEBIH DARI SATU ucapan (satu ucapan = satu siklus
        tekan-lepas PTT/squelch). Setiap kali squelch tertutup/PTT dilepas
        dan rilisnya terkonfirmasi (VOX_RELEASE_SECONDS), ucapan yang baru
        direkam ditutup sebagai SATU SEGMEN tersendiri dan backend kembali
        menunggu ucapan berikutnya -- TANPA PERNAH mengembalikan kontrol ke
        caller/web hanya karena PTT dilepas. Sesi baru benar-benar berakhir
        (fungsi return) kalau: (a) user menekan stop manual di web
        (cancel_event, lihat endpoint /record-radio/stop), atau (b) tidak
        ada PTT baru sama sekali selama max_sec sejak segmen terakhir
        berakhir.

        Tiap segmen dikembalikan APA ADANYA supaya pemanggil bisa
        men-transkrip Whisper PER SEGMEN lalu menggabung hasilnya dengan
        tanda titik di antaranya -- misal PTT "aku" [lepas] PTT "kamu"
        [lepas] [stop manual] akan menjadi "Aku. Kamu.", bukan "aku kamu".
        """
        self.current_threshold = float(threshold)
        self.current_phase = "listening"
        self.current_label = "Mendengarkan sinyal radio via Web-888…"
        client.clear_audio()

        sr = int(client.get_audio_sample_rate() or KIWI_AUDIO_RATE)
        is_recording = False
        current_chunks: List[np.ndarray] = []
        segments: List[np.ndarray] = []
        listen_started = time.monotonic()
        record_started = 0.0
        last_audio_at = 0.0
        release_started: Optional[float] = None

        def finalize_segment(reason: str):
            """Tutup ucapan yang sedang direkam jadi satu segmen, lalu balik
            menunggu ucapan berikutnya -- sesi TIDAK berakhir di sini."""
            nonlocal current_chunks, is_recording, listen_started, release_started
            if current_chunks:
                segments.append(np.concatenate(current_chunks).astype(np.float32, copy=False))
                seg_dur = segments[-1].size / sr
                print(f"[WEB888] [SEGMENT] Ucapan #{len(segments)} selesai ({seg_dur:.2f} dtk) -- {reason}.", file=sys.stderr)
            current_chunks = []
            is_recording = False
            listen_started = time.monotonic()
            release_started = None
            self.current_phase = "listening"
            self.current_label = f"Ucapan #{len(segments)} tersimpan, menunggu PTT berikutnya…"

        while True:
            now = time.monotonic()
            if self.cancel_event.is_set():
                print("[WEB888] Dihentikan manual.", file=sys.stderr)
                break
            if not client.connected_snd:
                raise RuntimeError("Koneksi audio Web-888 terputus.")
            if not is_recording and now - listen_started >= max_sec:
                break
            if is_recording and now - record_started >= record_max_sec:
                finalize_segment(f"batas aman {record_max_sec:.0f} dtk tercapai")
                continue

            chunk = client.pop_audio(max_samples=max(1, int(sr * 0.25)))
            if chunk.size:
                chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
                rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
                self.current_rms = rms
                last_audio_at = now

                if not is_recording:
                    # Client sudah menerapkan squelch/histeresis. RMS tetap
                    # menjadi fallback untuk firmware yang tidak memberi S-meter.
                    if client.is_squelch_open() or rms >= threshold:
                        is_recording = True
                        record_started = now
                        self.current_phase = "recording"
                        seg_no = len(segments) + 1
                        self.current_label = f"Merekam ucapan #{seg_no} (Web-888, berhenti manual di web)…"
                        current_chunks.append(chunk)
                        release_started = None
                        print(f"[WEB888] [START] Rekam ucapan #{seg_no} (RMS={rms:.8e})", file=sys.stderr)
                else:
                    current_chunks.append(chunk)
                    is_low = (not client.is_squelch_open()) and rms < threshold
                    if is_low:
                        if release_started is None:
                            release_started = now
                        elif now - release_started >= VOX_RELEASE_SECONDS:
                            finalize_segment(f"PTT dilepas ({now - release_started:.2f} dtk di bawah threshold)")
                    else:
                        release_started = None
            else:
                self.current_rms = float(getattr(client, "current_rms", 0.0) or 0.0)
                if is_recording:
                    is_low = not client.is_squelch_open()
                    if is_low:
                        if release_started is None:
                            release_started = now
                        elif now - release_started >= VOX_RELEASE_SECONDS:
                            finalize_segment(f"PTT dilepas ({now - release_started:.2f} dtk di bawah threshold)")
                    else:
                        release_started = None
                time.sleep(0.02)

        self.current_rms = 0.0

        # Kalau berhenti manual/timeout SAAT MASIH merekam (PTT belum sempat
        # dilepas lagi), tetap simpan ucapan terakhir yang sedang berjalan.
        if is_recording and current_chunks:
            segments.append(np.concatenate(current_chunks).astype(np.float32, copy=False))
            print(f"[WEB888] [SEGMENT] Ucapan #{len(segments)} ditutup paksa (stop manual/timeout).", file=sys.stderr)

        if not segments:
            self.current_phase = "idle"
            self.current_label = "Siap"
            return [], sr

        total_dur = sum(seg.size for seg in segments) / sr
        print(
            f"[WEB888] Sesi rekam radio selesai: {len(segments)} ucapan, total {total_dur:.2f} dtk @ {sr} Hz",
            file=sys.stderr,
        )
        return segments, sr

    # ---------- WHISPER FASTER-WHISPER / CTranslate2 ----------
    def _ensure_whisper_radio(self):
        from faster_whisper import WhisperModel

        if self._whisper_model_radio is None:
            if should_swap_models_for_vram():
                self._unload_mt_model()

            device, compute_type = faster_whisper_device_compute()

            print(
                f"[FASTER-WHISPER RADIO] Loading model: {self.model_dir_radio} "
                f"device={device}, compute_type={compute_type}",
                file=sys.stderr
            )

            self._whisper_model_radio = WhisperModel(
                self.model_dir_radio,
                device=device,
                compute_type=compute_type,
            )

            clear_torch_memory()


    def _ensure_whisper_upload(self):
        from faster_whisper import WhisperModel

        if self._whisper_model_upload is None:
            if should_swap_models_for_vram():
                self._unload_mt_model()

            device, compute_type = faster_whisper_device_compute()

            print(
                f"[FASTER-WHISPER UPLOAD] Loading model: {self.model_dir_upload} "
                f"device={device}, compute_type={compute_type}",
                file=sys.stderr
            )

            self._whisper_model_upload = WhisperModel(
                self.model_dir_upload,
                device=device,
                compute_type=compute_type,
            )

            clear_torch_memory()


    def whisper_transcribe_radio(self, audio16):
        with self.model_lock:
            self._ensure_whisper_radio()
            segments, info = self._whisper_model_radio.transcribe(
                audio16,
                beam_size=1,
                # PERBAIKAN: language=None memaksa faster-whisper mendeteksi
                # bahasa otomatis lewat daftar ~99 token bahasa multibahasa
                # bawaan Whisper. Model hasil fine-tuning Papua (Ambai/Biak)
                # tidak lagi punya token-token itu secara lengkap, sehingga
                # auto-detect menabrak index di luar jangkauan dan gagal
                # dengan error "list index out of range". Kode bahasa "id"
                # dipakai sebagai kode dummy yang aman (token itu tetap ada
                # di vocabulary dasar Whisper) -- ini TIDAK memaksa hasil
                # transkripsi jadi bahasa Indonesia, cuma menentukan token
                # bahasa awal saat decoding; isi transkripsi tetap mengikuti
                # apa yang dipelajari model dari data fine-tuning.
                language="id",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 180},
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
            clear_torch_memory()
            return text

    def whisper_transcribe_upload(self, audio16):
        with self.model_lock:
            self._ensure_whisper_upload()
            segments, info = self._whisper_model_upload.transcribe(
                audio16,
                beam_size=1,
                # Lihat catatan PERBAIKAN yang sama di whisper_transcribe_radio().
                language="id",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 350, "speech_pad_ms": 180},
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
            clear_torch_memory()
            return text


    # ---------- MT best_bleu ----------
    def _ensure_yali_id(self):
        torch_env.ensure_torch()
        transformers = torch_env.ensure_transformers()
        AutoConfig = getattr(transformers, "AutoConfig")
        AutoTokenizer = getattr(transformers, "AutoTokenizer")
        AutoModelForSeq2SeqLM = getattr(
            transformers, "AutoModelForSeq2SeqLM"
        )

        if self._tok_yali_id is None or self._mdl_yali_id is None:
            # Mode hemat VRAM: sebelum load MT ke GPU, kosongkan Whisper dari GPU
            if should_swap_models_for_vram():
                self._unload_whisper_models()

            dtype = cuda_model_dtype()
            print(f"[MT] Loading best_bleu MT model to {torch_env.device} dtype={dtype} …", file=sys.stderr)
            model_dir = str(Path(self.model_dir_mt).resolve())

            config_path = Path(model_dir) / "config.json"
            adapter_config_path = Path(model_dir) / "adapter_config.json"

            if config_path.exists():
                # Folder berisi model utuh (bukan adapter LoRA/PEFT).
                _ = AutoConfig.from_pretrained(model_dir, local_files_only=True)
                tok = AutoTokenizer.from_pretrained(
                    model_dir, use_fast=True, local_files_only=True
                )
                mdl = AutoModelForSeq2SeqLM.from_pretrained(
                    model_dir,
                    local_files_only=True,
                    torch_dtype=dtype,
                    low_cpu_mem_usage=True,
                ).to(torch_env.device).eval()

            elif adapter_config_path.exists():
                # PENTING: folder ini adalah hasil fine-tuning LoRA/PEFT
                # (isinya cuma adapter_config.json + adapter_model.safetensors,
                # dsb -- lihat README di folder itu). Folder semacam ini TIDAK
                # punya config.json sendiri, jadi tidak bisa langsung dibuka
                # dengan AutoModelForSeq2SeqLM.from_pretrained(model_dir) --
                # itulah sumber error "Unrecognized model ... Should have a
                # `model_type` key in its config.json". Model dasarnya harus
                # dimuat dulu (dari 'base_model_name_or_path' di dalam
                # adapter_config.json), baru adapter LoRA-nya dipasang di atas.
                import json

                with open(adapter_config_path, "r", encoding="utf-8") as f:
                    adapter_cfg = json.load(f)
                base_model_name = adapter_cfg.get("base_model_name_or_path")
                if not base_model_name:
                    raise RuntimeError(
                        f"'{adapter_config_path}' tidak punya field "
                        "'base_model_name_or_path', jadi base model untuk "
                        "adapter LoRA ini tidak diketahui."
                    )

                peft = torch_env.ensure_peft()
                PeftModel = getattr(peft, "PeftModel")

                print(
                    f"[MT] '{model_dir}' adalah adapter LoRA/PEFT -> "
                    f"memuat base model '{base_model_name}' dahulu…",
                    file=sys.stderr,
                )

                # Tokenizer: pakai yang disimpan bersama adapter (folder
                # 'tokenizer'/'tokenizer_config' di checkpoint) kalau ada,
                # kalau tidak fallback ke tokenizer base model.
                try:
                    tok = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
                except Exception:
                    tok = AutoTokenizer.from_pretrained(base_model_name, use_fast=True)

                base_mdl = AutoModelForSeq2SeqLM.from_pretrained(
                    base_model_name,
                    torch_dtype=dtype,
                    low_cpu_mem_usage=True,
                )
                mdl = PeftModel.from_pretrained(base_mdl, model_dir)
                # Gabungkan bobot adapter ke base model supaya inference
                # secepat model biasa (tidak perlu hitung LoRA tiap forward).
                mdl = mdl.merge_and_unload()
                mdl = mdl.to(torch_env.device).eval()

            else:
                raise RuntimeError(
                    f"Folder model MT '{model_dir}' tidak berisi config.json "
                    "maupun adapter_config.json, jadi bukan folder model "
                    "(atau checkpoint LoRA) yang valid."
                )

            # ---- Paksa kode bahasa mBART-50 (src & target) ----
            # Tanpa ini, model multibahasa mBART-50 bisa memilih bahasa
            # keluaran yang salah (lihat catatan di MT_SRC_LANG_CODE /
            # MT_TGT_LANG_CODE di atas).
            src_code = MT_SRC_LANG_CODE.get(self.current_lang, "id_ID")
            if hasattr(tok, "src_lang"):
                try:
                    tok.src_lang = src_code
                except Exception as exc:
                    print(f"[MT] Gagal set tok.src_lang='{src_code}': {exc}", file=sys.stderr)

            forced_bos_token_id = None
            lang_code_to_id = getattr(tok, "lang_code_to_id", None)
            if lang_code_to_id and MT_TGT_LANG_CODE in lang_code_to_id:
                forced_bos_token_id = lang_code_to_id[MT_TGT_LANG_CODE]
            else:
                print(
                    f"[MT] PERINGATAN: kode bahasa target '{MT_TGT_LANG_CODE}' "
                    "tidak ditemukan di tokenizer.lang_code_to_id -- "
                    "forced_bos_token_id tidak di-set, terjemahan bisa "
                    "salah bahasa. Cek MT_TGT_LANG_CODE / tokenizer_config.json.",
                    file=sys.stderr,
                )
            self._mt_forced_bos_token_id = forced_bos_token_id

            if tok.pad_token is None:
                tok.pad_token = tok.eos_token or tok.bos_token
                mdl.config.pad_token_id = tok.pad_token_id
            self._tok_yali_id, self._mdl_yali_id = tok, mdl
            clear_torch_memory()

    def _yali_to_id_single(self, text: str) -> str:
        torch = torch_env.ensure_torch()
        transformers = torch_env.ensure_transformers()
        GenerationConfig = getattr(transformers, "GenerationConfig")
        tok, mdl = self._tok_yali_id, self._mdl_yali_id
        enc = tok(
            [text],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=192,
        ).to(torch_env.device)

        # forced_bos_token_id: paksa mBART-50 keluarkan bahasa target yang
        # benar (lihat MT_TGT_LANG_CODE). Kalau tidak ditemukan saat load
        # model, fallback ke default bawaan model (bisa saja salah bahasa).
        forced_bos_token_id = (
            self._mt_forced_bos_token_id
            if self._mt_forced_bos_token_id is not None
            else getattr(mdl.config, "forced_bos_token_id", None)
        )

        gen_cfg = GenerationConfig(
            max_new_tokens=128,
            num_beams=MT_NUM_BEAMS,
            do_sample=False,
            use_cache=True,
            forced_bos_token_id=forced_bos_token_id,
        )

        with torch.inference_mode():
            if is_cuda_device():
                # autocast hemat VRAM saat generate di CUDA
                with torch.cuda.amp.autocast(enabled=USE_FP16_CUDA):
                    gen_ids = mdl.generate(**enc, generation_config=gen_cfg)
            else:
                gen_ids = mdl.generate(**enc, generation_config=gen_cfg)

        out = tok.batch_decode(gen_ids, skip_special_tokens=True)[0]

        del enc, gen_ids
        clear_torch_memory()
        return out

    def yali_to_id_segments_bestbleu(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        with self.model_lock:
            original = text
            raw_segments = text.split(".")
            segments = [seg.strip() for seg in raw_segments if seg.strip()]
            if not segments:
                return ""

            self._ensure_yali_id()
            translated_segments: List[str] = []
            for seg in segments:
                try:
                    sub_chunks = split_text_into_chunks(seg, CHUNK_MAX_WORDS, CHUNK_OVERLAP)
                    out_sub = []
                    for ch in sub_chunks:
                        ch = ch.strip()
                        if ch:
                            out_sub.append(self._yali_to_id_single(ch))
                    seg_id = " ".join(out_sub).strip()
                    if seg_id:
                        translated_segments.append(seg_id)
                except Exception as exc:
                    print(f"[MT] Gagal menerjemahkan segmen: {exc}", file=sys.stderr)

            if not translated_segments:
                return ""
            out = ". ".join(translated_segments).strip()
            if original.endswith(".") and not out.endswith("."):
                out += "."
            return out


# global service
pipeline = PipelineService()


# ==========================
# FLASK APP
# ==========================
app = Flask(__name__, static_folder="static", template_folder="templates")
# PENTING: tanpa ini, browser bisa menyimpan cache lama script.js/style.css
# dan terus memakainya walau file di server sudah diperbarui -- inilah
# kemungkinan besar kenapa perubahan labeling frekuensi "belum kelihatan"
# meski kodenya sudah benar diganti. Matikan cache statis supaya setiap
# reload selalu ambil versi terbaru dari disk.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    # Serve a real favicon kalau ada di static/favicon.ico, kalau tidak
    # cukup balas "no content" supaya browser berhenti mencatat 404.
    favicon_path = BASE / "static" / "favicon.ico"
    if favicon_path.exists():
        return send_file(str(favicon_path), mimetype="image/x-icon")
    return ("", 204)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "device": str(getattr(torch_env, "device", None))})


@app.route("/set-lang", methods=["POST"])
def set_lang():
    """
    Dipanggil dari dropdown "Pilih Bahasa Papua" begitu user mengganti
    pilihan (ambai/biak). Mengganti folder model Whisper & MT/best_bleu
    yang aktif di pipeline, dan selalu mencatat hasilnya (berhasil/gagal)
    ke console backend lewat pipeline.set_language().
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        lang = data.get("lang", "")
        result = pipeline.set_language(lang)
        return jsonify(result), 200
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[LANG] GAGAL — exception saat ganti bahasa: {e}\n{tb}", file=sys.stderr)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/devices", methods=["GET"])
def list_devices():
    try:
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        out = []

        # Opsi audio LANGSUNG dari Web-888 lewat WebSocket (tanpa kabel virtual/VB-Cable).
        # Selalu ditampilkan di dropdown yang sama; kalau dipilih tapi Web-888 belum
        # tersambung (lewat panel Spektrum), /record-radio akan membalas error yang jelas.
        out.append(
            {
                "index": WEB888_VIRTUAL_DEVICE_INDEX,
                "name": "Web-888 (Langsung via WebSocket, tanpa kabel)",
                "hostapi": "Jaringan",
                "max_input_channels": 1,
                "default_samplerate": KIWI_AUDIO_RATE,
            }
        )

        for i, d in enumerate(devs):
            max_in = int(d.get("max_input_channels", 0) or 0)
            if max_in <= 0:
                continue
            hostapi_idx = d.get("hostapi")
            hostapi_name = "?"
            if hostapi_idx is not None and 0 <= hostapi_idx < len(hostapis):
                hostapi_name = hostapis[hostapi_idx].get("name", "?")
            out.append(
                {
                    "index": i,
                    "name": d.get("name", "?"),
                    "hostapi": hostapi_name,
                    "max_input_channels": max_in,
                    "default_samplerate": int(d.get("default_samplerate") or 0),
                }
            )
        return jsonify({"ok": True, "devices": out})
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


# ==========================
# SPEKTRUM REAL-TIME VIA RTL_TCP
# ==========================
# RTL-SDR cuma bisa dipegang SATU program dalam satu waktu. Karena SDR++
# sudah memegang dongle untuk demodulasi (output ke VB-Cable), backend ini
# TIDAK membuka RTL-SDR secara langsung -- itu akan bentrok ("device busy").
#
# Solusinya: jalankan "rtl_tcp" (server kecil bawaan driver RTL-SDR,
# biasanya rtl_tcp.exe) di komputer yang sama. rtl_tcp yang memegang dongle,
# lalu SDR++ (Source -> "RTL-TCP") dan backend ini (sebagai client rtl_tcp
# terpisah) SAMA-SAMA membaca dari situ tanpa rebutan device.
#
# Protokol rtl_tcp (dari proyek osmocom/rtl-sdr):
#   - Saat connect, server kirim 12 byte header: b"RTL0" + tuner_type(4B BE) + gain_count(4B BE)
#   - Setelah itu server terus mengalirkan sampel IQ mentah: byte I, byte Q, I, Q, ... (uint8)
#   - Client BISA kirim command 5 byte (1 byte id + 4 byte BE param), tapi backend ini
#     sengaja TIDAK mengirim command apapun (tidak set freq/sample-rate dari sini),
#     supaya tidak bentrok dengan pengaturan yang sudah dikendalikan SDR++/rigctl.
#     Frekuensi tengah untuk label sumbu-X diambil dari cache hasil endpoint /sdr/*.

RTLTCP_HOST = os.environ.get("RTLTCP_HOST", "192.168.0.148")
RTLTCP_PORT = int(os.environ.get("RTLTCP_PORT", "8073"))

# "Perangkat" semu yang muncul di dropdown /devices yang sudah ada di UI, mewakili
# pilihan "ambil audio langsung dari Web-888 lewat WebSocket" (tanpa kabel virtual).
# Angka negatif ini tidak akan pernah bentrok dengan index device asli dari sounddevice
# (yang selalu >= 0).
WEB888_VIRTUAL_DEVICE_INDEX = -888
SPECTRUM_FFT_SIZE = 4096  # dinaikkan dari 1024: lebih banyak bin = resolusi Hz/bin lebih halus saat di-zoom
SPECTRUM_TARGET_FPS = 20
SPECTRUM_DEFAULT_SAMPLE_RATE_HZ = 2_400_000  # samakan dengan setting source RTL-TCP di SDR++

# Cache frekuensi tengah terakhir yang diketahui (diperbarui oleh endpoint /sdr/frequency)
# CATATAN: nilai ini adalah frekuensi RADIO/RF AKTUAL yang ditune di dongle
# (dipakai sebagai sumbu-tengah spektrum rtl_tcp) -- BUKAN frekuensi HT.
_last_known_freq_lock = threading.Lock()
_last_known_freq_hz = 100_000_000


def _set_last_known_freq(hz: int):
    global _last_known_freq_hz
    with _last_known_freq_lock:
        _last_known_freq_hz = int(hz)


def _get_last_known_freq() -> int:
    with _last_known_freq_lock:
        return int(_last_known_freq_hz)


# ==========================================================
# OFFSET FREKUENSI (HT <-> WEB-888)
# ==========================================================
# Kenapa perlu ini: frekuensi yang dipancarkan HT tidak selalu sama persis
# dengan frekuensi yang harus di-tune di penerima WEB-888 (mis. karena
# kalibrasi/PPM error, IF offset, atau receiver memang sengaja di-tune
# sedikit di luar frekuensi HT). Selisihnya konstan, jadi cukup satu angka
# offset (Hz, boleh negatif) yang ditambahkan ke frekuensi HT untuk
# mendapatkan frekuensi radio aktual:
#
#       frekuensi_radio_aktual = frekuensi_HT + offset_hz
#
# Semua endpoint /sdr/frequency (GET & POST) bekerja di level "frekuensi HT"
# (nilai yang tampil/diinput user di panel Frekuensi), lalu backend inilah
# yang menambah/mengurangi offset saat benar-benar bicara ke WEB-888/SDR++.
_freq_offset_lock = threading.Lock()
_freq_offset_hz = int(os.environ.get("WEB888_FREQ_OFFSET_HZ", "-122880000"))


def _set_freq_offset(hz: int):
    global _freq_offset_hz
    with _freq_offset_lock:
        _freq_offset_hz = int(hz)


def _get_freq_offset() -> int:
    with _freq_offset_lock:
        return int(_freq_offset_hz)


# Frekuensi HT terakhir yang diketahui (nilai "bersih", sebelum ditambah offset).
# Dipakai supaya saat offset diubah, radio bisa langsung di-retune ke frekuensi
# HT yang sama tanpa user perlu mengetik ulang frekuensinya.
_last_known_ht_freq_lock = threading.Lock()
_last_known_ht_freq_hz: Optional[int] = None


def _set_last_known_ht_freq(hz: int):
    global _last_known_ht_freq_hz
    with _last_known_ht_freq_lock:
        _last_known_ht_freq_hz = int(hz)


def _get_last_known_ht_freq() -> Optional[int]:
    with _last_known_ht_freq_lock:
        return _last_known_ht_freq_hz


class RtlTcpSpectrumReader:
    """Client rtl_tcp yang jalan di background thread, hitung FFT terus-menerus,
    dan menyimpan 1 frame spektrum terbaru (dalam dB) untuk diambil lewat HTTP."""

    def __init__(self):
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.connected = False
        self.error: Optional[str] = None

        self.host = RTLTCP_HOST
        self.port = RTLTCP_PORT
        self.sample_rate_hz = SPECTRUM_DEFAULT_SAMPLE_RATE_HZ
        self.fft_size = SPECTRUM_FFT_SIZE

        self.latest_db: Optional[np.ndarray] = None
        self.latest_ts = 0.0

        self._window = np.hanning(self.fft_size).astype(np.float32)

    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "connected": self.connected,
                "error": self.error,
                "host": self.host,
                "port": self.port,
                "sample_rate_hz": self.sample_rate_hz,
                "fft_size": self.fft_size,
            }

    def start(self, host=None, port=None, sample_rate_hz=None):
        with self.lock:
            if self.running:
                return
            if host:
                self.host = host
            if port:
                self.port = int(port)
            if sample_rate_hz:
                self.sample_rate_hz = int(sample_rate_hz)
            self.running = True
            self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        with self.lock:
            self.running = False

    def get_latest(self):
        with self.lock:
            if self.latest_db is None:
                return None
            return {
                "db": self.latest_db.tolist(),
                "timestamp": self.latest_ts,
                "sample_rate_hz": self.sample_rate_hz,
                "fft_size": self.fft_size,
                "center_freq_hz": _get_last_known_freq(),
            }

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            if not self.running:
                raise RuntimeError("dihentikan")
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Koneksi rtl_tcp terputus.")
            buf.extend(chunk)
        return bytes(buf)

    def _run(self):
        while True:
            with self.lock:
                if not self.running:
                    return
                host, port, sr = self.host, self.port, self.sample_rate_hz

            try:
                with socket.create_connection((host, port), timeout=3.0) as sock:
                    sock.settimeout(5.0)
                    header = self._recv_exact(sock, 12)
                    if header[:4] != b"RTL0":
                        raise RuntimeError("Header rtl_tcp tidak dikenali (bukan server rtl_tcp?).")

                    with self.lock:
                        self.connected = True
                        self.error = None

                    bytes_per_frame = int((sr * 2) / SPECTRUM_TARGET_FPS)
                    bytes_per_frame -= bytes_per_frame % 2  # harus genap (pasangan I/Q)
                    bytes_per_frame = max(bytes_per_frame, self.fft_size * 2)

                    while True:
                        with self.lock:
                            if not self.running:
                                return
                        raw = self._recv_exact(sock, bytes_per_frame)

                        # ambil FFT_SIZE sampel terakhir dari frame supaya tetap real-time
                        tail = raw[-(self.fft_size * 2):]
                        iq = np.frombuffer(tail, dtype=np.uint8).astype(np.float32)
                        iq = (iq - 127.5) / 127.5
                        i = iq[0::2]
                        q = iq[1::2]
                        complex_samples = i + 1j * q

                        windowed = complex_samples * self._window
                        spectrum = np.fft.fftshift(np.fft.fft(windowed, n=self.fft_size))
                        mag = np.abs(spectrum) / self.fft_size
                        db = 20.0 * np.log10(mag + 1e-12)

                        with self.lock:
                            self.latest_db = db.astype(np.float32)
                            self.latest_ts = time.time()

            except Exception as e:
                with self.lock:
                    self.connected = False
                    self.error = str(e)
                # tunggu sebentar sebelum coba reconnect, kecuali sudah diminta stop
                for _ in range(20):
                    with self.lock:
                        if not self.running:
                            return
                    time.sleep(0.25)


spectrum_reader = RtlTcpSpectrumReader()

# Client Web-888 (KiwiSDR) -- jalur LANGSUNG lewat jaringan, tanpa SDR++/rtl_tcp/kabel.
web888 = Web888Client()

# Sumber aktif saat ini: "sdrpp" (rigctl + rtl_tcp + device audio lokal, seperti semula)
# atau "web888" (langsung ke Web-888 lewat WebSocket). Dipilih OTOMATIS di /spectrum/start
# berdasarkan hasil deteksi Web888Client.probe() terhadap host:port yang diisi user di
# panel "Spektrum" (field yang sudah ada di UI -- tidak ada field/tombol baru).
_source_lock = threading.Lock()
_active_source = "sdrpp"


def _set_active_source(name: str):
    global _active_source
    with _source_lock:
        _active_source = name


def active_spectrum_source() -> str:
    with _source_lock:
        return _active_source


# ==========================================================
# AUTO FREQUENCY SCANNER — cari titik HT bekerja secara otomatis
# ==========================================================
# Menyisir frekuensi dari AUTO_SCAN_MIN_HZ..AUTO_SCAN_MAX_HZ (default 0–600
# MHz) dengan langkah AUTO_SCAN_STEP_HZ. Di tiap titik, radio benar-benar
# di-tune (lewat Web-888 atau rigctl/SDR++, jalur yang sama dipakai endpoint
# /sdr/frequency), lalu diberi jeda AUTO_SCAN_DWELL_SEC untuk mengukur ada
# tidaknya sinyal RF nyata (S-meter Web-888, atau RMS perangkat audio lokal
# terakhir untuk jalur SDR++/rigctl). Begitu sinyal HT ketemu, scanner
# BERHENTI menyisir dan tetap men-tune radio di frekuensi itu (state
# "locked") -- karena endpoint /sdr/frequency (GET) yang SUDAH di-poll UI
# tiap 500 ms akan langsung melaporkan frekuensi baru ini, slider/label
# frekuensi di halaman Set Radio otomatis "pindah sendiri" TANPA perlu ada
# perubahan apapun di frontend/UI.
#
# Scanner otomatis berhenti sejenak (tidak menggeser-geser frekuensi) kalau:
#   - sedang ada siklus VOX/rekam aktif (pipeline.current_phase != "idle"),
#   - user baru saja set frekuensi manual lewat slider/panel (cooldown),
#   - atau sinyal HT masih/baru saja ada di frekuensi yang terkunci.
# Semua ambang & kecepatan bisa diatur lewat env var, TANPA mengubah kode:
#   YALI_AUTOSCAN_ENABLED, YALI_AUTOSCAN_MIN_HZ, YALI_AUTOSCAN_MAX_HZ,
#   YALI_AUTOSCAN_STEP_HZ, YALI_AUTOSCAN_DWELL_SEC, YALI_AUTOSCAN_RESUME_SEC,
#   YALI_AUTOSCAN_MANUAL_COOLDOWN_SEC.
#
# CATATAN JUJUR: menyisir 0–600 MHz dengan langkah yang terlalu halus akan
# lama (mis. langkah 25 kHz ≈ 24.000 titik). Kalau HT/repeater kamu punya
# spacing channel yang diketahui (mis. 12.5/20/25 kHz di band tertentu),
# set YALI_AUTOSCAN_STEP_HZ sesuai itu supaya pencarian jauh lebih cepat
# daripada menyisir per-Hz.
AUTO_SCAN_ENABLED_DEFAULT = os.environ.get("YALI_AUTOSCAN_ENABLED", "0") == "1"
AUTO_SCAN_MIN_HZ = int(float(os.environ.get("YALI_AUTOSCAN_MIN_HZ", "0")))
AUTO_SCAN_MAX_HZ = int(float(os.environ.get("YALI_AUTOSCAN_MAX_HZ", "600000000")))
AUTO_SCAN_STEP_HZ = int(float(os.environ.get("YALI_AUTOSCAN_STEP_HZ", "25000")))
AUTO_SCAN_DWELL_SEC = float(os.environ.get("YALI_AUTOSCAN_DWELL_SEC", "0.20"))
AUTO_SCAN_RESUME_SEC = float(os.environ.get("YALI_AUTOSCAN_RESUME_SEC", "4.0"))
AUTO_SCAN_MANUAL_COOLDOWN_SEC = float(os.environ.get("YALI_AUTOSCAN_MANUAL_COOLDOWN_SEC", "12.0"))

# Cooldown: dipakai supaya scanner tidak langsung "menggeser lagi" frekuensi
# begitu user baru saja set frekuensi manual lewat UI yang sudah ada
# (slider/preset/input manual -> semua lewat POST /sdr/frequency).
_manual_tune_lock = threading.Lock()
_manual_tune_cooldown_until = 0.0


def _set_manual_tune_cooldown(seconds: float):
    global _manual_tune_cooldown_until
    with _manual_tune_lock:
        _manual_tune_cooldown_until = time.time() + max(seconds, 0.0)


def _get_manual_tune_cooldown_until() -> float:
    with _manual_tune_lock:
        return _manual_tune_cooldown_until


class AutoFreqScanner:
    """Background scanner: cari titik frekuensi HT aktif di rentang
    AUTO_SCAN_MIN_HZ..AUTO_SCAN_MAX_HZ, lalu tune radio ke sana otomatis."""

    def __init__(self):
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.running = False   # thread background hidup (selalu True setelah launch())
        self.enabled = AUTO_SCAN_ENABLED_DEFAULT  # sedang aktif menyisir atau tidak

        self.min_hz = AUTO_SCAN_MIN_HZ
        self.max_hz = AUTO_SCAN_MAX_HZ
        self.step_hz = max(AUTO_SCAN_STEP_HZ, 1)
        self.dwell_sec = AUTO_SCAN_DWELL_SEC
        self.resume_after_sec = AUTO_SCAN_RESUME_SEC

        self.current_scan_hz = self.min_hz
        self.locked_hz: Optional[int] = None
        self.last_signal_ts = 0.0
        self.state = "idle"  # idle | scanning | locked
        self.error: Optional[str] = None

    def status(self) -> dict:
        with self.lock:
            return {
                "enabled": self.enabled,
                "state": self.state,
                "current_hz": self.current_scan_hz,
                "locked_hz": self.locked_hz,
                "min_hz": self.min_hz,
                "max_hz": self.max_hz,
                "step_hz": self.step_hz,
                "dwell_sec": self.dwell_sec,
                "resume_after_sec": self.resume_after_sec,
                "error": self.error,
            }

    def configure(self, **kwargs):
        with self.lock:
            if kwargs.get("min_hz") is not None:
                self.min_hz = int(kwargs["min_hz"])
            if kwargs.get("max_hz") is not None:
                self.max_hz = int(kwargs["max_hz"])
            if kwargs.get("step_hz") is not None:
                self.step_hz = max(int(kwargs["step_hz"]), 1)
            if kwargs.get("dwell_sec") is not None:
                self.dwell_sec = max(float(kwargs["dwell_sec"]), 0.02)
            if kwargs.get("resume_after_sec") is not None:
                self.resume_after_sec = max(float(kwargs["resume_after_sec"]), 0.0)
            # kalau rentang berubah, pastikan titik scan sekarang tetap valid
            if self.current_scan_hz < self.min_hz or self.current_scan_hz > self.max_hz:
                self.current_scan_hz = self.min_hz

    def launch(self):
        """Nyalakan thread background SEKALI saat startup aplikasi. Status
        aktif/nonaktif (enabled) diatur terpisah lewat start()/stop()."""
        with self.lock:
            if self.thread is not None:
                return
            self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def start(self):
        with self.lock:
            self.enabled = True
            self.error = None

    def stop(self):
        with self.lock:
            self.enabled = False
            self.state = "idle"

    # ---------- tuning & deteksi sinyal ----------
    def _tune(self, ht_hz: int):
        offset = _get_freq_offset()
        radio_hz = int(ht_hz) + offset
        if active_spectrum_source() == "web888":
            web888.set_frequency(radio_hz)
        else:
            rigctl_command(f"F {radio_hz}")
        _set_last_known_ht_freq(int(ht_hz))
        _set_last_known_freq(radio_hz)

    def _signal_present(self) -> bool:
        """True kalau ada sinyal RF nyata di frekuensi yang SEDANG di-tune."""
        if active_spectrum_source() == "web888":
            if not web888.connected_snd:
                return False
            _, _, _, squelch_open = web888.get_meter_level()
            return bool(squelch_open)

        # Jalur SDR++/rigctl (audio lewat perangkat lokal/kabel virtual):
        # tidak ada S-meter lewat rigctl, jadi pakai RMS singkat dari
        # perangkat audio TERAKHIR yang dipakai user di dropdown /record-radio.
        dev_index = pipeline.last_device_index
        if dev_index is None:
            return False
        try:
            n_frames = max(int(self.dwell_sec * RADIO_SAMPLE_RATE), 256)
            rec = sd.rec(n_frames, samplerate=RADIO_SAMPLE_RATE, channels=1,
                          dtype="float32", device=dev_index)
            sd.wait()
            if rec.size == 0:
                return False
            rms = float(np.sqrt(np.mean(rec[:, 0] ** 2)))
            return rms > RMS_THRESHOLD
        except Exception as e:
            with self.lock:
                self.error = f"Gagal ukur level sinyal: {e}"
            return False

    def _run(self):
        while True:
            with self.lock:
                if not self.running:
                    return
                enabled = self.enabled

            if not enabled:
                with self.lock:
                    self.state = "idle"
                time.sleep(0.5)
                continue

            # Jangan ganggu siklus VOX/rekam yang sedang berjalan.
            if getattr(pipeline, "current_phase", "idle") != "idle":
                time.sleep(0.3)
                continue

            # Jangan ganggu user yang baru saja set frekuensi manual di UI.
            if time.time() < _get_manual_tune_cooldown_until():
                time.sleep(0.3)
                continue

            try:
                if active_spectrum_source() == "web888" and not web888.connected_snd:
                    with self.lock:
                        self.state = "idle"
                        self.error = "Web-888 belum tersambung (sambungkan lewat panel Spektrum)."
                    time.sleep(1.0)
                    continue

                with self.lock:
                    locked = self.locked_hz

                if locked is not None:
                    if self._signal_present():
                        with self.lock:
                            self.last_signal_ts = time.time()
                            self.state = "locked"
                            self.error = None
                        time.sleep(self.dwell_sec)
                        continue
                    with self.lock:
                        resume_after = self.resume_after_sec
                    if time.time() - self.last_signal_ts < resume_after:
                        time.sleep(self.dwell_sec)
                        continue
                    # Sinyal sudah hilang cukup lama -> lanjutkan menyisir lagi.
                    with self.lock:
                        self.locked_hz = None

                with self.lock:
                    hz = self.current_scan_hz
                    step = self.step_hz
                    lo, hi = self.min_hz, self.max_hz
                    self.state = "scanning"

                self._tune(hz)
                time.sleep(self.dwell_sec)

                if self._signal_present():
                    with self.lock:
                        self.locked_hz = hz
                        self.last_signal_ts = time.time()
                        self.state = "locked"
                        self.error = None
                    print(f"[AUTOSCAN] Titik HT ditemukan di {hz/1e6:.4f} MHz, radio dipindah ke sana.",
                          file=sys.stderr)
                else:
                    nxt = hz + step
                    if nxt > hi:
                        nxt = lo
                    with self.lock:
                        self.current_scan_hz = nxt

            except (ConnectionRefusedError, OSError) as e:
                with self.lock:
                    self.error = f"Tidak bisa terhubung ke radio: {e}"
                time.sleep(1.0)
            except Exception as e:
                with self.lock:
                    self.error = str(e)
                time.sleep(1.0)


auto_scanner = AutoFreqScanner()


@app.route("/spectrum/status", methods=["GET"])
def spectrum_status():
    src = active_spectrum_source()
    if src == "web888":
        return jsonify({"ok": True, "source": "web888", **web888.status()})
    return jsonify({"ok": True, "source": "sdrpp", **spectrum_reader.status()})


@app.route("/spectrum/zoom", methods=["POST"])
def spectrum_zoom():
    """Minta span waterfall baru (Hz) ke sumber spektrum yang aktif.

    Untuk sumber Web-888/KiwiSDR ini memicu ZOOM ASLI di sisi server
    (request ulang FFT dengan span lebih sempit -> resolusi Hz-per-bin
    sungguhan naik), bukan cuma crop+stretch di browser.

    Untuk sumber rtl_tcp lokal ("sdrpp") belum ada mekanisme retune span
    live yang setara, jadi endpoint ini hanya menjawab ok=True dengan
    supported=False supaya frontend tahu harus tetap memakai crop
    client-side seperti sebelumnya.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        wf_span_hz = data.get("wf_span_hz")
        if wf_span_hz is None:
            return jsonify({"ok": False, "error": "wf_span_hz wajib diisi."}), 400

        src = active_spectrum_source()
        if src == "web888":
            web888.set_wf_span_hz(wf_span_hz)
            return jsonify({"ok": True, "source": "web888", "supported": True, **web888.status()})

        return jsonify({"ok": True, "source": "sdrpp", "supported": False, **spectrum_reader.status()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/spectrum/start", methods=["POST"])
def spectrum_start():
    try:
        data = request.get_json(force=True, silent=True) or {}
        host = data.get("host") or RTLTCP_HOST
        port = int(data.get("port") or RTLTCP_PORT)
        sample_rate_hz = data.get("sample_rate_hz")

        # Deteksi otomatis: host:port ini Web-888 (KiwiSDR/WebSocket) atau rtl_tcp biasa?
        is_web888 = Web888Client.probe(host, port)

        if is_web888:
            spectrum_reader.stop()
            web888.stop()
            # wf_span_hz dikirim LANGSUNG ke start() (bukan di-set sesudahnya
            # seperti sebelumnya) supaya tidak ada race dengan thread W/F yang
            # bisa keburu connect & mengirim command zoom/center pakai nilai
            # lama sebelum sempat di-update. Kalau tidak dikirim di request,
            # start() tetap pakai default/ENV var yang sudah ada di client.
            ht_freq_hz = _get_last_known_ht_freq()
            radio_freq_hz = (
                int(ht_freq_hz + _get_freq_offset())
                if ht_freq_hz is not None
                else _get_last_known_freq()
            )
            web888.start(
                host=host,
                port=port,
                password=data.get("password", ""),
                wf_span_hz=data.get("wf_span_hz"),
                freq_hz=radio_freq_hz,
                mode=getattr(web888, "mode", "nbfm"),
                bandwidth_hz=getattr(web888, "bandwidth_hz", 12500),
            )
            _set_last_known_freq(radio_freq_hz)
            _set_active_source("web888")
            print(f"[SPECTRUM] Web-888 terdeteksi di {host}:{port} — jalur langsung dipakai.", file=sys.stderr)
            return jsonify({"ok": True, "source": "web888", **web888.status()})

        web888.stop()
        spectrum_reader.start(host=host, port=port, sample_rate_hz=sample_rate_hz)
        _set_active_source("sdrpp")
        return jsonify({"ok": True, "source": "sdrpp", **spectrum_reader.status()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/spectrum/stop", methods=["POST"])
def spectrum_stop():
    spectrum_reader.stop()
    web888.stop()
    return jsonify({"ok": True})


@app.route("/spectrum", methods=["GET"])
def spectrum_latest():
    src = active_spectrum_source()
    frame = web888.get_latest() if src == "web888" else spectrum_reader.get_latest()
    if frame is None:
        return jsonify({"ok": False, "error": "Belum ada data spektrum (belum tersambung?)."}), 503
    return jsonify({"ok": True, "source": src, **frame})


@app.route("/web888/audio-chunk", methods=["GET"])
def web888_audio_chunk():
    """
    Audio HT LANGSUNG (untuk didengarkan lewat browser) selagi melihat
    frekuensi/waterfall di halaman Set Radio -- terpisah dari alur
    /record-radio (yang dipakai untuk transkrip Whisper). Endpoint ini
    HANYA relevan kalau sumber aktif adalah Web-888 (untuk SDR++/rigctl,
    audio sudah keluar lewat speaker PC via SDR++ sendiri, jadi browser
    tidak perlu memutar apa pun).

    Dipanggil berulang (polling) oleh frontend; setiap panggilan menguras
    (drain) buffer audio yang terkumpul sejak panggilan terakhir, dikirim
    sebagai PCM16 mono base64 supaya ringan lewat JSON.

    CATATAN: dulu endpoint ini menguras pop_audio() -- buffer yang SAMA
    dipakai /record-radio saat mode "Dengarkan" (Whisper) aktif, dan buffer
    itu DIGERBANG squelch (S-meter). Efeknya: kalau kalibrasi squelch
    meleset sedikit saja, user tidak dengar suaranya sendiri SAMA SEKALI
    walau HT sudah pas di frekuensi yang benar -- padahal tujuan endpoint
    ini justru supaya user bisa menitik-tengahkan frekuensi pakai telinga.
    Sekarang dipakai pop_monitor_audio(): buffer TERPISAH yang SELALU
    terisi dari setiap frame SND, TIDAK digerbang squelch sama sekali, jadi
    endpoint ini tidak lagi berebut buffer dengan /record-radio maupun
    kena pengaruh kalibrasi squelch.
    """
    try:
        if active_spectrum_source() != "web888" or not web888.connected_snd:
            return jsonify({"ok": True, "has_audio": False})

        sample_rate = int(web888.get_audio_sample_rate() or KIWI_AUDIO_RATE)
        # Batasi tiap respons sekitar 350 ms agar browser tidak menerima
        # backlog besar dan monitor tetap mendekati real-time.
        chunk = web888.pop_monitor_audio(max_samples=max(1, int(sample_rate * 0.35)))
        if chunk.size == 0:
            return jsonify({"ok": True, "has_audio": False, "sample_rate": sample_rate})

        pcm16 = np.clip(chunk, -1.0, 1.0)
        pcm16 = (pcm16 * 32767.0).astype("<i2")
        b64 = base64.b64encode(pcm16.tobytes()).decode("ascii")

        return jsonify(
            {
                "ok": True,
                "has_audio": True,
                "sample_rate": sample_rate,
                "rms": float(np.sqrt(np.mean(chunk ** 2) + 1e-12)),
                "pcm16_base64": b64,
            }
        )
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500



# SDR++ punya modul bawaan "Rigctl Server" (aktifkan lewat Module Manager di
# SDR++, defaultnya listen di 127.0.0.1:4532). Modul ini menerima perintah
# teks sederhana ala Hamlib:
#   F <freq_hz>          -> set frekuensi
#   f                     -> baca frekuensi saat ini
#   M <mode> <passband>   -> set mode + bandwidth (passband dalam Hz)
#   m                     -> baca mode + bandwidth saat ini (2 baris: mode, passband)
#
# Logika di bawah ini adalah port langsung dari sdrpp_gui_controller.py
# (kontroler Tkinter yang sudah terbukti jalan), hanya dibungkus jadi
# endpoint HTTP karena browser tidak bisa membuka koneksi TCP mentah
# ke rigctl secara langsung seperti aplikasi desktop Python.
RIGCTL_HOST = os.environ.get("RIGCTL_HOST", "192.168.0.148")
RIGCTL_PORT = int(os.environ.get("RIGCTL_PORT", "8073"))


def rigctl_command(command: str, host: str = RIGCTL_HOST, port: int = RIGCTL_PORT, timeout: float = 1.5) -> str:
    """Kirim satu perintah RigCTL ke SDR++ dan kembalikan responsnya (bisa multi-baris)."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((command.strip() + "\n").encode("utf-8"))
        chunks = []
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
                if b"\n" in data:
                    break
            except socket.timeout:
                break
    return b"".join(chunks).decode("utf-8", errors="ignore").strip()


def _rigctl_connection_error_json(e: Exception):
    return {
        "ok": False,
        "error": (
            f"Tidak bisa terhubung ke RigCTL Server SDR++ di {RIGCTL_HOST}:{RIGCTL_PORT}. "
            f"Pastikan modul 'Rigctl Server' sudah ditambahkan & di-Start di Module Manager SDR++. "
            f"Detail: {e}"
        ),
    }


@app.route("/sdr/frequency", methods=["GET"])
def sdr_get_frequency():
    """Baca frekuensi saat ini (dari Web-888 langsung, atau dari SDR++ via rigctl).

    "freq_hz" di response = frekuensi HT (radio_freq_hz dikurangi offset),
    supaya panel Frekuensi di UI selalu menampilkan frekuensi HT, bukan
    frekuensi radio aktual yang sudah dikoreksi offset.
    """
    offset_hz = _get_freq_offset()

    if active_spectrum_source() == "web888":
        radio_freq_hz = int(web888.freq_hz)
        ht_freq_hz = radio_freq_hz - offset_hz
        _set_last_known_ht_freq(ht_freq_hz)
        # PERBAIKAN: cache frekuensi radio global ini sebelumnya HANYA
        # diperbarui lewat jalur SDR++/rigctl, tidak lewat Web-888 --
        # akibatnya kalau spektrum/waterfall perlu fallback ke cache ini
        # (mis. saat /spectrum/start dipanggil ulang sebelum ht_freq_hz
        # pernah di-set), nilainya bisa basi dan tidak sesuai frekuensi
        # HT/Web-888 yang sesungguhnya sedang aktif. Sinkronkan juga di sini.
        _set_last_known_freq(radio_freq_hz)
        return jsonify({"ok": True, "freq_hz": ht_freq_hz, "radio_freq_hz": radio_freq_hz, "offset_hz": offset_hz})
    try:
        response = rigctl_command("f")
        if not response:
            return jsonify({"ok": False, "error": "Tidak ada respons dari SDR++ Rigctl Server."}), 200
        for line in (l.strip() for l in response.splitlines() if l.strip()):
            try:
                radio_freq_hz = int(float(line))
                ht_freq_hz = radio_freq_hz - offset_hz
                _set_last_known_freq(radio_freq_hz)
                _set_last_known_ht_freq(ht_freq_hz)
                return jsonify({"ok": True, "freq_hz": ht_freq_hz, "radio_freq_hz": radio_freq_hz, "offset_hz": offset_hz})
            except ValueError:
                continue
        return jsonify({"ok": False, "error": f"Respons frekuensi tidak valid: {response!r}"}), 200
    except (ConnectionRefusedError, OSError) as e:
        return jsonify(_rigctl_connection_error_json(e)), 200
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/sdr/frequency", methods=["POST"])
def sdr_set_frequency():
    """Body JSON: { "freq_hz": 155700000 }

    "freq_hz" yang dikirim dari UI dianggap sebagai frekuensi HT.
    Backend menambahkan offset (lihat /sdr/frequency-offset) sebelum
    benar-benar mengirim perintah tuning ke Web-888/SDR++.
    """
    try:
        data = request.get_json(force=True) or {}
        freq_hz = data.get("freq_hz")
        if freq_hz is None:
            return jsonify({"ok": False, "error": "Field 'freq_hz' wajib diisi."}), 400
        ht_freq_hz = int(float(freq_hz))
        offset_hz = _get_freq_offset()
        radio_freq_hz = ht_freq_hz + offset_hz
        _set_last_known_ht_freq(ht_freq_hz)

        # User baru saja set frekuensi manual lewat UI (slider/preset/input
        # manual/klik spektrum -- semuanya lewat endpoint ini) -> beri jeda
        # ke AutoFreqScanner supaya tidak langsung menggeser frekuensi lagi.
        _set_manual_tune_cooldown(AUTO_SCAN_MANUAL_COOLDOWN_SEC)

        if active_spectrum_source() == "web888":
            web888.set_frequency(radio_freq_hz)
            # PERBAIKAN: sebelumnya cache frekuensi radio global (dipakai
            # sebagai fallback center frequency waterfall/spektrum) hanya
            # disinkronkan di jalur SDR++/rigctl -- tidak di jalur Web-888.
            # Disamakan di sini supaya frekuensi yang terdeteksi di waterfall
            # selalu mengikuti frekuensi HT/Web-888 yang baru saja di-set,
            # apa pun sumber spektrum yang sedang aktif.
            _set_last_known_freq(radio_freq_hz)
            return jsonify({
                "ok": True,
                "freq_hz": ht_freq_hz,
                "radio_freq_hz": radio_freq_hz,
                "offset_hz": offset_hz,
            })

        resp = rigctl_command(f"F {radio_freq_hz}")
        if resp and "RPRT -" in resp:
            return jsonify({"ok": False, "error": f"Gagal set frekuensi (respons: {resp!r})."}), 200

        _set_last_known_freq(radio_freq_hz)
        return jsonify({
            "ok": True,
            "freq_hz": ht_freq_hz,
            "radio_freq_hz": radio_freq_hz,
            "offset_hz": offset_hz,
            "response": resp,
        })
    except (ConnectionRefusedError, OSError) as e:
        return jsonify(_rigctl_connection_error_json(e)), 200
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/sdr/frequency-offset", methods=["GET"])
def sdr_get_frequency_offset():
    """Baca offset frekuensi (Hz) yang sedang dipakai: radio = HT + offset."""
    try:
        return jsonify({"ok": True, "offset_hz": _get_freq_offset()})
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/sdr/frequency-offset", methods=["POST"])
def sdr_set_frequency_offset():
    """Body JSON: { "offset_hz": -1500 }

    Mengubah offset yang dipakai untuk mengoreksi selisih antara frekuensi
    HT dan frekuensi yang benar-benar harus di-tune di Web-888/SDR++.
    Supaya radio langsung ikut pindah sesuai offset baru (tanpa user harus
    set ulang frekuensi HT-nya), begitu offset berubah kita hitung ulang
    frekuensi radio dari frekuensi HT TERAKHIR yang diketahui lalu kirim
    ulang perintah tuning-nya.
    """
    try:
        data = request.get_json(force=True) or {}
        offset_hz = data.get("offset_hz")
        if offset_hz is None:
            return jsonify({"ok": False, "error": "Field 'offset_hz' wajib diisi."}), 400
        offset_hz = int(float(offset_hz))
        _set_freq_offset(offset_hz)

        # Kalau sudah pernah ada frekuensi HT yang di-set sebelumnya, langsung
        # retune radio ke frekuensi HT yang SAMA memakai offset yang BARU --
        # supaya operator tidak perlu ketik ulang frekuensi HT-nya setiap kali
        # kalibrasi offset diubah.
        ht_freq_hz = _get_last_known_ht_freq()
        radio_freq_hz = None
        retune_error = None
        if ht_freq_hz is not None:
            radio_freq_hz = ht_freq_hz + offset_hz
            try:
                if active_spectrum_source() == "web888":
                    web888.set_frequency(radio_freq_hz)
                    # PERBAIKAN: sinkronkan juga cache frekuensi radio global
                    # di jalur Web-888 (sebelumnya cuma jalur rigctl di bawah
                    # yang melakukan ini), supaya deteksi frekuensi waterfall
                    # tetap konsisten setelah offset HT<->Web-888 diubah.
                    _set_last_known_freq(radio_freq_hz)
                else:
                    resp = rigctl_command(f"F {radio_freq_hz}")
                    if resp and "RPRT -" in resp:
                        retune_error = f"Gagal retune (respons: {resp!r})."
                    else:
                        _set_last_known_freq(radio_freq_hz)
            except (ConnectionRefusedError, OSError) as e:
                # Offset tetap tersimpan walau retune gagal (mis. SDR++/Web-888
                # belum tersambung) -- akan otomatis kepakai saat user set
                # frekuensi berikutnya.
                retune_error = f"Offset tersimpan, tapi retune gagal: {e}"

        result = {
            "ok": True,
            "offset_hz": offset_hz,
            "ht_freq_hz": ht_freq_hz,
            "radio_freq_hz": radio_freq_hz,
        }
        if retune_error:
            result["retune_warning"] = retune_error
        return jsonify(result)
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/sdr/mode", methods=["GET"])
def sdr_get_mode():
    """Baca mode + bandwidth saat ini (dari Web-888 langsung, atau dari SDR++ via rigctl)."""
    if active_spectrum_source() == "web888":
        return jsonify({"ok": True, "mode": web888.mode.upper(), "bandwidth_hz": web888.bandwidth_hz})
    try:
        response = rigctl_command("m")
        if not response:
            return jsonify({"ok": False, "error": "Tidak ada respons saat membaca mode/bandwidth."}), 200
        lines = [l.strip() for l in response.splitlines() if l.strip()]
        if len(lines) < 2:
            return jsonify({"ok": False, "error": f"Respons mode/bandwidth tidak lengkap: {response!r}"}), 200
        mode = lines[0]
        try:
            bandwidth_hz = int(float(lines[1]))
        except ValueError:
            return jsonify({"ok": False, "error": f"Passband tidak valid: {lines[1]!r}"}), 200
        return jsonify({"ok": True, "mode": mode, "bandwidth_hz": bandwidth_hz})
    except (ConnectionRefusedError, OSError) as e:
        return jsonify(_rigctl_connection_error_json(e)), 200
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/sdr/mode", methods=["POST"])
def sdr_set_mode():
    """Body JSON: { "mode": "FM", "bandwidth_hz": 12500 }"""
    try:
        data = request.get_json(force=True) or {}
        mode = str(data.get("mode", "")).strip().upper()
        bandwidth_hz = data.get("bandwidth_hz")
        if not mode:
            return jsonify({"ok": False, "error": "Field 'mode' wajib diisi."}), 400
        passband = int(float(bandwidth_hz)) if bandwidth_hz is not None else 0

        if active_spectrum_source() == "web888":
            web888.set_mode(mode, passband)
            return jsonify({"ok": True, "mode": mode, "bandwidth_hz": passband})

        resp = rigctl_command(f"M {mode} {passband}")
        if resp and "RPRT -" in resp:
            return jsonify({"ok": False, "error": f"Gagal set mode/bandwidth (respons: {resp!r})."}), 200

        return jsonify({"ok": True, "mode": mode, "bandwidth_hz": passband, "response": resp})
    except (ConnectionRefusedError, OSError) as e:
        return jsonify(_rigctl_connection_error_json(e)), 200
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/scan/status", methods=["GET"])
def scan_status():
    """Status pencarian frekuensi HT otomatis (0–600 MHz secara default)."""
    try:
        return jsonify({"ok": True, **auto_scanner.status()})
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/scan/start", methods=["POST"])
def scan_start():
    """Aktifkan pencarian otomatis (berjalan terus di background sampai
    ketemu titik HT bekerja, lalu tetap terkunci di sana)."""
    try:
        auto_scanner.start()
        return jsonify({"ok": True, **auto_scanner.status()})
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/scan/stop", methods=["POST"])
def scan_stop():
    """Nonaktifkan sementara pencarian otomatis (frekuensi tetap di posisi
    terakhir; user bisa lanjut atur manual lewat panel Frekuensi)."""
    try:
        auto_scanner.stop()
        return jsonify({"ok": True, **auto_scanner.status()})
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/scan/config", methods=["POST"])
def scan_config():
    """Body JSON opsional: min_hz, max_hz, step_hz, dwell_sec, resume_after_sec."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        auto_scanner.configure(
            min_hz=data.get("min_hz"),
            max_hz=data.get("max_hz"),
            step_hz=data.get("step_hz"),
            dwell_sec=data.get("dwell_sec"),
            resume_after_sec=data.get("resume_after_sec"),
        )
        return jsonify({"ok": True, **auto_scanner.status()})
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/rms", methods=["GET"])
def get_rms():
    """
    CATATAN: sebelumnya endpoint ini SELALU membaca pipeline.current_rms,
    yang HANYA ter-update selagi record_radio_rms()/record_radio_web888()
    berjalan (yaitu selama loop blocking "Dengarkan"/Whisper aktif). Akibatnya
    kalau user cuma ada di halaman Set Radio (lihat waterfall, bicara di HT,
    belum pencet "Dengarkan"), meteran RMS di UI diam terus -- persis keluhan
    "RMS tidak kebaca jelas". Untuk sumber Web-888, sekarang dipakai
    web888.get_meter_level(): level berbasis S-meter ASLI yang di-update
    TERUS-MENERUS oleh thread SND di background (tidak butuh "Dengarkan"
    aktif), lalu dipetakan ke skala numerik yang SAMA persis dengan yang
    sudah dipakai meteran di frontend (meterFill: (rms/1.2e-4)*100%),
    supaya TIDAK PERLU ubah UI/script.js sama sekali.
    """
    try:
        if active_spectrum_source() == "web888" and web888.connected_snd:
            level, threshold_level, smeter_dbm, squelch_open = web888.get_meter_level()
            METER_DISPLAY_SCALE = 1.2e-4  # skala yang sama dipakai meterFill di script.js
            return jsonify(
                {
                    "ok": True,
                    "rms": level * METER_DISPLAY_SCALE,
                    "threshold": threshold_level * METER_DISPLAY_SCALE,
                    "phase": str(getattr(pipeline, "current_phase", "idle")),
                    "label": str(getattr(pipeline, "current_label", "Siap")),
                    "smeter_dbm": smeter_dbm,
                    "squelch_open": squelch_open,
                }
            )

        return jsonify(
            {
                "ok": True,
                "rms": float(pipeline.current_rms),
                "threshold": float(pipeline.current_threshold),
                "phase": str(getattr(pipeline, "current_phase", "idle")),
                "label": str(getattr(pipeline, "current_label", "Siap")),
            }
        )
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500


@app.route("/record-radio/stop", methods=["POST"])
def stop_record_radio():
    """
    Hentikan SEGERA siklus rekam VOX yang sedang berjalan (dicek tiap blok
    audio di dalam record_radio_rms()/record_radio_web888(), jadi berhenti
    dalam hitungan puluhan-ratusan ms, bukan menunggu batas 20 detik).
    Aman dipanggil kapan saja walau tidak ada rekaman aktif.
    """
    pipeline.cancel_event.set()
    return jsonify({
        "ok": True,
        "phase": str(getattr(pipeline, "current_phase", "idle")),
        "label": str(getattr(pipeline, "current_label", "Siap")),
    })


@app.route("/record-radio", methods=["POST"])
def record_radio():
    """
    Jalankan satu siklus PTT/VOX, bersihkan audio, transkripsikan bahasa
    Papua/Yali, lalu terjemahkan ke Indonesia. Hanya satu siklus diizinkan
    pada satu waktu supaya device audio dan model GPU tidak saling berebut.
    """
    if not pipeline.record_lock.acquire(blocking=False):
        return jsonify(
            {
                "ok": False,
                "busy": True,
                "error": "Radio sedang dipakai oleh proses rekam/terjemahan sebelumnya.",
            }
        ), 200

    try:
        pipeline.cancel_event.clear()
        data = request.get_json(force=True, silent=False) or {}

        # Pastikan model Whisper/MT yang dipakai sesuai bahasa Papua yang
        # sedang dipilih user di dropdown (ambai/biak). Kalau gagal (mis.
        # folder model tidak ditemukan), lanjutkan pakai bahasa yang
        # sebelumnya aktif -- tetap dicatat di console lewat set_language().
        lang_result = pipeline.set_language(data.get("lang", ""))
        if not lang_result.get("ok"):
            print(
                f"[API] /record-radio: tetap memakai bahasa '{pipeline.current_lang}' "
                f"karena gagal ganti -> {lang_result.get('error')}",
                file=sys.stderr,
            )

        thr = max(float(data.get("rms_threshold", RMS_THRESHOLD)), 1e-9)
        max_sec = max(float(data.get("max_sec", LISTEN_MAX_SECONDS)), 1.0)
        # PERBAIKAN: "Rekam & Simpan Audio" hanya boleh merekam input suara
        # dan menyimpannya sebagai file rekaman -- TANPA masuk ke Whisper
        # ataupun diterjemahkan. "Rekam & Translate Audio" (default, seperti
        # semula) tetap merekam + simpan + transkrip + terjemahkan sekaligus.
        skip_translate = bool(data.get("skip_translate", False))

        raw_dev_index = data.get("device_index")
        try:
            dev_index = int(raw_dev_index)
        except (TypeError, ValueError):
            dev_index = None

        want_web888_audio = (dev_index == WEB888_VIRTUAL_DEVICE_INDEX) or (
            dev_index is None and active_spectrum_source() == "web888"
        )
        if dev_index is not None and dev_index != WEB888_VIRTUAL_DEVICE_INDEX:
            pipeline.last_device_index = dev_index

        pipeline.current_phase = "listening"
        pipeline.current_label = "Menunggu sinyal PTT/VOX dari radio…"

        if want_web888_audio:
            if not web888.connected_snd:
                return jsonify(
                    {
                        "ok": False,
                        "error": (
                            "Web-888 belum tersambung. Sambungkan lewat panel "
                            "Spektrum, lalu tunggu status audio siap."
                        ),
                    }
                ), 200
            print(f"[API] /record-radio via Web-888: thr={thr}, max_sec={max_sec}", file=sys.stderr)
            raw_segments, sr = pipeline.record_radio_web888(
                web888, threshold=thr, max_sec=max_sec
            )
        else:
            if dev_index is None:
                return jsonify(
                    {"ok": False, "error": "Pilih perangkat input audio terlebih dahulu."}
                ), 200
            print(
                f"[API] /record-radio via input lokal: device={dev_index}, thr={thr}, max_sec={max_sec}",
                file=sys.stderr,
            )
            raw_segments, sr = pipeline.record_radio_rms(
                device_index=dev_index,
                threshold=thr,
                blocksize=RADIO_BLOCKSIZE,
                sample_rate=RADIO_SAMPLE_RATE,
                max_sec=max_sec,
            )

        if not raw_segments:
            cancelled = pipeline.cancel_event.is_set()
            return jsonify(
                {
                    "ok": False,
                    "cancelled": cancelled,
                    "error": (
                        "Proses mendengarkan dihentikan."
                        if cancelled
                        else "Tidak ada suara PTT yang melewati ambang VOX/squelch."
                    ),
                }
            ), 200

        # PERBAIKAN: raw_segments berisi SATU audio per ucapan (satu siklus
        # tekan-lepas PTT dalam sesi ini) -- lihat record_radio_rms()/
        # record_radio_web888(). Normalisasi bentuknya dulu sebelum diproses.
        norm_segments: List[np.ndarray] = []
        for seg in raw_segments:
            seg = np.asarray(seg, dtype=np.float32)
            if seg.ndim > 1:
                seg = seg[:, 0]
            seg = seg.reshape(-1)
            if seg.size:
                norm_segments.append(seg)

        if not norm_segments:
            return jsonify({"ok": False, "error": "Audio kosong setelah proses cleaning."}), 200

        pipeline.current_phase = "processing"
        pipeline.current_label = "Membersihkan audio radio (reduksi noise)…"
        print(f"[API] Cleaning {len(norm_segments)} ucapan audio radio…", file=sys.stderr)

        # PERBAIKAN: sebelumnya file WAV SELALU ditulis ke RECORDINGS_DIR di
        # sini, tidak peduli tombol mana yang dipakai -- jadi "Rekam &
        # Translate Audio" pun ikut menyimpan berkas otomatis ke lokal.
        # Sekarang penyimpanan otomatis ke disk HANYA terjadi saat
        # skip_translate=True (tombol "Rekam & Simpan Audio"); alur
        # translate biasa tidak lagi menyimpan berkas otomatis.
        saved_path = None
        if skip_translate:
            # "Rekam & Simpan Audio": sambung semua ucapan (bisa lebih dari
            # satu siklus PTT) jadi SATU file WAV utuh -- TANPA masuk ke
            # Whisper ataupun diterjemahkan.
            raw_combined = concat_audio_segments(norm_segments, int(sr), gap_sec=0.4)
            audio_clean = clean_for_whisper(raw_combined, int(sr))
            if audio_clean.size == 0:
                return jsonify({"ok": False, "error": "Audio kosong setelah proses cleaning."}), 200

            if GAIN_LINEAR != 1.0:
                audio_clean = audio_clean * GAIN_LINEAR
            peak = float(np.max(np.abs(audio_clean))) if audio_clean.size else 0.0
            if peak > 1.0:
                audio_clean = audio_clean / peak * 0.99
            audio_clean = np.nan_to_num(
                audio_clean, nan=0.0, posinf=0.0, neginf=0.0
            ).astype(np.float32)

            if float(np.sqrt(np.mean(audio_clean * audio_clean) + 1e-12)) < 1e-6:
                return jsonify(
                    {"ok": False, "error": "Audio terlalu pelan setelah reduksi noise."}
                ), 200

            pipeline.last_audio_clean = audio_clean.copy()
            pipeline.last_audio_sr = int(sr)
            pipeline.last_audio_updated_at = time.time()

            duration = audio_clean.size / float(sr)
            print(
                f"[API] Audio siap: {duration:.2f} s @ {sr} Hz ({len(norm_segments)} ucapan)",
                file=sys.stderr,
            )

            pipeline.current_label = "Menyimpan berkas audio rekaman radio…"
            try:
                stamp_date = time.strftime("%Y%m%d")
                stamp_time = time.strftime("%H%M%S")
                rec_lang = (pipeline.current_lang or "ambai").strip().lower()
                seq = _next_recording_seq(rec_lang)
                saved_path = RECORDINGS_DIR / f"radio_{stamp_date}_{stamp_time}_{rec_lang}_{seq}.wav"
                pcm16_save = (
                    np.clip(audio_clean, -1.0, 1.0) * 32767.0
                ).astype(np.int16)
                sf.write(str(saved_path), pcm16_save, int(sr), subtype="PCM_16")
                pipeline.last_saved_path = str(saved_path)
            except Exception as exc:
                print(f"[SAVE ERROR] {exc}", file=sys.stderr)

            # "Rekam & Simpan Audio": input suara sudah masuk file rekaman di
            # atas -- berhenti di sini, JANGAN jalankan Whisper/terjemahan.
            print("[API] skip_translate=True -> lewati Whisper & terjemahan (rekam & simpan saja).", file=sys.stderr)
            return jsonify(
                {
                    "ok": True,
                    "skip_translate": True,
                    "text_papua": "",
                    "text_indonesia": "",
                    "duration_sec": duration,
                    "saved_file": str(saved_path) if saved_path else None,
                    "lang": pipeline.current_lang,
                    "lang_warning": None if lang_result.get("ok") else lang_result.get("error"),
                }
            )

        # PERBAIKAN: "Rekam & Translate Audio" sekarang membersihkan &
        # men-transkrip Whisper TIAP ucapan/segmen PTT SECARA TERPISAH, lalu
        # menggabung hasilnya dengan join_segment_texts() -- ini yang
        # memastikan setiap batas ucapan PASTI diberi tanda titik (".") di
        # teks akhir, misal PTT "aku" [lepas] PTT "kamu" [lepas] menjadi
        # "Aku. Kamu." -- bukan bergantung pada tebakan Whisper soal jeda
        # (yang sebelumnya kadang malah menghasilkan koma atau tanpa tanda
        # baca sama sekali).
        cleaned_segments: List[np.ndarray] = []
        segment_texts: List[str] = []
        for idx, seg in enumerate(norm_segments, start=1):
            pipeline.current_label = f"Membersihkan ucapan #{idx}/{len(norm_segments)}…"
            seg_clean = clean_for_whisper(seg, int(sr))
            if seg_clean.size == 0:
                print(f"[API] Ucapan #{idx} kosong setelah cleaning, dilewati.", file=sys.stderr)
                continue

            if GAIN_LINEAR != 1.0:
                seg_clean = seg_clean * GAIN_LINEAR
            peak = float(np.max(np.abs(seg_clean))) if seg_clean.size else 0.0
            if peak > 1.0:
                seg_clean = seg_clean / peak * 0.99
            seg_clean = np.nan_to_num(
                seg_clean, nan=0.0, posinf=0.0, neginf=0.0
            ).astype(np.float32)

            if float(np.sqrt(np.mean(seg_clean * seg_clean) + 1e-12)) < 1e-6:
                print(f"[API] Ucapan #{idx} terlalu pelan setelah reduksi noise, dilewati.", file=sys.stderr)
                continue

            cleaned_segments.append(seg_clean)

            seg16 = (
                resample_to_16k(seg_clean, int(sr))
                if int(sr) != TARGET_SR
                else seg_clean
            )
            seg16 = np.clip(seg16, -1.0, 1.0).astype(np.float32)
            if seg16.size == 0:
                print(f"[API] Ucapan #{idx} gagal di-resample, dilewati.", file=sys.stderr)
                continue

            pipeline.current_label = f"Transkripsi Whisper ucapan #{idx}/{len(norm_segments)}…"
            seg_text = remove_quotes(pipeline.whisper_transcribe_radio(seg16).strip())
            print(f"[API] Whisper ucapan #{idx}: {seg_text}", file=sys.stderr)
            if seg_text:
                segment_texts.append(seg_text)

        if not cleaned_segments:
            return jsonify(
                {"ok": False, "error": "Audio kosong/terlalu pelan setelah proses cleaning."}
            ), 200

        audio_clean = concat_audio_segments(cleaned_segments, int(sr), gap_sec=0.4)
        pipeline.last_audio_clean = audio_clean.copy()
        pipeline.last_audio_sr = int(sr)
        pipeline.last_audio_updated_at = time.time()

        duration = audio_clean.size / float(sr)
        print(
            f"[API] Audio siap: {duration:.2f} s @ {sr} Hz ({len(cleaned_segments)} ucapan)",
            file=sys.stderr,
        )

        # join_segment_texts() memastikan tiap ucapan diakhiri "." (kalau
        # belum diakhiri ".", "!", atau "?" oleh Whisper sendiri) sebelum
        # digabung -- lihat definisinya di atas.
        text_papua = join_segment_texts(segment_texts)

        print(f"[API] Whisper result (gabungan {len(segment_texts)} ucapan): {text_papua}", file=sys.stderr)
        if text_papua:
            pipeline.current_label = "Menerjemahkan hasil transkripsi radio…"
        text_indonesia = (
            pipeline.yali_to_id_segments_bestbleu(text_papua)
            if text_papua
            else ""
        )

        return jsonify(
            {
                "ok": True,
                "text_papua": text_papua,
                "text_indonesia": text_indonesia,
                "duration_sec": duration,
                "saved_file": str(saved_path) if saved_path else None,
                "lang": pipeline.current_lang,
                "lang_warning": None if lang_result.get("ok") else lang_result.get("error"),
            }
        )
    except sd.PortAudioError as exc:
        tb = traceback.format_exc()
        print(f"[API ERROR] /record-radio (PortAudio): {exc}\n{tb}", file=sys.stderr)
        msg = str(exc)
        if "WDM-KS" in msg or "-9999" in msg or "Unanticipated host error" in msg:
            friendly = (
                "Gagal membuka perangkat lewat Windows WDM-KS. Pilih perangkat "
                "yang sama melalui WASAPI, DirectSound, atau MME."
            )
        else:
            friendly = f"Gagal membuka input audio ({msg})."
        return jsonify({"ok": False, "error": friendly, "traceback": tb}), 200
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[API ERROR] /record-radio: {exc}\n{tb}", file=sys.stderr)
        return jsonify({"ok": False, "error": str(exc), "traceback": tb}), 200
    finally:
        pipeline.current_phase = "idle"
        pipeline.current_label = "Siap"
        pipeline.current_rms = 0.0
        pipeline.record_lock.release()


@app.route("/last-audio.wav", methods=["GET"])
def last_audio_wav():
    try:
        wav_bytes = pipeline.get_last_audio_wav_bytes()
        if wav_bytes is None:
            return jsonify({"ok": False, "error": "Belum ada rekaman radio."}), 404

        buf = io.BytesIO(wav_bytes)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="last_audio.wav",
        )
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500

@app.route("/translate-text", methods=["POST"])
def translate_text():
    try:
        data = request.get_json(force=True, silent=False) or {}
        text = (data.get("text") or "").strip()
        text = remove_quotes(text)
        if not text:
            return jsonify({"ok": False, "error": "Input teks kosong."}), 400

        lang_result = pipeline.set_language(data.get("lang", ""))
        if not lang_result.get("ok"):
            print(
                f"[API] /translate-text: tetap memakai bahasa '{pipeline.current_lang}' "
                f"karena gagal ganti -> {lang_result.get('error')}",
                file=sys.stderr,
            )

        print("[API] /translate-text", file=sys.stderr)
        pipeline.current_phase = "processing"
        pipeline.current_label = "Menerjemahkan teks…"
        text_id = pipeline.yali_to_id_segments_bestbleu(text)

        return jsonify(
            {
                "ok": True,
                "input_papua": text,
                "output_indonesia": text_id,
                "lang": pipeline.current_lang,
                "lang_warning": None if lang_result.get("ok") else lang_result.get("error"),
            }
        )
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500
    finally:
        pipeline.current_phase = "idle"
        pipeline.current_label = "Siap"
    
@app.route("/preview-upload-audio", methods=["POST"])
def preview_upload_audio():
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "File tidak ditemukan"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"ok": False, "error": "Nama file kosong"}), 400

        filename = file.filename
        filename_lower = filename.lower()

        if not (filename_lower.endswith(".wav") or filename_lower.endswith(".mp3")):
            return jsonify({
                "ok": False,
                "error": "Format file harus WAV atau MP3."
            }), 400

        pipeline.current_phase = "processing"
        pipeline.current_label = "Menyiapkan pratinjau audio unggahan…"

        audio_bytes = file.read()

        if not audio_bytes:
            return jsonify({
                "ok": False,
                "error": "File audio kosong."
            }), 400

        # Tentukan mimetype
        if filename_lower.endswith(".mp3"):
            mime_type = "audio/mpeg"
        else:
            mime_type = "audio/wav"

        # Simpan sementara di memory
        pipeline.upload_preview_bytes = audio_bytes
        pipeline.upload_preview_mime = mime_type
        pipeline.upload_preview_filename = filename
        pipeline.upload_preview_updated_at = time.time()

        print(f"[PREVIEW UPLOAD] Audio disimpan sementara: {filename}", file=sys.stderr)

        return jsonify({
            "ok": True,
            "filename": filename,
            "audio_url": f"/upload-preview-audio?t={int(time.time())}"
        })

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[PREVIEW UPLOAD ERROR] {e}\n{tb}", file=sys.stderr)
        return jsonify({
            "ok": False,
            "error": str(e),
            "traceback": tb
        }), 500
    finally:
        pipeline.current_phase = "idle"
        pipeline.current_label = "Siap"


@app.route("/upload-preview-audio", methods=["GET"])
def upload_preview_audio():
    try:
        if not hasattr(pipeline, "upload_preview_bytes"):
            return jsonify({
                "ok": False,
                "error": "Belum ada audio upload untuk diputar."
            }), 404

        audio_bytes = pipeline.upload_preview_bytes
        mime_type = getattr(pipeline, "upload_preview_mime", "audio/wav")
        filename = getattr(pipeline, "upload_preview_filename", "upload_audio.wav")

        buf = io.BytesIO(audio_bytes)
        buf.seek(0)

        return send_file(
            buf,
            mimetype=mime_type,
            as_attachment=False,
            download_name=filename,
            max_age=0
        )

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[UPLOAD PREVIEW AUDIO ERROR] {e}\n{tb}", file=sys.stderr)
        return jsonify({
            "ok": False,
            "error": str(e),
            "traceback": tb
        }), 500

@app.route("/upload-audio", methods=["POST"])
def upload_audio():
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "File tidak ditemukan"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"ok": False, "error": "Nama file kosong"}), 400

        filename = file.filename.lower()
        print(f"[UPLOAD] File diterima: {filename}", file=sys.stderr)

        lang_result = pipeline.set_language(request.form.get("lang", ""))
        if not lang_result.get("ok"):
            print(
                f"[UPLOAD] tetap memakai bahasa '{pipeline.current_lang}' "
                f"karena gagal ganti -> {lang_result.get('error')}",
                file=sys.stderr,
            )

        # =========================
        # LOAD AUDIO (MP3/WAV)
        # =========================
        audio_bytes = file.read()

        # Gunakan pydub untuk support mp3/wav
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))

        sr = audio_segment.frame_rate
        samples = np.array(audio_segment.get_array_of_samples()).astype(np.float32)

        # stereo → mono
        if audio_segment.channels > 1:
            samples = samples.reshape((-1, audio_segment.channels)).mean(axis=1)

        # normalize ke float32 [-1,1]
        samples = samples / (1 << (8 * audio_segment.sample_width - 1))

        print(f"[UPLOAD] Audio loaded: {len(samples)/sr:.2f} sec @ {sr} Hz", file=sys.stderr)

        # =========================
        # CLEANING (PAKAI PIPELINE KAMU)
        # =========================
        pipeline.current_phase = "processing"
        pipeline.current_label = "Membersihkan audio unggahan (reduksi noise)…"

        audio_clean = clean_for_whisper_upload_no_trim(samples, sr)

        # gain
        audio_clean = audio_clean * GAIN_LINEAR
        mx = float(np.max(np.abs(audio_clean)) + 1e-9)
        if mx > 1.0:
            audio_clean = (audio_clean / mx) * 0.99

        # simpan untuk playback
        pipeline.last_audio_clean = audio_clean
        pipeline.last_audio_sr = sr

        # =========================
        # WHISPER
        # =========================
        print("[UPLOAD] Whisper transcribe...", file=sys.stderr)
        pipeline.current_label = "Transkripsi Whisper (audio unggahan)…"

        audio16 = resample_to_16k(audio_clean, sr)
        print(f"[UPLOAD] audio16 shape={audio16.shape}, max={np.max(np.abs(audio16)):.6f}", file=sys.stderr)
        text_papua = pipeline.whisper_transcribe_upload(audio16).strip()

        if text_papua and not text_papua.endswith("."):
            text_papua += "."

        text_papua = remove_quotes(text_papua)

        print(f"[UPLOAD] Whisper result: {text_papua}", file=sys.stderr)

        # =========================
        # TRANSLATE
        # =========================
        if text_papua:
            pipeline.current_label = "Menerjemahkan hasil transkripsi unggahan…"
        text_id = pipeline.yali_to_id_segments_bestbleu(text_papua)

        pipeline.current_phase = "idle"
        pipeline.current_label = "Siap"

        return jsonify({
            "ok": True,
            "text_papua": text_papua,
            "text_indonesia": text_id,
            "lang": pipeline.current_lang,
            "lang_warning": None if lang_result.get("ok") else lang_result.get("error"),
        })

    except Exception as e:
        tb = traceback.format_exc()
        pipeline.current_phase = "idle"
        pipeline.current_label = "Siap"
        print(f"[UPLOAD ERROR] {e}\n{tb}", file=sys.stderr)
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500

@app.route("/tts", methods=["GET"])
def tts():
    try:
        text = (request.args.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "Teks kosong untuk TTS."}), 400

        cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()

        with pipeline._tts_cache_lock:
            cached_mp3 = pipeline._tts_cache.get(cache_key)

        if cached_mp3 is not None:
            # Teks ini sudah pernah di-TTS-kan sebelumnya -> langsung pakai
            # hasil yang tersimpan, TIDAK perlu memanggil Google lagi.
            print(f"[TTS] Cache HIT untuk teks (panjang={len(text)}), tidak memanggil gTTS.", file=sys.stderr)
            pipeline.current_phase = "idle"
            pipeline.current_label = "Siap"
            return send_file(
                io.BytesIO(cached_mp3),
                mimetype="audio/mpeg",
                as_attachment=False,
                download_name="tts_id.mp3",
            )

        pipeline.current_phase = "processing"
        pipeline.current_label = "Membuat suara TTS…"

        mp3_buf = io.BytesIO()
        gTTS(text=text, lang="id").write_to_fp(mp3_buf)
        mp3_bytes = mp3_buf.getvalue()

        with pipeline._tts_cache_lock:
            pipeline._tts_cache[cache_key] = mp3_bytes
            pipeline._tts_cache_order.append(cache_key)
            # Buang entri paling lama kalau cache sudah penuh.
            while len(pipeline._tts_cache_order) > pipeline._tts_cache_max_entries:
                oldest_key = pipeline._tts_cache_order.popleft()
                pipeline._tts_cache.pop(oldest_key, None)

        return send_file(
            io.BytesIO(mp3_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="tts_id.mp3",
        )
    except (gTTSError, socket.gaierror, ConnectionError, TimeoutError) as e:
        # PERBAIKAN: sebelumnya kegagalan gTTS (paling sering karena server
        # TIDAK ADA akses internet ke Google Translate TTS, atau permintaan
        # diblokir/timeout) jatuh ke except Exception generik di bawah --
        # pesannya jadi baris exception mentah yang tidak jelas maksudnya
        # bagi user. Sekarang kasus ini dibedakan & diberi pesan yang
        # langsung ke akar masalah.
        tb = traceback.format_exc()
        return jsonify({
            "ok": False,
            "error": (
                "Gagal membuat suara TTS: tidak bisa menghubungi layanan Google "
                "Text-to-Speech. Pastikan perangkat server (bukan hanya browser) "
                f"punya koneksi internet aktif. Detail: {e}"
            ),
            "traceback": tb,
        }), 500
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500
    finally:
        pipeline.current_phase = "idle"
        pipeline.current_label = "Siap"


if __name__ == "__main__":
    try:
        torch_env.ensure_torch()
        torch_env.ensure_transformers()
        print(f"[INIT] Device: {torch_env.device}", file=sys.stderr)
    except Exception as e:
        print(f"[INIT ERROR] {e}", file=sys.stderr)

    # Nyalakan thread background pencarian frekuensi HT otomatis (0–600 MHz
    # secara default, lihat AUTO_SCAN_* di atas). Kalau YALI_AUTOSCAN_ENABLED=0,
    # thread tetap hidup tapi diam (idle) sampai diaktifkan lewat POST /scan/start.
    auto_scanner.launch()
    print(
        f"[INIT] Auto-scan frekuensi HT: "
        f"{'AKTIF' if AUTO_SCAN_ENABLED_DEFAULT else 'nonaktif (idle)'} "
        f"({AUTO_SCAN_MIN_HZ/1e6:.1f}–{AUTO_SCAN_MAX_HZ/1e6:.1f} MHz, "
        f"langkah {AUTO_SCAN_STEP_HZ/1000:.1f} kHz)",
        file=sys.stderr,
    )

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)