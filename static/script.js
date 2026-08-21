(() => {
  'use strict';

  /* ============================================================
     KONFIGURASI BACKEND
     Karena halaman ini di-render oleh Flask (render_template) dan
     dibuka lewat http://<host>:5000/, kita pakai path relatif saja
     supaya otomatis memanggil origin yang sama (tanpa masalah CORS).
     ============================================================ */
  const API_BASE = '';

  /* ============================================================
     VIDEO PENGANTAR (Home)
     Isi salah satu dari:
       - nama file video yang ditaruh di folder static/ Flask, format
         apa saja yang bisa diputar browser (mp4, webm, ogg, mov, mkv,
         dst), contoh: 'papua.mp4' -> otomatis diarahkan ke
         '/static/papua.mp4' (folder yang sama dengan logo & style.css)
       - path absolut di server, contoh: '/static/videos/intro.mp4'
       - URL video langsung (http/https) ke file video, contoh:
         'https://example.com/video/intro.mp4'
       - link YouTube (watch, youtu.be, shorts) atau Vimeo, contoh:
         'https://www.youtube.com/watch?v=XXXXXXXXXXX'
     Deteksi sumber & pemilihan pemutar (tag <video> vs iframe embed)
     dilakukan otomatis oleh resolveVideoSource(), lihat di bawah.
     Selama dikosongkan (''), tombol play akan menampilkan pesan
     yang jelas alih-alih memuat file yang tidak ada (mencegah 404).
     ============================================================ */
  const INTRO_VIDEO_URL = 'papua.mp4';

  /* ---- Deteksi sumber video: file langsung vs YouTube/Vimeo ---- */
  function getYouTubeVideoId(url){
    try{
      const u = new URL(url, window.location.href);
      const host = u.hostname.replace(/^www\./, '');
      if (host === 'youtu.be'){
        return u.pathname.slice(1).split('/')[0] || null;
      }
      if (host === 'youtube.com' || host === 'm.youtube.com' || host === 'music.youtube.com'){
        if (u.pathname === '/watch') return u.searchParams.get('v');
        const m = u.pathname.match(/^\/(embed|shorts|live)\/([^/?]+)/);
        if (m) return m[2];
      }
    } catch(e){ /* bukan URL absolut (kemungkinan path file lokal), abaikan */ }
    return null;
  }
  function getVimeoVideoId(url){
    try{
      const u = new URL(url, window.location.href);
      const host = u.hostname.replace(/^www\./, '');
      if (host === 'vimeo.com' || host === 'player.vimeo.com'){
        const m = u.pathname.match(/(\d+)/);
        if (m) return m[1];
      }
    } catch(e){ /* abaikan */ }
    return null;
  }
  function resolveVideoSource(url){
    const ytId = getYouTubeVideoId(url);
    if (ytId) return { type: 'embed', embedUrl: `https://www.youtube-nocookie.com/embed/${ytId}?autoplay=1&rel=0` };
    const vimeoId = getVimeoVideoId(url);
    if (vimeoId) return { type: 'embed', embedUrl: `https://player.vimeo.com/video/${vimeoId}?autoplay=1` };
    // Bukan YouTube/Vimeo -> anggap file video langsung, diputar lewat tag
    // <video> bawaan. PERBAIKAN: sebelumnya nama file polos (mis. 'papua.mp4')
    // dipakai apa adanya sebagai src, sehingga browser memintanya relatif ke
    // URL halaman ("/papua.mp4") -- BUKAN ke folder static Flask tempat file
    // itu sebenarnya berada ("/static/papua.mp4"), makanya video selalu gagal
    // dimuat ("no supported source was found") walau formatnya sudah benar.
    // Sekarang: URL absolut (http/https), path absolut ("/..."), maupun
    // data: URL dipakai apa adanya; selain itu otomatis diarahkan ke
    // "/static/<nama>", sama seperti logo & style.css di index.html.
    const isAbsolute = /^([a-z][a-z0-9+.-]*:)?\/\//i.test(url) || url.startsWith('/') || url.startsWith('data:');
    const directUrl = isAbsolute ? url : `/static/${url.replace(/^\.?\//, '')}`;
    return { type: 'direct', directUrl };
  }

  /* ============================================================
     UTILITIES
     ============================================================ */
  const $ = (id) => document.getElementById(id);

  function formatMHz(hz){
    return (hz / 1_000_000).toFixed(6);
  }
  function formatMHzShort(hz){
    return (hz / 1_000_000).toFixed(3);
  }
  // Label MHz dengan jumlah desimal yang menyesuaikan besar step antar-tick
  // (mis. step 50 kHz -> "32.60 MHz", step 500 kHz -> "32.5 MHz"), supaya
  // ruler tidak penuh sesak dengan digit yang tidak perlu saat di-zoom out,
  // sekaligus tetap presisi saat di-zoom in -- mirip label pada gambar
  // referensi ("32.60 MHz", "32.65 MHz", dst).
  function formatMHzForStep(hz, stepHz){
    const decimals = stepHz >= 1_000_000 ? 0 : (stepHz >= 100_000 ? 1 : (stepHz >= 10_000 ? 2 : 3));
    return (hz / 1_000_000).toFixed(decimals);
  }
  // Menghitung "step" antar-tick yang rapi (1, 2, atau 5 dikali kelipatan 10)
  // dari sebuah perkiraan kasar -- teknik umum untuk auto-scaling ruler/grid
  // supaya jaraknya selalu bulat & enak dibaca, bukan angka pecahan aneh.
  function niceStep(roughStep){
    if (!(roughStep > 0)) return 1;
    const pow10 = Math.pow(10, Math.floor(Math.log10(roughStep)));
    const frac = roughStep / pow10;
    let niceFrac;
    if (frac <= 1) niceFrac = 1;
    else if (frac <= 2) niceFrac = 2;
    else if (frac <= 5) niceFrac = 5;
    else niceFrac = 10;
    return niceFrac * pow10;
  }
  function formatHz(hz){
    return Math.round(hz).toLocaleString('id-ID') + ' Hz';
  }
  function formatKHz(hz){
    return (hz / 1000).toFixed(2);
  }
  function clamp(v, min, max){
    return Math.min(max, Math.max(min, v));
  }
  function setSliderFill(slider){
    const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
    slider.style.setProperty('--fill', pct + '%');
  }
  function truncateForLog(text, max = 90){
    if (!text) return '(kosong)';
    return text.length > max ? text.slice(0, max) + '…' : text;
  }
  async function safeJson(res){
    try { return await res.json(); }
    catch(e){ return { ok: false, error: `Respons server tidak valid (HTTP ${res.status}).` }; }
  }

  /* ============================================================
     LOG CONSOLE
     ============================================================ */
  const logBox = $('logBox');

  function log(message, type = 'info'){
    const line = document.createElement('div');
    line.className = `log-line type-${type}`;
    const time = new Date().toLocaleTimeString('id-ID', { hour12: false });
    line.innerHTML = `<span class="log-time">[${time}]</span><span class="log-msg"></span>`;
    line.querySelector('.log-msg').textContent = message;
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
  }

  function logLangWarningIfAny(data){
    if (data && data.lang_warning){
      log(`Peringatan bahasa: ${data.lang_warning}`, 'warn');
    }
  }

  // Label "Siap" pada status pill sekarang mengikuti bahasa Papua yang
  // sedang aktif ("Ambai Siap" / "Biak Siap"), bukan cuma "Siap" polos --
  // supaya operator selalu tahu bahasa mana yang sedang dipakai hanya
  // dengan melihat status pill. `selectedPapuaLang` di sini dibaca lewat
  // closure (diisi belakangan di bagian "Pilih Bahasa Papua"), aman karena
  // fungsi ini hanya benar-benar dipanggil saat event terjadi, bukan saat
  // skrip pertama kali dijalankan.
  const PAPUA_LANG_LABELS = { ambai: 'Ambai', biak: 'Biak' };
  function papuaSiapLabel(){
    const langLabel = PAPUA_LANG_LABELS[selectedPapuaLang] || '';
    return langLabel ? `${langLabel} Siap` : 'Siap';
  }

  $('clearLogBtn').addEventListener('click', () => {
    logBox.innerHTML = '';
    log('Log dibersihkan.', 'info');
  });

  /* ============================================================
     NAVIGASI HALAMAN (Home / Set Radio / Auto Translate)
     ============================================================ */
  const pages = {
    pageHome: $('pageHome'),
    pageSetRadio: $('pageSetRadio'),
    pageTranslate: $('pageTranslate'),
  };
  const navButtons = {
    pageHome: $('navHomeBtn'),
    pageSetRadio: $('navSetRadioBtn'),
    pageTranslate: $('navTranslateBtn'),
  };

  function showPage(pageId){
    Object.entries(pages).forEach(([id, el]) => {
      const active = id === pageId;
      el.hidden = !active;
      el.classList.toggle('active', active);
      navButtons[id].setAttribute('aria-selected', active ? 'true' : 'false');
    });
    if (pageId === 'pageSetRadio') resizeScopeCanvases();
  }

  Object.entries(navButtons).forEach(([id, btn]) => {
    btn.addEventListener('click', () => showPage(id));
  });

  document.querySelectorAll('[data-goto]').forEach(btn => {
    btn.addEventListener('click', () => showPage(btn.dataset.goto));
  });


  // Toggle sidebar Frekuensi/Bandwidth (satu-satunya sumber kebenaran: class
  // .sidebar-open pada .radio-console — dulu ada 2 handler yang bentrok
  // [salah satunya men-toggle class .collapsed terpisah], itulah sebabnya
  // klik ikon garis 3 kadang tidak menampilkan sidebar sama sekali).
  const radioConsoleEl = document.querySelector('.radio-console');
  const sidebarToggleBtnTop = $('sidebarToggleBtnTop');
  const sidebarToggleBtnInside = $('sidebarToggleBtn');

  function toggleRadioSidebar(){
    radioConsoleEl.classList.toggle('sidebar-open');
  }
  if (sidebarToggleBtnTop) sidebarToggleBtnTop.addEventListener('click', toggleRadioSidebar);
  if (sidebarToggleBtnInside) sidebarToggleBtnInside.addEventListener('click', toggleRadioSidebar);

  
  /* ============================================================
     TAB FREKUENSI / BANDWIDTH (di sidebar Set Radio)
     ============================================================ */
  const tabFrekuensiBtn = $('tabFrekuensiBtn');
  const tabBandwidthBtn = $('tabBandwidthBtn');
  const panelFreqEl = $('panelFreq');
  const panelBwEl = $('panelBw');

  function showFbwTab(tab){
    const isFreq = tab === 'frekuensi';
    panelFreqEl.hidden = !isFreq;
    panelBwEl.hidden = isFreq;
    tabFrekuensiBtn.classList.toggle('active', isFreq);
    tabBandwidthBtn.classList.toggle('active', !isFreq);
  }
  tabFrekuensiBtn.addEventListener('click', () => showFbwTab('frekuensi'));
  tabBandwidthBtn.addEventListener('click', () => showFbwTab('bandwidth'));

  
  /* ============================================================
     FREQUENCY PANEL (kontrol lokal untuk SDR/receiver eksternal —
     tidak ada endpoint backend terkait, jadi tetap murni UI)
     ============================================================ */
  const freqSlider = $('freqSlider');
  const freqMHzEl = $('freqMHz');
  const freqHzEl = $('freqHz');
  const freqManual = $('freqManual');
  const freqPresets = $('freqPresets');

  let currentFreq = Number(freqSlider.value);
  let userEditingFreq = false; // true selama slider sedang di-drag -> jangan ditimpa oleh polling
  // radio = HT + freqOffsetHz; dipakai buat konversi skala di canvas spektrum.
  // Tidak ada lagi kontrol manual di UI -- nilainya diambil otomatis dari
  // backend (kalibrasi HT <-> WEB-888 sudah tetap/otomatis sejak awal masuk).
  let freqOffsetHz = 0;

  function setFreqActivePreset(hz){
    freqPresets.querySelectorAll('.chip').forEach(chip => {
      chip.classList.toggle('active', Number(chip.dataset.freq) === hz);
    });
  }

  function updateToolbarFreq(hz){
    const el = $('toolbarFreqValue');
    if (el) el.textContent = formatMHz(hz);
  }

  // Update tampilan saja saat slider sedang digeser (live preview), belum kirim ke SDR++.
  // Ini port dari on_slider_drag() di sdrpp_gui_controller.py.
  function previewFreqDisplay(hz){
    const clamped = clamp(hz, Number(freqSlider.min), Number(freqSlider.max));
    freqSlider.value = clamped;
    setSliderFill(freqSlider);
    freqMHzEl.textContent = formatMHz(clamped);
    freqHzEl.textContent = formatHz(clamped) + '  (preview)';
    updateToolbarFreq(clamped);
  }

  // Terapkan frekuensi baru ke tampilan lalu KIRIM ke SDR++.
  // Ini port dari set_target_mhz()/geser()/apply_manual_entry()/on_slider_release().
  function commitFreqDisplay(hz, source = 'slider'){
    currentFreq = clamp(hz, Number(freqSlider.min), Number(freqSlider.max));
    freqSlider.value = currentFreq;
    setSliderFill(freqSlider);
    freqMHzEl.textContent = formatMHz(currentFreq);
    freqHzEl.textContent = formatHz(currentFreq);
    setFreqActivePreset(currentFreq);
    updateToolbarFreq(currentFreq);
    log(`Frekuensi diatur ke ${formatMHz(currentFreq)} MHz (${source}).`, 'ok');
    sendFreqToSdr(currentFreq);
  }

  // Terapkan frekuensi hasil baca-balik dari SDR++ (polling), TANPA mengirim ulang
  // (supaya tidak jadi loop tak berujung). Ini port dari _update_display().
  function applyRemoteFreq(hz){
    currentFreq = clamp(hz, Number(freqSlider.min), Number(freqSlider.max));
    freqSlider.value = currentFreq;
    setSliderFill(freqSlider);
    freqMHzEl.textContent = formatMHz(currentFreq);
    freqHzEl.textContent = formatHz(currentFreq);
    setFreqActivePreset(currentFreq);
    updateToolbarFreq(currentFreq);
  }

  /* ---- Komunikasi dengan SDR++ lewat backend (backend yang bicara rigctl) ---- */
  async function sendFreqToSdr(hz){
    try{
      const res = await fetch(`${API_BASE}/sdr/frequency`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ freq_hz: Math.round(hz) })
      });
      const data = await safeJson(res);
      if (!data.ok) log(`SDR++: ${data.error}`, 'err');
    } catch(err){
      log(`Gagal mengirim frekuensi ke SDR++: ${err.message}`, 'err');
    }
  }

  async function sendModeToSdr(mode, bandwidthHz){
    try{
      const res = await fetch(`${API_BASE}/sdr/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, bandwidth_hz: Math.round(bandwidthHz) })
      });
      const data = await safeJson(res);
      if (!data.ok) log(`SDR++: ${data.error}`, 'err');
    } catch(err){
      log(`Gagal mengirim mode/bandwidth ke SDR++: ${err.message}`, 'err');
    }
  }

  /* ---- Offset frekuensi HT <-> WEB-888 (radio = frekuensi HT + offset) ----
     Sudah tidak ada kontrol manual di UI -- kalibrasi HT <-> WEB-888 dipakai
     otomatis dari backend (lihat WEB888_FREQ_OFFSET_HZ) sejak awal halaman
     dibuka, supaya frekuensi yang tampil di panel selalu langsung sama
     dengan frekuensi HT tanpa perlu diset manual. */
  async function loadFreqOffset(){
    try{
      const res = await fetch(`${API_BASE}/sdr/frequency-offset`);
      const data = await safeJson(res);
      if (!data.ok) return;
      freqOffsetHz = Number(data.offset_hz) || 0;
    } catch(err){
      // Diamkan: backend/koneksi mungkin belum siap saat halaman baru dibuka.
    }
  }

  loadFreqOffset();

  // Slider: preview live saat digeser (mouse masih ditekan)...
  freqSlider.addEventListener('input', () => {
    userEditingFreq = true;
    previewFreqDisplay(Number(freqSlider.value));
  });
  // ...baru kirim ke SDR++ saat mouse/jari dilepas (event 'change' pada <input type="range">
  // otomatis terpicu saat rilis, sama seperti on_slider_release() di GUI Tkinter).
  freqSlider.addEventListener('change', () => {
    commitFreqDisplay(Number(freqSlider.value), 'slider');
    userEditingFreq = false;
  });

  document.querySelectorAll('[data-freq-step]').forEach(btn => {
    btn.addEventListener('click', () => {
      commitFreqDisplay(currentFreq + Number(btn.dataset.freqStep), 'tombol geser');
    });
  });

  $('freqSetBtn').addEventListener('click', () => {
    const val = parseFloat(freqManual.value.replace(',', '.'));
    if (isNaN(val) || val <= 0){
      log('Nilai frekuensi manual tidak valid.', 'err');
      freqManual.focus();
      return;
    }
    commitFreqDisplay(val * 1_000_000, 'input manual');
    freqManual.value = '';
  });

  freqManual.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('freqSetBtn').click();
  });

  freqPresets.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    commitFreqDisplay(Number(chip.dataset.freq), 'preset');
  });

  /* ============================================================
     BANDWIDTH PANEL (dikirim bersama mode lewat satu perintah
     rigctl "M <mode> <passband>", persis seperti set_bandwidth()
     di sdrpp_gui_controller.py)
     ============================================================ */
  const bwSlider = $('bwSlider');
  const bwValueEl = $('bwValue');
  const bwManual = $('bwManual');
  const bwPresets = $('bwPresets');
  const modeSelect = $('modeSelect');

  let currentBw = Number(bwSlider.value);
  let userEditingBw = false; // true selama slider bandwidth di-drag

  function setBwActivePreset(hz){
    bwPresets.querySelectorAll('.chip').forEach(chip => {
      chip.classList.toggle('active', Number(chip.dataset.bw) === hz);
    });
  }

  function previewBwDisplay(hz){
    const clamped = clamp(hz, Number(bwSlider.min), Number(bwSlider.max));
    bwSlider.value = clamped;
    setSliderFill(bwSlider);
    bwValueEl.textContent = formatKHz(clamped);
  }

  function commitBwDisplay(hz, source = 'slider'){
    currentBw = clamp(hz, Number(bwSlider.min), Number(bwSlider.max));
    bwSlider.value = currentBw;
    setSliderFill(bwSlider);
    bwValueEl.textContent = formatKHz(currentBw);
    setBwActivePreset(currentBw);
    log(`Bandwidth diatur ke ${formatKHz(currentBw)} kHz (${source}).`, 'ok');
    sendModeToSdr(modeSelect.value, currentBw);
  }

  function applyRemoteBw(hz){
    currentBw = clamp(hz, Number(bwSlider.min), Number(bwSlider.max));
    bwSlider.value = currentBw;
    setSliderFill(bwSlider);
    bwValueEl.textContent = formatKHz(currentBw);
    setBwActivePreset(currentBw);
  }

  bwSlider.addEventListener('input', () => {
    userEditingBw = true;
    previewBwDisplay(Number(bwSlider.value));
  });
  bwSlider.addEventListener('change', () => {
    commitBwDisplay(Number(bwSlider.value), 'slider');
    userEditingBw = false;
  });

  $('bwSetBtn').addEventListener('click', () => {
    const val = parseFloat(bwManual.value.replace(',', '.'));
    if (isNaN(val) || val <= 0){
      log('Nilai bandwidth manual tidak valid.', 'err');
      bwManual.focus();
      return;
    }
    commitBwDisplay(val * 1000, 'input manual');
    bwManual.value = '';
  });

  bwManual.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('bwSetBtn').click();
  });

  bwPresets.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    commitBwDisplay(Number(chip.dataset.bw), 'preset');
  });

  modeSelect.addEventListener('change', () => {
    log(`Mode demodulasi diganti ke ${modeSelect.value}.`, 'info');
    sendModeToSdr(modeSelect.value, currentBw);
  });

  /* ============================================================
     SINKRONISASI DUA ARAH DENGAN SDR++ (polling)
     Port dari _start_poll_thread() di sdrpp_gui_controller.py:
     baca frekuensi & mode/bandwidth dari SDR++ tiap 500ms, lalu
     update tampilan HANYA jika nilainya berbeda dan user sedang
     tidak menggeser slider yang bersangkutan.
     ============================================================ */
  let sdrFreqOnline = null; // null = belum dicek
  let sdrModeOnline = null;
  let sdrFreqFailStreak = 0;
  let sdrModeFailStreak = 0;
  // 502 di sini normal selama SDR++ (RigCTL) atau Web-888 belum disambungkan
  // dari halaman "Set Radio". Beri toleransi beberapa kegagalan dulu supaya
  // tidak langsung memunculkan peringatan begitu halaman baru dibuka.
  const SDR_FAIL_GRACE = 6; // ~6 x 500ms = 3 detik toleransi
  // PERBAIKAN BUG (lihat screenshot laporan): sebelumnya polling
  // /sdr/frequency & /sdr/mode jalan lewat setInterval tetap 500ms TANPA
  // guard overlap dan TANPA backoff. Saat backend mati/restart lama, 502
  // menumpuk terus tiap 500ms sampai akhirnya socket OS kehabisan buffer
  // (net::ERR_NO_BUFFER_SPACE) seperti di log console. Sekarang polling
  // dijadwalkan ulang sendiri (bukan interval tetap) + backoff bertahap
  // saat gagal beruntun, lalu kembali ke kecepatan normal begitu backend
  // online lagi.
  let sdrPollTimer = null;
  let sdrPollInFlight = false;
  const SDR_POLL_BASE_MS = 500;
  const SDR_POLL_MAX_MS = 5000;
  const SDR_POLL_BACKOFF_START = SDR_FAIL_GRACE; // baru mulai backoff setelah masa toleransi lewat

  async function pollSdrFrequency(){
    if (userEditingFreq) return;
    try{
      const res = await fetch(`${API_BASE}/sdr/frequency`);
      const data = await safeJson(res);
      if (!data.ok){
        sdrFreqFailStreak++;
        if (sdrFreqOnline !== false && sdrFreqFailStreak > SDR_FAIL_GRACE){
          sdrFreqOnline = false;
          log(`SDR++ (frekuensi): ${data.error}`, 'warn');
        }
        return;
      }
      sdrFreqFailStreak = 0;
      if (sdrFreqOnline !== true){
        sdrFreqOnline = true;
        log('SDR++: berhasil membaca frekuensi (RigCTL tersambung).', 'ok');
      }
      if (Number.isFinite(Number(data.offset_hz))){
        freqOffsetHz = Number(data.offset_hz);
      }
      const freqHz = Number(data.freq_hz);
      if (Number.isFinite(freqHz) && freqHz !== currentFreq){
        applyRemoteFreq(freqHz);
      }
    } catch(err){
      if (sdrFreqOnline !== false) sdrFreqOnline = false;
    }
  }

  async function pollSdrMode(){
    if (userEditingBw) return;
    try{
      const res = await fetch(`${API_BASE}/sdr/mode`);
      const data = await safeJson(res);
      if (!data.ok){
        sdrModeFailStreak++;
        if (sdrModeOnline !== false) sdrModeOnline = false;
        return;
      }
      sdrModeFailStreak = 0;
      if (sdrModeOnline !== true) sdrModeOnline = true;

      const bwHz = Number(data.bandwidth_hz);
      if (Number.isFinite(bwHz) && bwHz !== currentBw){
        applyRemoteBw(bwHz);
      }

      const mode = String(data.mode || '').toUpperCase();
      if (mode && modeSelect.value !== mode){
        const hasOption = Array.from(modeSelect.options).some(opt => opt.value === mode);
        if (hasOption) modeSelect.value = mode;
      }
    } catch(err){
      sdrModeFailStreak++;
      if (sdrModeOnline !== false) sdrModeOnline = false;
    }
  }

  async function pollSdrOnce(){
    // Guard supaya request /sdr/frequency & /sdr/mode berikutnya tidak
    // ditembak sebelum yang sebelumnya selesai (mencegah request menumpuk
    // kalau backend lambat/mati) -- lihat catatan PERBAIKAN di atas.
    if (sdrPollInFlight) return;
    sdrPollInFlight = true;
    try{
      await Promise.all([pollSdrFrequency(), pollSdrMode()]);
    } finally {
      sdrPollInFlight = false;
      const failStreak = Math.max(sdrFreqFailStreak, sdrModeFailStreak);
      let delay = SDR_POLL_BASE_MS;
      if (failStreak > SDR_POLL_BACKOFF_START){
        const backoffLevel = Math.floor((failStreak - SDR_POLL_BACKOFF_START) / 4);
        delay = Math.min(SDR_POLL_MAX_MS, SDR_POLL_BASE_MS * Math.pow(2, backoffLevel));
      }
      sdrPollTimer = setTimeout(pollSdrOnce, delay);
    }
  }

  function startSdrPolling(){
    if (sdrPollTimer) clearTimeout(sdrPollTimer);
    pollSdrOnce();
  }

  /* ============================================================
     AUDIO PLAYER BERSAMA
     ============================================================ */
  const audioPlayer = $('audioPlayer');

  // Kalau playAudioUrl() dipanggil lagi sebelum play() sebelumnya selesai
  // (mis. klik cepat, atau dua sumber audio mau diputar hampir bersamaan),
  // pause() pada src baru membatalkan promise play() yang lama -> browser
  // melempar "AbortError: play() request was interrupted by a call to
  // pause()". Ini dijamin aman/normal, jadi kita: (1) antre pemanggilan
  // lewat rantai promise supaya tidak saling menimpa, dan (2) diamkan
  // AbortError-nya secara khusus alih-alih menampilkannya sebagai error.
  let audioPlayChain = Promise.resolve();

  // PERBAIKAN: status pill "Siap" sebelumnya diam saja saat audio sedang
  // diputar (radio/unggahan/TTS), jadi tidak "mengikuti" aksi playback di
  // front end. Sekarang pill menampilkan "Memutar Audio…" (tanpa kelas
  // .busy, karena ini bukan proses berat di backend) selama pemutaran,
  // lalu kembali ke "Siap" begitu audio selesai/berhenti/gagal.
  // PERBAIKAN: sebelumnya TIDAK ADA penanganan event 'error' pada elemen
  // <audio> bersama ini (dipakai oleh Play Audio Upload, Putar Audio Papua,
  // dan Play TTS). Kalau file audio dari backend gagal dimuat/diputar
  // (404, respons bukan audio, format tidak didukung, dll), tidak ada log
  // maupun perubahan status sama sekali -- pill tetap diam di "Siap" tanpa
  // keterangan apa pun. Sekarang error media ditangkap & dilaporkan jelas.
  function markPlayingStatus(){
    if (statusPill.classList.contains('busy')) return; // jangan timpa proses backend yang sedang berjalan
    statusPill.textContent = 'Memutar Audio…';
  }
  function resetPlayingStatus(){
    if (statusPill.classList.contains('busy')) return;
    statusPill.textContent = papuaSiapLabel();
  }
  audioPlayer.addEventListener('ended', resetPlayingStatus);
  audioPlayer.addEventListener('pause', resetPlayingStatus);
  audioPlayer.addEventListener('error', () => {
    if (!audioPlayer.currentSrc) return; // belum ada sumber yang dicoba, abaikan
    const codeMap = {1: 'dibatalkan', 2: 'jaringan gagal', 3: 'format/berkas rusak', 4: 'format tidak didukung browser'};
    const code = audioPlayer.error ? audioPlayer.error.code : null;
    const failedSrc = audioPlayer.currentSrc;
    log(`Audio gagal diputar (${codeMap[code] || 'tidak diketahui'}).`, 'err');
    resetPlayingStatus();
    // PERBAIKAN: kode error <audio> di atas (mis. "format tidak didukung
    // browser") cuma menjelaskan elemen <audio> gagal MEMAINKAN datanya --
    // padahal penyebab aslinya sering kali backend mengembalikan JSON error
    // (400/500, mis. /tts gagal generate suara karena server tidak ada
    // internet) alih-alih file audio asli, jadi pesan di atas jadi
    // membingungkan (seolah masalahnya format audio). Di sini kita cek
    // ulang sumber yang gagal tsb secara diam-diam: kalau isinya ternyata
    // JSON error dari backend, tampilkan pesan aslinya juga di log.
    fetch(failedSrc).then(async (res) => {
      const ct = res.headers.get('content-type') || '';
      if (!res.ok || ct.includes('application/json')){
        try{
          const data = await res.json();
          if (data && data.error) log(`Penyebab sebenarnya (dari server): ${data.error}`, 'err');
        } catch(_e){ /* bukan JSON valid, biarkan pesan generik di atas saja */ }
      }
    }).catch(() => { /* pengecekan tambahan ini opsional, abaikan kalau gagal */ });
  });

  // PERBAIKAN TAMBAHAN: sebagai lapisan pengaman ekstra (selain perbaikan
  // race condition di atas), URL audio non-blob selalu ditambahkan penanda
  // waktu unik sebelum dipasang ke elemen <audio> -- supaya walau URL dari
  // backend kebetulan sama dengan permintaan sebelumnya, browser tetap
  // mengambil ulang berkasnya dari server, bukan memutar audio dari cache.
  function withCacheBust(url){
    if (url.startsWith('blob:') || url.startsWith('data:')) return url; // sudah unik/tidak di-cache HTTP
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}_cb=${Date.now()}`;
  }

  function playAudioUrl(url, okMessage){
    // Status & log langsung tampil begini tombol ditekan (sinkron), tidak
    // menunggu promise play() selesai -- supaya selalu terlihat ada aksi
    // berjalan, walau audio ternyata gagal dimuat sesaat kemudian.
    statusPill.textContent = 'Memuat Audio…';
    statusPill.classList.remove('busy');
    log(`Memuat audio: ${url}`, 'info');

    audioPlayChain = audioPlayChain
      .catch(() => {}) // jangan biarkan kegagalan sebelumnya menghentikan antrean
      .then(() => {
        audioPlayer.pause();
        audioPlayer.src = withCacheBust(url);
        return audioPlayer.play();
      })
      .then(() => {
        markPlayingStatus();
        if (okMessage) log(okMessage, 'ok');
      })
      .catch(err => {
        if (err && err.name === 'AbortError'){
          // Race normal saat sumber audio diganti dengan cepat (mis. klik
          // ganda) -- tetap dicatat supaya tidak terlihat diam tanpa jejak.
          log('Pemutaran audio dibatalkan (sumber audio diganti).', 'warn');
          resetPlayingStatus();
          return;
        }
        log(`Tidak bisa memutar audio: ${err.message}`, 'err');
        resetPlayingStatus();
      });
  }

  /* ============================================================
     VOLUME CONTROL (di toolbar Set Radio, di samping tombol play)
     Mengatur volume elemen <audio> bersama yang dipakai untuk
     memutar rekaman radio maupun TTS.
     ============================================================ */
  const volumeSlider = $('volumeSlider');
  const volumeIcon = $('volumeIcon');

  function updateVolumeIcon(vol){
    if (!volumeIcon) return;
    volumeIcon.classList.toggle('muted', vol <= 0);
  }

  if (volumeSlider){
    audioPlayer.volume = Number(volumeSlider.value) / 100;
    setSliderFill(volumeSlider);
    updateVolumeIcon(audioPlayer.volume);

    volumeSlider.addEventListener('input', () => {
      const vol = clamp(Number(volumeSlider.value), 0, 100);
      audioPlayer.volume = vol / 100;
      setSliderFill(volumeSlider);
      updateVolumeIcon(audioPlayer.volume);
    });
  }

  if (volumeIcon){
    volumeIcon.addEventListener('click', () => {
      if (!volumeSlider) return;
      if (audioPlayer.volume > 0){
        volumeIcon.dataset.prevVol = volumeSlider.value;
        volumeSlider.value = 0;
      } else {
        volumeSlider.value = volumeIcon.dataset.prevVol || 100;
      }
      audioPlayer.volume = Number(volumeSlider.value) / 100;
      setSliderFill(volumeSlider);
      updateVolumeIcon(audioPlayer.volume);
    });
  }

  /* ============================================================
     AUDIO INPUT DEVICE — GET /devices
     ============================================================ */
  const deviceSelect = $('deviceSelect');
  const refreshBtn = $('refreshDevices');
  const statusPill = $('statusPill');
  const brandDot = $('brandDot');
  const brandLabel = $('brandLabel');

  function updateBrandDotFromDevice(){
    const opt = deviceSelect.options[deviceSelect.selectedIndex];
    const isCable = !!(opt && /cable/i.test(opt.textContent));
    brandDot.classList.toggle('offline', !isCable);
  }

  async function loadDevices(){
    deviceSelect.disabled = true;
    deviceSelect.innerHTML = '<option>Memuat perangkat…</option>';
    try{
      const res = await fetch(`${API_BASE}/devices`);
      const data = await safeJson(res);
      if (!data.ok) throw new Error(data.error || 'Gagal memuat daftar perangkat.');

      deviceSelect.innerHTML = '';
      if (!data.devices.length){
        const opt = document.createElement('option');
        opt.textContent = 'Tidak ada perangkat input ditemukan';
        deviceSelect.appendChild(opt);
        log('Tidak ada perangkat input audio yang terdeteksi di server.', 'warn');
        return;
      }

      // Prioritas pemilihan otomatis perangkat CABLE: WASAPI > DirectSound > MME > WDM-KS.
      // CATATAN: 'Windows WDM-KS' sengaja ditaruh PALING BAWAH sekarang -- banyak
      // adapter USB audio melempar error PortAudio "Unanticipated host error
      // [PaErrorCode -9999]" / "usbTerminalGUID" kalau dibuka lewat WDM-KS
      // (bug driver yang dikenal luas), jadi jangan jadikan pilihan utama.
      const HOSTAPI_PRIORITY = ['WASAPI', 'Windows DirectSound', 'MME', 'Windows WDM-KS'];
      let bestCable = null; // { index, priority }

      data.devices.forEach((d) => {
        const hostapi = d.hostapi || '?';
        const isWdmKs = /wdm-ks/i.test(hostapi);
        const opt = document.createElement('option');
        opt.value = String(d.index);
        opt.textContent = isWdmKs
          ? `[${d.index}] ${d.name} — ${hostapi} ⚠️ kurang stabil`
          : `[${d.index}] ${d.name} — ${hostapi}`;
        deviceSelect.appendChild(opt);

        if (/cable/i.test(d.name)){
          let prio = HOSTAPI_PRIORITY.findIndex(p => hostapi.toLowerCase().includes(p.toLowerCase()));
          if (prio === -1) prio = HOSTAPI_PRIORITY.length; // tidak dikenal -> prioritas terendah
          if (!bestCable || prio < bestCable.priority) bestCable = { index: d.index, priority: prio };
        }
      });
      if (bestCable) deviceSelect.value = String(bestCable.index);

      updateBrandDotFromDevice();
      log(`Daftar perangkat audio diperbarui (${data.devices.length} perangkat).`, 'ok');
    } catch(err){
      deviceSelect.innerHTML = '<option>Gagal memuat perangkat</option>';
      log(`Gagal memuat perangkat dari server: ${err.message}`, 'err');
    } finally {
      deviceSelect.disabled = false;
    }
  }

  deviceSelect.addEventListener('change', () => {
    const opt = deviceSelect.options[deviceSelect.selectedIndex];
    log(`Perangkat input dipilih: ${opt ? opt.textContent : '-'}`, 'info');
    updateBrandDotFromDevice();
  });

  refreshBtn.addEventListener('click', () => {
    refreshBtn.style.transform = 'rotate(180deg)';
    setTimeout(() => { refreshBtn.style.transform = ''; }, 300);
    loadDevices();
  });

  /* ============================================================
     RMS METER — polling GET /rms
     ============================================================ */
  const rmsValueEl = $('rmsValue');
  const meterFill = $('meterFill');
  const thresholdToggle = $('thresholdToggle');
  const thresholdLabel = $('thresholdLabel');

  // PERBAIKAN: sebelumnya pill status HANYA punya 4 teks generik hardcode
  // ("Merekam Sinyal"/"Mendengarkan…"/"Memproses…"/"Siap") berdasarkan
  // `phase` saja -- jadi kalau backend sedang mengerjakan sesuatu yang
  // lebih spesifik (mis. "Transkripsi Whisper" vs "Menerjemahkan" vs
  // "Membuat suara TTS", semuanya cuma tampil "Memproses…"), dan endpoint
  // yang TIDAK mengubah `phase` sama sekali (translate-text/tts/preview
  // upload sebelum ini) pill-nya tidak mengikuti apa pun. Backend sekarang
  // selalu mengirim `label` (teks manusiawi, lihat pipeline.current_label
  // di app_faster_whisper_lokal.py) lewat /rms -- pill di sini SELALU
  // memakai teks itu apa adanya kalau ada, supaya keterangan yang tampil ke
  // user PERSIS mengikuti apa yang backend bilang, bukan tebakan lokal.
  // Kelas 'busy' (dot animasi) tetap ditentukan dari `phase`, bukan label.
  function applyPhaseToStatusPill(phase, label){
    switch(phase){
      case 'recording':
        statusPill.textContent = label || 'Merekam Sinyal';
        statusPill.classList.add('busy');
        break;
      case 'listening':
        statusPill.textContent = label || 'Mendengarkan…';
        statusPill.classList.remove('busy');
        break;
      case 'processing':
        statusPill.textContent = label || 'Memproses…';
        statusPill.classList.add('busy');
        break;
      default:
        statusPill.textContent = papuaSiapLabel();
        statusPill.classList.remove('busy');
    }
  }

  // PERBAIKAN: sebelumnya perubahan fase proses di backend (listening ->
  // recording -> processing -> idle) HANYA terlihat di status pill kecil,
  // tidak pernah tercatat di panel Log/Console -- jadi user tidak dapat
  // pemberitahuan yang jelas soal proses apa yang sedang berjalan di
  // belakang layar. Sekarang tiap kali fase BERUBAH (bukan tiap polling,
  // supaya log tidak banjir tiap 400ms), backend log satu baris ke console.
  // PERBAIKAN: log ini sekarang memakai `label` asli dari backend (kalau
  // ada) alih-alih teks generik per-fase, supaya konsisten dengan pill.
  // PERBAIKAN LANJUTAN: dedup SEBELUMNYA berdasarkan `phase` saja, jadi
  // selama satu siklus "Rekam & Translate Audio" (input HT sampai hasil
  // terjemahan keluar), banyak tahap berbeda (bersihkan noise -> transkripsi
  // Whisper -> menerjemahkan -> simpan berkas) semuanya berbagi `phase` yang
  // SAMA ("processing"), sehingga hanya tahap PERTAMA yang pernah tercatat
  // di log/console -- tahap-tahap berikutnya diam, padahal pill-nya sendiri
  // sudah berubah teks. Sekarang dedup dilakukan atas kombinasi
  // (phase + label), jadi SETIAP tahap yang punya keterangan berbeda dari
  // backend selalu tercatat satu baris log, dari mulai menunggu sinyal HT
  // sampai hasil akhir keluar.
  let lastLoggedKey = null;
  const PHASE_LOG_MESSAGES = {
    listening: 'Backend: menunggu sinyal PTT/VOX dari radio…',
    recording: 'Backend: sinyal terdeteksi, merekam audio…',
    processing: 'Backend: memproses audio (cleaning, Whisper, terjemahan)…',
    idle: 'Backend: proses selesai, kembali siap.',
  };
  function logBackendPhaseChange(phase, label){
    const normalizedPhase = phase || 'idle';
    const normalizedLabel = label || '';
    const key = normalizedPhase + '|' + normalizedLabel;
    if (key === lastLoggedKey) return;
    // Saat pertama kali polling jalan (belum ada fase sebelumnya), jangan
    // langsung log "idle" supaya console tidak berisik begitu halaman dibuka.
    const isFirstRead = lastLoggedKey === null;
    lastLoggedKey = key;
    if (isFirstRead && normalizedPhase === 'idle') return;
    const message = (normalizedPhase !== 'idle' && normalizedLabel)
      ? `Backend: ${normalizedLabel}`
      : PHASE_LOG_MESSAGES[normalizedPhase];
    if (message) log(message, normalizedPhase === 'idle' ? 'ok' : 'info');
  }

  let rmsPollTimer = null;
  let backendOnline = null; // null = belum dicek
  let rmsFailStreak = 0;
  // Backend butuh beberapa detik untuk load model (Whisper/torch) sebelum
  // Flask siap menerima koneksi. Beri toleransi beberapa kegagalan beruntun
  // dulu sebelum benar-benar menandai "SERVER OFFLINE", supaya tidak flapping
  // merah di log padahal cuma server masih booting.
  const RMS_FAIL_GRACE = 5; // ~5 x 400ms = 2 detik toleransi

  // BUG DITEMUKAN: elemen id="thresholdLabel" sudah tidak ada di index.html
  // (sudah dihapus dari UI), tapi baris `thresholdLabel.textContent = ...`
  // di bawah masih dipanggil TANPA pengecekan null, DI DALAM try block yang
  // SAMA dengan kode yang mengupdate status pill ("Siap") dan log console.
  // Karena thresholdLabel selalu null, baris itu SELALU melempar TypeError
  // setiap kali polling /rms jalan (tiap 400ms) -- error itu langsung
  // ditangkap oleh catch() di bawah, sehingga applyPhaseToStatusPill() dan
  // logBackendPhaseChange() TIDAK PERNAH SEMPAT DIPANGGIL. Akibatnya pill
  // status diam terus di "Siap" dan log console tidak pernah mencatat
  // proses backend (rekam/cleaning/Whisper/translate), walau backend-nya
  // sendiri sudah mengirim phase/label yang benar lewat /rms.
  //
  // PERBAIKAN: (1) elemen opsional yang mungkin tidak ada di HTML sekarang
  // dijaga dengan pengecekan null, dan (2) yang lebih penting, update
  // tampilan meter/threshold (non-kritis) dipisah ke try/catch-nya SENDIRI
  // dari update status pill + log console (kritis) -- supaya kalau ada
  // elemen UI lain yang suatu saat dihapus/berubah lagi, itu TIDAK PERNAH
  // BISA lagi diam-diam mem-block pemberitahuan proses ke user.
  function startRmsPolling(){
    if (rmsPollTimer) return;
    rmsPollTimer = setInterval(async () => {
      let data;
      try{
        const res = await fetch(`${API_BASE}/rms`);
        data = await safeJson(res);
        if (!data.ok) return;

        rmsFailStreak = 0;
        if (backendOnline !== true){
          backendOnline = true;
          brandLabel.textContent = 'TRANSLATE · ONLINE';
          log('Terhubung ke backend.', 'ok');
        }
      } catch(err){
        rmsFailStreak++;
        if (backendOnline !== false && rmsFailStreak > RMS_FAIL_GRACE){
          backendOnline = false;
          brandLabel.textContent = 'TRANSLATE · SERVER OFFLINE';
          log('Tidak bisa terhubung ke backend (cek apakah server Flask sedang berjalan).', 'err');
        } else if (backendOnline === null){
          brandLabel.textContent = 'TRANSLATE · MENYAMBUNG…';
        }
        return;
      }

      // Tampilan meter/threshold: non-kritis, diisolasi supaya kalau salah
      // satu elemennya hilang dari HTML, itu tidak menjatuhkan update
      // status pill + log console di bawah.
      try{
        rmsValueEl.textContent = Number(data.rms).toExponential(2);
        meterFill.style.width = clamp((data.rms / 1.2e-4) * 100, 2, 100) + '%';
        if (thresholdLabel){
          thresholdLabel.textContent = `Threshold RMS: ${Number(data.threshold).toExponential(1)}`;
        }
      } catch(err){
        console.error('Gagal update tampilan meter RMS:', err);
      }

      // Status pill + log console: SELALU dijalankan selama respons /rms
      // berhasil, apa pun yang terjadi pada tampilan meter di atas -- ini
      // yang membuat user tahu proses apa yang sedang berjalan di backend.
      //
      // BUG DITEMUKAN: sebelumnya pill HANYA di-update dari sini kalau
      // `listening` sedang true ATAU phase backend bukan 'idle'. Begitu
      // sebuah proses satu-kali (mis. Upload & Translate, Translate Text,
      // Play TTS Indonesia, atau "Rekam & Simpan Audio" saat autoTtsToggle
      // dimatikan) SELESAI dan backend kembali ke phase 'idle' sementara
      // `listening` masih false, kondisi ini gagal -- pill TIDAK PERNAH
      // diberi tahu bahwa backend sudah selesai. Pill jadi tersangkut di
      // teks "Memproses…"/label proses terakhir (kelas .busy tetap ada)
      // selamanya, padahal logBackendPhaseChange() di baris berikutnya TETAP
      // berjalan tanpa syarat dan mencatat "Backend: proses selesai, kembali
      // siap." -- jadi pill & log console tidak pernah sinkron: log sudah
      // bilang selesai, pill masih menampilkan sedang berjalan.
      //
      // PERBAIKAN: pill sekarang SELALU disamakan dengan phase/label asli
      // dari backend, apa pun nilai `listening` -- backend (pipeline.
      // current_phase) adalah satu-satunya sumber kebenaran untuk SEMUA
      // proses (record-radio, upload, translate-text, tts), jadi input,
      // proses, dan output yang ditampilkan ke user selalu konsisten satu
      // sama lain, apa pun fitur yang sedang dijalankan.
      try{
        applyPhaseToStatusPill(data.phase, data.label);
        logBackendPhaseChange(data.phase, data.label);
      } catch(err){
        console.error('Gagal update status pill/log dari /rms:', err);
      }
    }, 400);
  }

  /* ============================================================
     LISTEN / RECORD RADIO — POST /record-radio, GET /last-audio.wav
     ============================================================ */
  const playRadioBtn = $('playRadioBtn');
  const playLastRecordingBtn = $('playLastRecordingBtn');
  const whisperOutput = $('whisperOutput');
  const translationOutput = $('translationOutput');
  const autoTtsToggle = $('autoTtsToggle');

  let listening = false;

  function playIcon(){
    return '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 5v14l12-7L7 5z" fill="currentColor"/></svg>';
  }
  function pauseIcon(){
    return '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/></svg>';
  }

  async function recordRadioCycle(opts = {}){
    const skipTranslate = !!opts.skipTranslate;
    const deviceIndex = deviceSelect.value;
    if (deviceIndex === '' || isNaN(Number(deviceIndex))){
      log('Pilih perangkat input audio terlebih dahulu.', 'err');
      return false;
    }
    try{
      // PERBAIKAN: log ini dipasang di sini (bukan hanya mengandalkan poll
      // /rms yang jalan tiap 400ms) supaya SETIAP siklus VOX baru pasti
      // tercatat di console begitu diminta ke backend -- tidak bergantung
      // pada waktu polling yang kadang telat menangkap fase yang berubah
      // cepat (mis. saat backend sibuk memproses Whisper/terjemahan).
      log(
        skipTranslate
          ? 'Menunggu sinyal HT untuk direkam & disimpan…'
          : 'Menunggu sinyal HT untuk direkam & diterjemahkan…',
        'info'
      );
      const res = await fetch(`${API_BASE}/record-radio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_index: Number(deviceIndex),
          // Sebelumnya: `thresholdToggle.checked ? 2.0e-5 : 2.0e-5` -- elemen
          // 'thresholdToggle' ini rupanya sudah tidak ada di HTML saat ini,
          // jadi thresholdToggle bernilai null dan `.checked` melempar error
          // "Cannot read properties of null". Lagipula kedua cabangnya
          // menghasilkan nilai yang SAMA, jadi disederhanakan jadi konstanta.
          rms_threshold: 2.0e-5,
          max_sec: 300,
          lang: selectedPapuaLang,
          // "Rekam & Simpan Audio" mengirim skipTranslate=true supaya backend
          // HANYA merekam & menyimpan file audio, tanpa Whisper/terjemahan.
          // "Rekam & Translate Audio" (default) tetap seperti semula.
          skip_translate: skipTranslate
        })
      });
      const data = await safeJson(res);

      if (!data.ok){
        log(`Radio: ${data.error || 'gagal merekam / tidak ada sinyal di atas threshold.'}`, 'warn');
        return true; // bukan error fatal, lanjut mendengarkan siklus berikutnya
      }

      playLastRecordingBtn.hidden = false;
      logLangWarningIfAny(data);

      if (skipTranslate){
        // Rekam & Simpan Audio: JANGAN isi kotak Whisper/Terjemahan, dan
        // jangan trigger auto-TTS -- audio hanya disimpan sebagai rekaman.
        log(`Audio radio direkam & disimpan (durasi ${Number(data.duration_sec ?? 0).toFixed(2)} dtk), tanpa translate.`, 'ok');
        return true;
      }

      whisperOutput.value = data.text_papua || '';
      translationOutput.value = data.text_indonesia || '';
      log(`Whisper (radio): "${truncateForLog(data.text_papua)}"`, 'info');
      log(`Terjemahan radio selesai (durasi ${Number(data.duration_sec ?? 0).toFixed(2)} dtk).`, 'ok');

      if ((autoTtsToggle && autoTtsToggle.checked) && data.text_indonesia){
        await playTtsText(data.text_indonesia);
      }
      return true;
    } catch(err){
      log(`Gagal menghubungi backend saat merekam radio: ${err.message}`, 'err');
      return false; // error jaringan/fatal -> hentikan loop
    }
  }

  // PERBAIKAN: backend sekarang TIDAK PERNAH lagi menghentikan rekaman
  // sendiri saat sinyal PTT/VOX dilepas -- rekaman terus berjalan sampai
  // ada yang memanggil POST /record-radio/stop (lihat cancel_event di
  // app_faster_whisper_lokal.py). Helper ini dipakai baik oleh tombol
  // "Berhenti Mendengarkan" maupun "Rekam & Simpan Audio" untuk mengirim
  // sinyal berhenti manual itu dari web.
  async function stopActiveRecording(){
    try{
      await fetch(`${API_BASE}/record-radio/stop`, { method: 'POST' });
    } catch(err){
      log(`Gagal mengirim sinyal berhenti ke backend: ${err.message}`, 'err');
    }
  }

  async function radioListenLoop(){
    while (listening){
      const shouldContinue = await recordRadioCycle();
      if (!shouldContinue) break;
    }
    if (listening) stopListening();
  }

  function startListening(){
    listening = true;
    playRadioBtn.innerHTML = pauseIcon() + 'Berhenti Mendengarkan';
    deviceSelect.disabled = true;
    statusPill.textContent = 'Menunggu sinyal PTT/VOX dari radio…';
    statusPill.classList.remove('busy');
    log(`Mulai mendengarkan audio radio (perangkat [${deviceSelect.value}])… rekaman tidak lagi berhenti sendiri saat PTT dilepas, tekan "Berhenti Mendengarkan" untuk menghentikan & memproses rekaman.`, 'ok');
    radioListenLoop();
  }

  function stopListening(){
    listening = false;
    // PERBAIKAN: sebelumnya label tombol ini di-set jadi "Putar Audio Papua"
    // saat berhenti mendengarkan, padahal label aslinya (dan seharusnya
    // tetap) adalah "Rekam & Translate Audio" -- baru berubah jadi
    // "Berhenti Mendengarkan" SAAT sedang aktif mendengarkan. "Putar Audio
    // Papua" adalah label tombol lain (playLastRecordingBtn) untuk memutar
    // ulang rekaman terakhir, bukan untuk tombol ini.
    playRadioBtn.innerHTML = playIcon() + 'Rekam &amp; Translate Audio';
    deviceSelect.disabled = false;
    applyPhaseToStatusPill('idle');
    log('Berhenti mendengarkan audio radio.', 'warn');
    // PERBAIKAN: rekaman yang sedang berjalan (atau yang masih menunggu
    // sinyal) tidak lagi berhenti sendiri di backend -- klik tombol ini
    // HARUS memberi tahu backend secara eksplisit supaya siklus yang
    // sedang tertahan di dalam record_radio_rms()/record_radio_web888()
    // langsung selesai (lalu diproses/diterjemahkan) alih-alih menggantung.
    stopActiveRecording();
  }

  playRadioBtn.addEventListener('click', () => {
    if (!listening) startListening();
    else stopListening();
  });

  playLastRecordingBtn.addEventListener('click', () => {
    playAudioUrl(`${API_BASE}/last-audio.wav?t=${Date.now()}`, 'Memutar rekaman radio terakhir…');
  });

  /* ---- Rekam & Simpan Audio (rekam manual, berhenti lewat klik ulang) ---- */
  const recordSaveBtn = $('recordSaveBtn');
  if (recordSaveBtn){
    function saveIcon(){
      return '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 21v-8H7v8M7 3v5h8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    }
    // PERBAIKAN: sebelumnya tombol ini menjalankan SATU siklus rekam yang
    // (dulu) berhenti sendiri begitu PTT dilepas -- klik = tunggu backend
    // auto-stop. Sekarang backend tidak pernah auto-stop lagi, jadi tombol
    // ini diubah jadi SAKLAR manual: klik pertama mulai rekam & menunggu
    // sinyal, klik kedua (selagi merekam/menunggu) mengirim sinyal berhenti
    // ke backend supaya rekaman selesai & disimpan.
    let recordSaveActive = false;
    let recordSaveCyclePromise = null;

    recordSaveBtn.addEventListener('click', async () => {
      if (listening){
        log('Sedang mendengarkan radio — hentikan dahulu sebelum merekam & menyimpan.', 'warn');
        return;
      }

      if (!recordSaveActive){
        recordSaveActive = true;
        recordSaveBtn.innerHTML = pauseIcon() + 'Berhenti &amp; Simpan Audio';
        statusPill.textContent = 'Menunggu sinyal PTT untuk direkam & disimpan…';
        statusPill.classList.remove('busy');
        log('Merekam & menyimpan audio radio (tanpa translate)… klik "Berhenti & Simpan Audio" untuk menghentikan secara manual.', 'info');
        recordSaveCyclePromise = recordRadioCycle({ skipTranslate: true });
        return;
      }

      // Sudah aktif merekam/menunggu -> klik kedua ini berarti berhenti manual.
      recordSaveBtn.disabled = true;
      try{
        await stopActiveRecording();
        await recordSaveCyclePromise;
      } finally {
        recordSaveActive = false;
        recordSaveCyclePromise = null;
        recordSaveBtn.disabled = false;
        recordSaveBtn.innerHTML = saveIcon() + 'Rekam &amp; Simpan Audio';
        applyPhaseToStatusPill('idle');
      }
    });
  }

  /* ---- Pilih Bahasa Papua (dikirim sebagai field "lang" ke backend) ---- */
  const papuaLangSelect = $('papuaLangSelect');
  const papuaLangSearch = $('papuaLangSearch');
  let selectedPapuaLang = papuaLangSelect ? papuaLangSelect.value : '';
  // Set label pill sesuai bahasa default saat halaman pertama kali dimuat.
  if (!statusPill.classList.contains('busy')) statusPill.textContent = papuaSiapLabel();

  async function applyPapuaLangChange(lang, label){
    log(`Mengganti translate ke Bahasa ${label}…`, 'info');
    try{
      const res = await fetch(`${API_BASE}/set-lang`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang })
      });
      const data = await safeJson(res);
      if (!data.ok){
        log(`Gagal mengganti ke Bahasa ${label}: ${data.error || 'terjadi kesalahan.'}`, 'err');
        return;
      }
      if (data.changed === false){
        log(`Bahasa ${label} sudah aktif (tidak ada perubahan).`, 'info');
      } else {
        log(`Berhasil mengganti translate ke Bahasa ${label}.`, 'ok');
      }
    } catch(err){
      log(`Gagal menghubungi backend saat mengganti bahasa: ${err.message}`, 'err');
    }
  }

  // Bersihkan input & output translate sebelumnya (Whisper, hasil terjemahan,
  // teks Papua, berkas unggahan) begitu bahasa Papua diganti -- supaya tidak
  // ada teks/hasil dari bahasa sebelumnya yang tertinggal di layar dan
  // membingungkan mana yang terjemahan bahasa baru.
  function resetTranslateWorkspace(){
    whisperOutput.value = '';
    translationOutput.value = '';
    if (papuaTextInput) papuaTextInput.value = '';
    if (audioFile) audioFile.value = '';
    if (fileNameEl) fileNameEl.textContent = 'Belum ada berkas dipilih';
    uploadPreviewUrl = null;
    uploadPreviewToken++; // buang hasil pratinjau upload yang mungkin masih berjalan (basi)
    playLastRecordingBtn.hidden = true;
    log('Input & output translate sebelumnya dibersihkan karena ganti bahasa.', 'info');
  }

  if (papuaLangSelect){
    papuaLangSelect.addEventListener('change', () => {
      selectedPapuaLang = papuaLangSelect.value;
      const opt = papuaLangSelect.options[papuaLangSelect.selectedIndex];
      const label = opt ? opt.textContent : selectedPapuaLang;
      log(`Bahasa Papua dipilih: ${label}`, 'info');
      resetTranslateWorkspace();
      if (!statusPill.classList.contains('busy')) statusPill.textContent = papuaSiapLabel();
      applyPapuaLangChange(selectedPapuaLang, label);
    });
  }
  if (papuaLangSearch && papuaLangSelect){
    papuaLangSearch.addEventListener('input', () => {
      const q = papuaLangSearch.value.trim().toLowerCase();
      Array.from(papuaLangSelect.options).forEach(opt => {
        opt.hidden = q.length > 0 && !opt.textContent.toLowerCase().includes(q);
      });
    });
  }

  /* ============================================================
     UPLOAD AUDIO — POST /preview-upload-audio, /upload-audio
     ============================================================ */
  const audioFile = $('audioFile');
  const fileNameEl = $('fileName');
  const playUploadBtn = $('playUploadBtn');
  const uploadTranslateBtn = $('uploadTranslateBtn');

  let uploadPreviewUrl = null;
  // PERBAIKAN: sebelumnya kalau berkas diganti dua kali dengan cepat, dua
  // permintaan pratinjau ke backend berjalan bersamaan (race condition) --
  // jika respons untuk berkas yang LAMA kembali belakangan, ia menimpa
  // uploadPreviewUrl milik berkas yang BARU, sehingga saat tombol Play
  // ditekan yang terdengar justru audio dari berkas lama. Token di bawah
  // memastikan hanya respons dari pemilihan berkas TERBARU yang dipakai;
  // respons yang sudah basi (berkas sudah diganti lagi) otomatis dibuang.
  let uploadPreviewToken = 0;

  async function prepareUploadPreview(file){
    uploadPreviewUrl = null;
    const myToken = ++uploadPreviewToken;
    // PERBAIKAN: sebelumnya proses ini (kirim berkas ke backend untuk
    // dibuatkan pratinjau) tidak terlihat sama sekali di status pill --
    // hanya hasil akhirnya yang tercatat di log. Sekarang pill juga
    // menunjukkan progres saat sedang mengunggah/menyiapkan pratinjau.
    statusPill.textContent = 'Menyiapkan Pratinjau…';
    statusPill.classList.add('busy');
    try{
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`${API_BASE}/preview-upload-audio`, { method: 'POST', body: fd, cache: 'no-store' });
      const data = await safeJson(res);
      if (myToken !== uploadPreviewToken) return; // berkas sudah diganti lagi, buang hasil yang basi ini
      if (!data.ok){
        log(`Gagal menyiapkan pratinjau audio: ${data.error}`, 'err');
        return;
      }
      uploadPreviewUrl = `${API_BASE}${data.audio_url}`;
      log('Pratinjau audio unggahan siap diputar.', 'ok');
    } catch(err){
      if (myToken !== uploadPreviewToken) return;
      log(`Gagal mengirim berkas untuk pratinjau: ${err.message}`, 'err');
    } finally {
      if (myToken === uploadPreviewToken){
        statusPill.textContent = papuaSiapLabel();
        statusPill.classList.remove('busy');
      }
    }
  }

  audioFile.addEventListener('change', () => {
    if (!audioFile.files.length){
      fileNameEl.textContent = 'Belum ada berkas dipilih';
      uploadPreviewUrl = null;
      return;
    }
    const file = audioFile.files[0];
    fileNameEl.textContent = file.name;
    log(`Berkas dipilih: ${file.name}`, 'info');
    prepareUploadPreview(file);
  });

  playUploadBtn.addEventListener('click', () => {
    if (!audioFile.files.length){
      log('Pilih berkas audio terlebih dahulu.', 'err');
      return;
    }
    if (!uploadPreviewUrl){
      log('Pratinjau belum siap, tunggu sebentar lalu coba lagi.', 'warn');
      return;
    }
    playAudioUrl(uploadPreviewUrl, `Memutar berkas: ${audioFile.files[0].name}`);
  });

  uploadTranslateBtn.addEventListener('click', async () => {
    if (!audioFile.files.length){
      log('Tidak ada berkas untuk diunggah.', 'err');
      return;
    }
    const file = audioFile.files[0];
    uploadTranslateBtn.disabled = true;
    statusPill.textContent = 'Memproses…';
    statusPill.classList.add('busy');
    log(`Mengunggah dan memproses: ${file.name}…`, 'info');

    try{
      const fd = new FormData();
      fd.append('file', file);
      fd.append('lang', selectedPapuaLang);
      const res = await fetch(`${API_BASE}/upload-audio`, { method: 'POST', body: fd });
      const data = await safeJson(res);

      if (!data.ok){
        log(`Gagal memproses berkas: ${data.error}`, 'err');
        return;
      }

      whisperOutput.value = data.text_papua || '';
      translationOutput.value = data.text_indonesia || '';
      logLangWarningIfAny(data);
      log('Terjemahan selesai (berkas unggahan).', 'ok');
      playLastRecordingBtn.hidden = false; // /upload-audio juga mengisi last_audio_clean di backend

      if ((autoTtsToggle && autoTtsToggle.checked) && data.text_indonesia){
        await playTtsText(data.text_indonesia);
      }
    } catch(err){
      log(`Gagal menghubungi backend: ${err.message}`, 'err');
    } finally {
      uploadTranslateBtn.disabled = false;
      statusPill.textContent = papuaSiapLabel();
      statusPill.classList.remove('busy');
    }
  });

  /* ============================================================
     TEXT TRANSLATE — POST /translate-text
     ============================================================ */
  const papuaTextInput = $('papuaTextInput');
  const translateTextBtn = $('translateTextBtn');

  translateTextBtn.addEventListener('click', async () => {
    const text = papuaTextInput.value.trim();
    if (!text){
      log('Ketik teks Papua sebelum menerjemahkan.', 'err');
      papuaTextInput.focus();
      return;
    }

    whisperOutput.value = text;
    translateTextBtn.disabled = true;
    statusPill.textContent = 'Menerjemahkan…';
    statusPill.classList.add('busy');

    try{
      const res = await fetch(`${API_BASE}/translate-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, lang: selectedPapuaLang })
      });
      const data = await safeJson(res);

      if (!data.ok){
        log(`Gagal menerjemahkan: ${data.error}`, 'err');
        return;
      }

      translationOutput.value = data.output_indonesia || '';
      logLangWarningIfAny(data);
      log('Terjemahan selesai: Papua → Indonesia.', 'ok');

      if ((autoTtsToggle && autoTtsToggle.checked) && data.output_indonesia){
        await playTtsText(data.output_indonesia);
      }
    } catch(err){
      log(`Gagal menghubungi backend: ${err.message}`, 'err');
    } finally {
      translateTextBtn.disabled = false;
      statusPill.textContent = papuaSiapLabel();
      statusPill.classList.remove('busy');
    }
  });

  /* ============================================================
     SPEKTRUM & WATERFALL REAL-TIME (dari rtl_tcp lewat backend)
     ============================================================ */
  const spectrumCanvas = $('spectrumCanvas');
  const waterfallCanvas = $('waterfallCanvas');
  const scaleCanvas = $('scaleCanvas');
  const specCtx = spectrumCanvas.getContext('2d');
  const wfCtx = waterfallCanvas.getContext('2d');
  const scaleCtx = scaleCanvas ? scaleCanvas.getContext('2d') : null;
  const spectrumToggleBtn = $('spectrumToggleBtn');
  const spectrumStatusPill = $('spectrumStatusPill');
  const rtltcpDot = $('rtltcpDot');
  const rtltcpStatusText = $('rtltcpStatusText');
  const rtltcpHostInput = $('rtltcpHost');
  const rtltcpPortInput = $('rtltcpPort');
  const rtltcpApplyBtn = $('rtltcpApplyBtn');
  const rtltcpStopBtn = $('rtltcpStopBtn');
  const axisMinEl = $('axisMin');
  const axisCenterEl = $('axisCenter');
  const axisMaxEl = $('axisMax');
  const zoomSlider = $('zoomSlider');
  const zoomValueEl = $('zoomValue');
  const contrastSlider = $('contrastSlider');
  const contrastValueEl = $('contrastValue');

  let spectrumRunning = false;
  let spectrumPollTimer = null;
  let waterfallInitialized = false;
  let activeSpectrumSource = null; // 'web888' | 'sdrpp' | null
  // PERBAIKAN BUG (lihat screenshot laporan): sebelumnya polling /spectrum
  // jalan lewat setInterval tetap 50ms TANPA guard overlap dan TANPA
  // backoff. Saat backend mati/restart lama, 502 menumpuk terus tiap 50ms
  // sampai akhirnya socket OS kehabisan buffer (net::ERR_NO_BUFFER_SPACE)
  // seperti di log console. Sekarang polling dijadwalkan ulang sendiri
  // (bukan interval tetap) + backoff bertahap saat gagal beruntun, lalu
  // kembali ke ~20fps normal begitu backend online lagi.
  let spectrumPollInFlight = false;
  let spectrumFailStreak = 0;
  const SPECTRUM_POLL_BASE_MS = 50; // ~20fps, selaras SPECTRUM_TARGET_FPS backend
  const SPECTRUM_POLL_MAX_MS = 2000;
  const SPECTRUM_POLL_BACKOFF_START = 6; // toleransi ~6 kegagalan dulu sebelum backoff

  /* ------------------------------------------------------------
     AUDIO LIVE HT (khusus sumber Web-888) — supaya kedengaran
     suaranya sendiri saat speech di HT, selagi melihat
     frekuensi/waterfall di Set Radio. Untuk sumber SDR++, audio
     sudah keluar lewat speaker PC via SDR++ sendiri, jadi tidak
     perlu diputar ulang di browser.

     Teknik: polling GET /web888/audio-chunk (bukan WebSocket, biar
     konsisten dengan pola /rms & /spectrum yang sudah ada), lalu
     jadwalkan tiap potongan PCM secara berurutan lewat Web Audio
     API (AudioBufferSourceNode) supaya sambung-menyambung tanpa
     jeda/klik, mirip pemutaran streaming radio internet.
     ------------------------------------------------------------ */
  let web888AudioCtx = null;
  let web888AudioNextStart = 0;
  let web888AudioPollTimer = null;
  let web888AudioActive = false;

  function ensureWeb888AudioCtx(){
    if (!web888AudioCtx){
      const Ctx = window.AudioContext || window.webkitAudioContext;
      web888AudioCtx = new Ctx();
    }
    if (web888AudioCtx.state === 'suspended'){
      web888AudioCtx.resume().catch(() => {});
    }
    return web888AudioCtx;
  }

  function base64ToInt16Array(b64){
    const binary = atob(b64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
    return new Int16Array(bytes.buffer);
  }

  async function pollWeb888Audio(){
    // PERBAIKAN: sebelumnya di sini ada `if (listening) return;` yang
    // menghentikan monitor audio live setiap kali loop "Rekam & Translate"
    // (atau "Rekam & Simpan Audio") aktif -- akibatnya suara HT SAMA SEKALI
    // tidak terdengar di browser selama proses rekam/translate berjalan,
    // padahal justru saat itulah operator paling butuh dengar suaranya
    // sendiri (untuk tahu PTT sudah "masuk" atau belum). Guard itu dulunya
    // untuk mencegah rebutan buffer dengan /record-radio, tapi backend
    // sekarang SUDAH memakai dua buffer terpisah: pop_audio() untuk
    // /record-radio (Whisper) dan pop_monitor_audio() khusus endpoint ini
    // (lihat komentar /web888/audio-chunk di app_faster_whisper_lokal.py),
    // jadi keduanya tidak lagi berebut. Monitor ini sekarang dibiarkan
    // tetap jalan terus -- baik saat idle, saat "Rekam & Translate Audio",
    // maupun saat "Rekam & Simpan Audio" -- selama koneksi Web-888 aktif,
    // persis seperti radio HT sungguhan yang suaranya selalu terdengar
    // dari speaker selama PTT ditekan.
    try{
      const res = await fetch(`${API_BASE}/web888/audio-chunk`);
      const data = await safeJson(res);
      if (!data.ok || !data.has_audio) return;

      const int16 = base64ToInt16Array(data.pcm16_base64);
      if (int16.length === 0) return;

      const ctx = ensureWeb888AudioCtx();
      const buffer = ctx.createBuffer(1, int16.length, data.sample_rate);
      const channel = buffer.getChannelData(0);
      for (let i = 0; i < int16.length; i++) channel[i] = int16[i] / 32768.0;

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);

      // Jadwalkan sambung-menyambung: kalau jadwal sebelumnya sudah lewat
      // (mis. jeda jaringan), mulai lagi dari "sekarang" supaya tidak makin
      // ketinggalan (drift) dari waktu nyata.
      const now = ctx.currentTime;
      let startAt = Math.max(web888AudioNextStart, now);

      // PERBAIKAN DELAY/GEMA YANG MAKIN LAMA MAKIN PANJANG:
      // Sebelum ini, kalau antrian sempat menumpuk di DEPAN waktu nyata
      // (mis. sesaat setelah jeda jaringan/tab browser sibuk, server
      // sempat mem-buffer sisa audio HT beberapa ratus ms), kode ini
      // hanya menambah terus `web888AudioNextStart` tanpa pernah
      // memangkasnya kembali -- backlog itu tidak pernah "dibuang", jadi
      // jeda antara suara asli HT dan yang kedengaran di browser terus
      // menumpuk dan tidak pernah pulih sendiri, makin lama dipakai makin
      // parah. Sekarang: kalau antrian sudah menumpuk lebih dari
      // MAX_LOOKAHEAD_SECONDS di depan waktu nyata, buang backlog itu dan
      // mulai lagi dari "sekarang" -- persis seperti penanganan saat
      // ketinggalan di atas, tapi untuk arah sebaliknya.
      //
      // Nilai ini SENGAJA dibuat sekecil mungkin (namun tetap aman dari
      // klik/putus-putus) supaya delay selalu mendekati minimum praktis --
      // TIDAK bisa dibuat 0 mutlak karena Web Audio API tetap butuh sedikit
      // "napas" ke depan supaya penjadwalan antar-potongan audio tidak
      // bercelah/berbunyi klik.
      const MAX_LOOKAHEAD_SECONDS = 0.15;
      if (startAt - now > MAX_LOOKAHEAD_SECONDS) {
        startAt = now;
      }

      src.start(startAt);
      web888AudioNextStart = startAt + buffer.duration;
    } catch(err){
      // Diamkan -- ini polling latar belakang, tidak perlu bikin log berisik.
    }
  }

  function startWeb888AudioMonitor(){
    if (web888AudioActive) return;
    web888AudioActive = true;
    const ctx = ensureWeb888AudioCtx();
    web888AudioNextStart = ctx.currentTime;
    if (web888AudioPollTimer) clearInterval(web888AudioPollTimer);
    // Interval polling diperkecil (dari 150ms) supaya potongan audio yang
    // diambil tiap kali lebih kecil & lebih sering -- delay dari sisi ini
    // jadi lebih dekat ke minimum praktis. Turunkan lagi kalau perangkat
    // masih kuat (CPU/koneksi lokal), tapi terlalu kecil (<30ms) berisiko
    // membebani server dengan request yang berlebihan tanpa manfaat nyata.
    web888AudioPollTimer = setInterval(pollWeb888Audio, 60);
  }

  function stopWeb888AudioMonitor(){
    web888AudioActive = false;
    if (web888AudioPollTimer) clearInterval(web888AudioPollTimer);
    web888AudioPollTimer = null;
  }
  let scopeZoom = zoomSlider ? Number(zoomSlider.value) : 1;
  let scopeContrast = contrastSlider ? Number(contrastSlider.value) : 1;

  // --- Zoom ASLI di sisi server (Web-888/KiwiSDR) ---
  // baseWfSpanHz: lebar rentang (Hz) saat zoom masih 1x, direkam sekali waktu
  // spektrum baru dimulai. Dipakai sebagai acuan supaya span yang diminta ke
  // server selalu dihitung dari titik awal yang sama, terlepas dari span
  // saat ini (yang mungkin sudah berubah akibat zoom sebelumnya).
  let baseWfSpanHz = null;
  // true kalau permintaan zoom terakhir berhasil ditangani server (span
  // benar-benar diperkecil di sumbernya) -- kalau true, potongan array di
  // browser (lihat drawSpectrumFrame) TIDAK perlu dipotong lagi, supaya
  // tidak dobel-zoom (server sudah zoom, browser jangan zoom lagi).
  let serverZoomActive = false;
  let zoomApplyTimer = null;

  async function applyServerZoom(zoomFactor){
    if (activeSpectrumSource !== 'web888' || !baseWfSpanHz) return;
    const wfSpanHz = Math.max(1000, Math.round(baseWfSpanHz / zoomFactor));
    try{
      const res = await fetch(`${API_BASE}/spectrum/zoom`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wf_span_hz: wfSpanHz }),
      });
      const data = await safeJson(res);
      serverZoomActive = !!(data && data.ok && data.supported);
    } catch(err){
      serverZoomActive = false;
    }
  }

  // Kurva kontras sederhana yang berputar di sekitar titik tengah (0.5),
  // dipakai untuk mempertajam/melunakkan gradasi warna waterfall.
  function applyContrast(norm, contrast){
    return clamp(0.5 + (norm - 0.5) * contrast, 0, 1);
  }

  if (zoomSlider){
    zoomSlider.addEventListener('input', () => {
      scopeZoom = Number(zoomSlider.value);
      zoomValueEl.textContent = scopeZoom.toFixed(1) + 'x';
      setSliderFill(zoomSlider);
      waterfallInitialized = false; // lebar tampilan berubah, mulai ulang waterfall
      if (zoomApplyTimer) clearTimeout(zoomApplyTimer);
      zoomApplyTimer = setTimeout(() => applyServerZoom(scopeZoom), 180);
    });
  }
  if (contrastSlider){
    contrastSlider.addEventListener('input', () => {
      scopeContrast = Number(contrastSlider.value);
      contrastValueEl.textContent = scopeContrast.toFixed(1) + 'x';
      setSliderFill(contrastSlider);
    });
  }

  function resizeScopeCanvases(){
    const dpr = window.devicePixelRatio || 1;
    [scaleCanvas, spectrumCanvas, waterfallCanvas].forEach(cv => {
      if (!cv) return;
      const cssWidth = cv.clientWidth;
      const cssHeight = cv.clientHeight;
      // PERBAIKAN BUG: sebelumnya kalau cssWidth/cssHeight bernilai 0 (kanvas
      // sedang tersembunyi -- mis. halaman Set Radio belum aktif saat event
      // 'resize' window terpicu), kode ini jatuh ke fallback sembarang
      // (600 / 180), lalu MENIMPA atribut width/height kanvas dengan angka
      // yang tidak proporsional terhadap ukuran aslinya. Sekarang, dengan
      // .scope-canvas sudah punya height CSS tetap (lihat style.css), ukuran
      // TAMPILAN kanvas tidak lagi bisa rusak -- tapi resolusi gambar
      // internal tetap sebaiknya tidak diubah sama sekali selagi kanvas
      // tersembunyi, jadi di sini kita cukup lewati (skip) kanvas itu untuk
      // siklus resize kali ini; ia akan diukur ulang dengan benar begitu
      // terlihat lagi (dipanggil lagi dari showPage()).
      if (!cssWidth || !cssHeight) return;
      const minH = cv === scaleCanvas ? 24 : 60;
      const targetW = Math.max(200, Math.round(cssWidth * dpr));
      const targetH = Math.max(minH, Math.round(cssHeight * dpr));
      if (cv.width !== targetW || cv.height !== targetH){
        cv.width = targetW;
        cv.height = targetH;
        waterfallInitialized = false;
      }
    });
    if (scaleCtx) drawFreqRuler(0, 0, false);
  }
  window.addEventListener('resize', () => { resizeScopeCanvases(); waterfallInitialized = false; });

  // Bilah skala/ruler frekuensi di atas grafik spektrum & waterfall, meniru
  // gaya pada gambar referensi: latar abu-abu metalik, garis takik (tick)
  // mayor (berlabel MHz) & minor (tanpa label), plus penanda hijau berbentuk
  // trapesium yang menunjukkan frekuensi + bandwidth yang sedang di-tune.
  function drawFreqRuler(centerHtHz, halfHz, hasAxisFlag){
    if (!scaleCtx) return;
    const w = scaleCanvas.width;
    const h = scaleCanvas.height;
    if (!w || !h) return;
    scaleCtx.clearRect(0, 0, w, h);

    const bg = scaleCtx.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, '#6e7378');
    bg.addColorStop(0.45, '#4b4f53');
    bg.addColorStop(1, '#2a2d30');
    scaleCtx.fillStyle = bg;
    scaleCtx.fillRect(0, 0, w, h);
    scaleCtx.fillStyle = 'rgba(255,255,255,0.10)';
    scaleCtx.fillRect(0, 0, w, Math.max(1, Math.round(h * 0.06)));

    if (!hasAxisFlag || !halfHz) return;

    const lowHz = centerHtHz - halfHz;
    const highHz = centerHtHz + halfHz;
    const spanHz = 2 * halfHz;
    const hzToX = (hz) => ((hz - lowHz) / spanHz) * w;

    // Target ~10 label utama melintasi lebar bilah -> step "rapi" (1/2/5 x 10^n)
    const majorStep = niceStep(spanHz / 10);
    const minorStep = majorStep / 5;
    const dpr = window.devicePixelRatio || 1;

    const minorTickH = Math.max(3, Math.round(h * 0.16));
    const majorTickH = Math.max(6, Math.round(h * 0.32));

    // tick minor (tanpa label)
    scaleCtx.lineWidth = Math.max(1, Math.round(dpr));
    scaleCtx.strokeStyle = 'rgba(220,230,230,0.45)';
    let f0 = Math.ceil(lowHz / minorStep) * minorStep;
    for (let f = f0; f <= highHz; f += minorStep){
      if (Math.abs(Math.round(f / majorStep) * majorStep - f) < minorStep * 0.01) continue; // sudah jadi major
      const x = hzToX(f);
      scaleCtx.beginPath();
      scaleCtx.moveTo(x, h);
      scaleCtx.lineTo(x, h - minorTickH);
      scaleCtx.stroke();
    }

    // tick major + label MHz
    const fontPx = Math.max(9, Math.round(10 * dpr));
    scaleCtx.font = `600 ${fontPx}px sans-serif`;
    scaleCtx.textBaseline = 'top';
    scaleCtx.lineWidth = Math.max(1, Math.round(1.2 * dpr));
    scaleCtx.strokeStyle = 'rgba(235,245,245,0.85)';
    let f1 = Math.ceil(lowHz / majorStep) * majorStep;
    for (let f = f1; f <= highHz + 1e-6; f += majorStep){
      const x = hzToX(f);
      scaleCtx.beginPath();
      scaleCtx.moveTo(x, h);
      scaleCtx.lineTo(x, h - majorTickH);
      scaleCtx.stroke();

      const label = formatMHzForStep(f, majorStep) + ' MHz';
      scaleCtx.textAlign = x < 24 ? 'left' : (x > w - 24 ? 'right' : 'center');
      scaleCtx.fillStyle = 'rgba(235,245,245,0.92)';
      scaleCtx.fillText(label, x, Math.round(h * 0.06));
    }

    // penanda hijau (trapesium) = frekuensi + bandwidth yang sedang di-tune
    if (typeof currentFreq === 'number' && currentFreq >= lowHz && currentFreq <= highHz){
      const bw = (typeof currentBw === 'number' && currentBw > 0) ? currentBw : (spanHz * 0.01);
      const xLow = clamp(hzToX(currentFreq - bw / 2), 0, w);
      const xHigh = clamp(hzToX(currentFreq + bw / 2), 0, w);
      if (xHigh > xLow){
        const topY = 1;
        const flatY = topY + Math.max(3, Math.round(h * 0.24));
        const slant = Math.min((xHigh - xLow) * 0.4, 6);
        scaleCtx.save();
        scaleCtx.beginPath();
        scaleCtx.moveTo(xLow, flatY);
        scaleCtx.lineTo(xLow + slant, topY);
        scaleCtx.lineTo(xHigh - slant, topY);
        scaleCtx.lineTo(xHigh, flatY);
        scaleCtx.strokeStyle = '#3ee85a';
        scaleCtx.lineWidth = Math.max(1.5, 1.5 * dpr);
        scaleCtx.shadowColor = 'rgba(62,232,90,0.7)';
        scaleCtx.shadowBlur = 4;
        scaleCtx.stroke();
        scaleCtx.shadowBlur = 0;
        scaleCtx.restore();
      }
    }
  }

  function drawSpectrumFrame(dbArrayFull, centerFreqHz, sampleRateHzFull){
    const w = spectrumCanvas.width;
    const h = spectrumCanvas.height;

    // --- ZOOM: ambil potongan array di sekitar titik tengah sesuai faktor zoom,
    // supaya makin besar zoom-nya, makin sempit rentang frekuensi yang tampil
    // (skala frekuensi terlihat lebih "dalam"/detail).
    const fullLen = dbArrayFull.length;
    let dbArray = dbArrayFull;
    let sampleRateHz = sampleRateHzFull;
    let cropZoom = scopeZoom;
    if (activeSpectrumSource === 'web888' && serverZoomActive && baseWfSpanHz && sampleRateHzFull){
      // Server Web-888 sudah mempersempit span SUNGGUHAN (resolusi Hz/bin
      // beneran naik, bukan cuma direntang di layar). KiwiSDR cuma punya
      // level zoom kelipatan pangkat 2, jadi span aktual kadang tidak
      // persis sama dengan target -- di sini cuma memangkas SISANYA saja,
      // supaya nilai slider tetap presisi tanpa dobel-zoom di atas zoom
      // yang server sudah lakukan.
      const desiredSpanHz = baseWfSpanHz / scopeZoom;
      cropZoom = clamp(sampleRateHzFull / desiredSpanHz, 1, scopeZoom);
    }
    if (cropZoom > 1.02 && fullLen > 8){
      const sliceLen = Math.max(8, Math.round(fullLen / cropZoom));
      const start = Math.floor((fullLen - sliceLen) / 2);
      dbArray = dbArrayFull.slice(start, start + sliceLen);
      if (sampleRateHzFull) sampleRateHz = sampleRateHzFull / cropZoom;
    }

    // --- Metadata sumbu frekuensi, dihitung SEKALI di awal supaya bisa dipakai
    // baik untuk overlay bandwidth (digambar sebelum garis spektrum, jadi
    // "di belakang" garisnya) maupun untuk label sumbu (di bawah nanti).
    // "centerFreqHz" dari backend adalah frekuensi RADIO aktual (yang benar-benar
    // di-tune di dongle/Web-888); dikurangi offset supaya sumbu yang tampil ke
    // user selalu dalam skala frekuensi HT, konsisten dengan panel Frekuensi.
    //
    // PERBAIKAN: sebelumnya sumbu tampilan DIPAKSA tetap 50 MHz total (lihat
    // riwayat komentar lama), padahal data ASLI yang benar-benar ditangkap dari
    // rtl_tcp/Web-888 jauh lebih sempit (cuma selebar sample rate-nya, mis. ~2-3
    // MHz) -- akibatnya grafik & waterfall cuma tampil sebagai jalur sempit di
    // tengah kotak, sementara sisi kiri-kanannya kosong/noise tanpa data
    // sungguhan. Sekarang sumbu tampilan (axisHalfHz) disamakan dengan bentang
    // data asli (dataHalfHz) supaya data SELALU digambar memenuhi lebar kotak
    // dari ujung kiri sampai ujung kanan. Efek baiknya juga membetulkan slider
    // Zoom: saat di-slider ke atas (fullLen dipotong makin sempit di sekitar
    // titik tengah, lihat blok ZOOM di atas), potongan yang makin sempit itu
    // ikut memenuhi lebar kotak yang SAMA -- inilah definisi "zoom in" yang
    // benar (detail makin besar/dekat), bukan makin mengecil seperti sebelumnya.
    // Sumbu selalu mengikuti bentang data asli yang benar-benar ditangkap
    // dari sumber (rtl_tcp/Web-888) -- lihat "PERBAIKAN" di atas.
    const hasAxis = !!(centerFreqHz && sampleRateHz);
    const dataHalfHz = hasAxis ? sampleRateHz / 2 : 0;
    const axisHalfHz = dataHalfHz;
    const axisCenterHtHz = hasAxis ? (centerFreqHz - freqOffsetHz) : 0;
    const htFreqToX = (hz) => ((hz - (axisCenterHtHz - axisHalfHz)) / (2 * axisHalfHz)) * w;

    drawFreqRuler(axisCenterHtHz, axisHalfHz, hasAxis);

    // --- garis spektrum ---
    specCtx.clearRect(0, 0, w, h);
    specCtx.fillStyle = '#030b0c';
    specCtx.fillRect(0, 0, w, h);

    // --- overlay bandwidth: bayangan putih transparan menandai rentang frekuensi
    // yang benar-benar diambil untuk demodulasi suara (sesuai panel Bandwidth),
    // digambar SEBELUM garis spektrum supaya garis & grid tetap terlihat di atasnya.
    if (hasAxis && typeof currentFreq === 'number' && typeof currentBw === 'number' && currentBw > 0){
      const bwLowHz = currentFreq - currentBw / 2;
      const bwHighHz = currentFreq + currentBw / 2;
      const xLow = clamp(htFreqToX(bwLowHz), 0, w);
      const xHigh = clamp(htFreqToX(bwHighHz), 0, w);
      if (xHigh > xLow){
        specCtx.save();
        specCtx.fillStyle = 'rgba(255,255,255,0.14)';
        specCtx.fillRect(xLow, 0, xHigh - xLow, h);
        specCtx.strokeStyle = 'rgba(255,255,255,0.32)';
        specCtx.lineWidth = 1;
        specCtx.strokeRect(xLow + 0.5, 0.5, Math.max(xHigh - xLow - 1, 0), h - 1);
        specCtx.restore();
      }
    }

    // grid horizontal tipis
    specCtx.strokeStyle = 'rgba(88,214,214,0.12)';
    specCtx.lineWidth = 1;
    for (let i = 1; i < 4; i++){
      const y = (h / 4) * i;
      specCtx.beginPath();
      specCtx.moveTo(0, y);
      specCtx.lineTo(w, y);
      specCtx.stroke();
    }

    const n = dbArray.length;
    if (n > 1){
      let minDb = Infinity, maxDb = -Infinity;
      for (let i = 0; i < n; i++){
        if (dbArray[i] < minDb) minDb = dbArray[i];
        if (dbArray[i] > maxDb) maxDb = dbArray[i];
      }
      if (!isFinite(minDb) || !isFinite(maxDb)) {
        minDb = -100; maxDb = 0;
      } else if (maxDb - minDb < 6) {
        // Data nyaris rata (mis. HT tidak transmit, cuma noise lantai).
        // JANGAN diganti ke rentang absolut (-100..0) -- skala dB di aplikasi
        // ini (lihat web888_client.py: db = raw-255+cal_db) bisa jauh di luar
        // -100..0, jadi kalau diganti absolut, garis malah ke-clamp mentok di
        // tepi atas/bawah dan kelihatan "hilang". Di sini rentang dilebarkan
        // di SEKITAR nilai asli supaya garis tetap tampil proporsional.
        const mid = (minDb + maxDb) / 2;
        minDb = mid - 3; maxDb = mid + 3;
      }
      const pad = (maxDb - minDb) * 0.08;
      minDb -= pad; maxDb += pad;

      specCtx.beginPath();
      specCtx.strokeStyle = '#3fe0e0';
      specCtx.lineWidth = 1.5;
      specCtx.shadowColor = 'rgba(63,224,224,0.55)';
      specCtx.shadowBlur = 6;
      let started = false;
      let firstX = 0, lastX = w;
      for (let i = 0; i < n; i++){
        let x;
        if (hasAxis && dataHalfHz > 0){
          const freqHere = axisCenterHtHz - dataHalfHz + (i / (n - 1)) * (2 * dataHalfHz);
          x = htFreqToX(freqHere);
        } else {
          x = (i / (n - 1)) * w;
        }
        const norm = clamp((dbArray[i] - minDb) / (maxDb - minDb), 0, 1);
        const y = h - norm * h;
        if (!started) { specCtx.moveTo(x, y); started = true; firstX = x; } else { specCtx.lineTo(x, y); }
        lastX = x;
      }
      specCtx.stroke();
      specCtx.shadowBlur = 0;

      // isi bawah garis (fill halus) — cuma di rentang x tempat data asli
      // benar-benar tergambar, bukan seluruh lebar kanvas 50 MHz.
      specCtx.lineTo(lastX, h);
      specCtx.lineTo(firstX, h);
      specCtx.closePath();
      const grad = specCtx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, 'rgba(63,224,224,0.25)');
      grad.addColorStop(1, 'rgba(63,224,224,0.0)');
      specCtx.fillStyle = grad;
      specCtx.fill();

      // simpan untuk keperluan klik-untuk-tuning
      spectrumCanvas.dataset.minDb = String(minDb);
      spectrumCanvas.dataset.maxDb = String(maxDb);
    }

    // --- geser waterfall ke bawah 1 baris, gambar baris baru di atas ---
    const wfW = waterfallCanvas.width;
    const wfH = waterfallCanvas.height;
    if (!waterfallInitialized){
      wfCtx.fillStyle = '#030b0c';
      wfCtx.fillRect(0, 0, wfW, wfH);
      waterfallInitialized = true;
    }
    wfCtx.drawImage(waterfallCanvas, 0, 0, wfW, wfH - 1, 0, 1, wfW, wfH - 1);

    const rowImg = wfCtx.createImageData(wfW, 1);
    let minDb2 = Infinity, maxDb2 = -Infinity;
    for (let i = 0; i < n; i++){
      if (dbArray[i] < minDb2) minDb2 = dbArray[i];
      if (dbArray[i] > maxDb2) maxDb2 = dbArray[i];
    }
    if (!isFinite(minDb2) || !isFinite(maxDb2)) {
      minDb2 = -100; maxDb2 = 0;
    } else if (maxDb2 - minDb2 < 6) {
      // Sama seperti di grafik spektrum di atas: jangan diganti rentang
      // absolut -- lebarkan di sekitar nilai asli supaya waterfall tetap
      // tampil (tidak jadi warna rata/kosong) walau sinyalnya nyaris flat.
      const mid2 = (minDb2 + maxDb2) / 2;
      minDb2 = mid2 - 3; maxDb2 = mid2 + 3;
    }

    for (let x = 0; x < wfW; x++){
      const off = x * 4;
      if (hasAxis && dataHalfHz > 0){
        // frekuensi yang diwakili pixel x ini pada sumbu 50 MHz tetap (tampilan)
        const freqHere = (axisCenterHtHz - axisHalfHz) + (x / wfW) * (2 * axisHalfHz);
        const dataLow = axisCenterHtHz - dataHalfHz;
        const dataHigh = axisCenterHtHz + dataHalfHz;
        if (freqHere < dataLow || freqHere > dataHigh){
          // Di luar rentang data asli yang benar-benar ditangkap dari sumber.
          // BUKAN data sungguhan -- cuma tekstur "noise floor" acak tipis biar
          // waterfall terlihat menyambung penuh secara visual, tidak ada celah
          // hitam kosong. Nilainya sengaja dibuat rendah & acak kecil supaya
          // tetap kelihatan beda dari sinyal asli di tengah.
          const fakeNoiseNorm = Math.random() * 0.12;
          const [nr, ng, nb] = waterfallColor(fakeNoiseNorm);
          rowImg.data[off] = nr;
          rowImg.data[off + 1] = ng;
          rowImg.data[off + 2] = nb;
          rowImg.data[off + 3] = 255;
          continue;
        }
        const posNorm = (freqHere - dataLow) / (dataHigh - dataLow);
        const srcIdx = Math.min(n - 1, Math.max(0, Math.floor(posNorm * n)));
        let norm = clamp((dbArray[srcIdx] - minDb2) / (maxDb2 - minDb2), 0, 1);
        norm = applyContrast(norm, scopeContrast);
        const [r, g, b] = waterfallColor(norm);
        rowImg.data[off] = r;
        rowImg.data[off + 1] = g;
        rowImg.data[off + 2] = b;
        rowImg.data[off + 3] = 255;
      } else {
        const srcIdx = Math.min(n - 1, Math.floor((x / wfW) * n));
        let norm = clamp((dbArray[srcIdx] - minDb2) / (maxDb2 - minDb2), 0, 1);
        norm = applyContrast(norm, scopeContrast);
        const [r, g, b] = waterfallColor(norm);
        rowImg.data[off] = r;
        rowImg.data[off + 1] = g;
        rowImg.data[off + 2] = b;
        rowImg.data[off + 3] = 255;
      }
    }
    wfCtx.putImageData(rowImg, 0, 0);

    // --- label sumbu frekuensi (dalam skala HT) ---
    if (hasAxis){
      const half = axisHalfHz;
      const centerHtHz = axisCenterHtHz;
      const freqAtX = (x) => centerHtHz - half + (x / w) * (2 * half);

      axisMinEl.textContent = formatMHz(centerHtHz - half) + ' MHz';
      axisCenterEl.textContent = formatMHz(centerHtHz) + ' MHz';
      axisMaxEl.textContent = formatMHz(centerHtHz + half) + ' MHz';
      // Disimpan dalam skala HT juga, supaya klik-untuk-tuning (di bawah)
      // otomatis konsisten: nilai yang dihitung dari klik langsung terpakai
      // sebagai freq_hz (HT) saat dikirim ke backend.
      spectrumCanvas.dataset.centerFreq = String(centerHtHz);
      spectrumCanvas.dataset.sampleRate = String(2 * axisHalfHz);

      // Sebelumnya cuma ada 3 label (kiri/tengah/kanan) di LUAR canvas, tanpa
      // garis bantu yang menunjukkan posisinya persis di mana pada grafik —
      // jadi sulit menebak "titik ini di frekuensi berapa". Sekarang tambah
      // 4 garis kisi vertikal + label MHz langsung di atas canvas, sejajar
      // posisi aslinya.
      specCtx.save();
      specCtx.font = `${Math.max(10, Math.round(11 * (window.devicePixelRatio || 1)))}px sans-serif`;
      specCtx.fillStyle = 'rgba(170,230,230,0.85)';
      specCtx.strokeStyle = 'rgba(88,214,214,0.20)';
      specCtx.lineWidth = 1;
      specCtx.textBaseline = 'top';
      for (let i = 1; i < 4; i++){
        const x = (w / 4) * i;
        specCtx.beginPath();
        specCtx.moveTo(x, 0);
        specCtx.lineTo(x, h);
        specCtx.stroke();
        const label = formatMHzShort(freqAtX(x));
        specCtx.textAlign = i === 2 ? 'center' : (i < 2 ? 'left' : 'right');
        specCtx.fillText(label, x, 2);
      }
      specCtx.restore();

      // Garis penanda: frekuensi yang SEDANG di-tune (currentFreq), supaya
      // langsung kelihatan jelas posisinya relatif terhadap sinyal di
      // spektrum/waterfall, bukan cuma angka di panel sebelah.
      if (typeof currentFreq === 'number' && currentFreq >= (centerHtHz - half) && currentFreq <= (centerHtHz + half)){
        const tunedX = ((currentFreq - (centerHtHz - half)) / (2 * half)) * w;
        specCtx.save();
        specCtx.strokeStyle = '#ffd23f';
        specCtx.lineWidth = 2;
        specCtx.shadowColor = 'rgba(255,210,63,0.65)';
        specCtx.shadowBlur = 5;
        specCtx.beginPath();
        specCtx.moveTo(tunedX, 0);
        specCtx.lineTo(tunedX, h);
        specCtx.stroke();
        specCtx.shadowBlur = 0;

        specCtx.font = `${Math.max(11, Math.round(12 * (window.devicePixelRatio || 1)))}px sans-serif`;
        specCtx.fillStyle = '#ffd23f';
        specCtx.textBaseline = 'bottom';
        specCtx.textAlign = tunedX > w - 90 ? 'right' : (tunedX < 90 ? 'left' : 'center');
        specCtx.fillText(`▼ ${formatMHz(currentFreq)} MHz`, tunedX, h - 4);
        specCtx.restore();
      }
    }
  }

  // Skema warna waterfall biru->cyan->kuning->merah (mirip SDR software pada umumnya)
  function waterfallColor(norm){
    const stops = [
      [0.00, 5, 10, 28],
      [0.30, 12, 35, 95],
      [0.50, 30, 100, 190],
      [0.68, 110, 200, 235],
      [0.82, 225, 245, 255],
      [0.92, 255, 205, 70],
      [1.00, 235, 60, 45],
    ];
    for (let i = 1; i < stops.length; i++){
      const [p0, r0, g0, b0] = stops[i - 1];
      const [p1, r1, g1, b1] = stops[i];
      if (norm <= p1 || i === stops.length - 1){
        const t = (norm - p0) / Math.max(1e-6, (p1 - p0));
        const tt = clamp(t, 0, 1);
        return [
          Math.round(r0 + (r1 - r0) * tt),
          Math.round(g0 + (g1 - g0) * tt),
          Math.round(b0 + (b1 - b0) * tt),
        ];
      }
    }
    return [0, 0, 0];
  }

  // Klik pada grafik spektrum -> tuning langsung ke frekuensi tsb
  spectrumCanvas.addEventListener('click', (e) => {
    const centerFreq = Number(spectrumCanvas.dataset.centerFreq);
    const sampleRate = Number(spectrumCanvas.dataset.sampleRate);
    if (!centerFreq || !sampleRate) return;
    const rect = spectrumCanvas.getBoundingClientRect();
    const xNorm = (e.clientX - rect.left) / rect.width;
    const freqHz = centerFreq - sampleRate / 2 + xNorm * sampleRate;
    commitFreqDisplay(freqHz, 'klik spektrum');
  });

  async function pollSpectrum(){
    // Guard supaya request /spectrum berikutnya tidak ditembak sebelum
    // yang sebelumnya selesai (mencegah request menumpuk kalau backend
    // lambat/mati) -- lihat catatan PERBAIKAN di deklarasi variabel di atas.
    if (spectrumPollInFlight) return;
    spectrumPollInFlight = true;
    try{
      const res = await fetch(`${API_BASE}/spectrum`);
      const data = await safeJson(res);
      if (!data.ok){
        spectrumFailStreak++;
        setRtltcpStatus(false, data.error || 'Belum ada data.');
        return;
      }
      spectrumFailStreak = 0;
      setRtltcpStatus(true, 'Tersambung, menerima data spektrum.');
      drawSpectrumFrame(data.db, data.center_freq_hz, data.sample_rate_hz);
    } catch(err){
      spectrumFailStreak++;
      setRtltcpStatus(false, `Gagal mengambil data spektrum: ${err.message}`);
    } finally {
      spectrumPollInFlight = false;
      if (spectrumRunning){
        let delay = SPECTRUM_POLL_BASE_MS;
        if (spectrumFailStreak > SPECTRUM_POLL_BACKOFF_START){
          const backoffLevel = spectrumFailStreak - SPECTRUM_POLL_BACKOFF_START;
          delay = Math.min(SPECTRUM_POLL_MAX_MS, SPECTRUM_POLL_BASE_MS * Math.pow(2, backoffLevel));
        }
        spectrumPollTimer = setTimeout(pollSpectrum, delay);
      }
    }
  }

  function setRtltcpStatus(online, text){
    rtltcpDot.classList.toggle('online', online);
    rtltcpStatusText.textContent = text;
  }

  function startSpectrum(){
    resizeScopeCanvases();
    waterfallInitialized = false;
    spectrumRunning = true;
    spectrumToggleBtn.innerHTML = pauseIcon();
    spectrumStatusPill.textContent = 'Berjalan';
    spectrumStatusPill.classList.add('busy');
    if (spectrumPollTimer) clearTimeout(spectrumPollTimer);
    spectrumFailStreak = 0;
    spectrumPollInFlight = false;
    pollSpectrum(); // polling berikutnya dijadwalkan otomatis di dalam pollSpectrum()
    if (activeSpectrumSource === 'web888') startWeb888AudioMonitor();
  }

  function stopSpectrumUi(){
    spectrumRunning = false;
    spectrumToggleBtn.innerHTML = playIcon();
    spectrumStatusPill.textContent = 'Berhenti';
    spectrumStatusPill.classList.remove('busy');
    if (spectrumPollTimer) clearTimeout(spectrumPollTimer);
    spectrumPollTimer = null;
    stopWeb888AudioMonitor();
    baseWfSpanHz = null;
    serverZoomActive = false;
  }

  spectrumToggleBtn.addEventListener('click', async () => {
    if (spectrumRunning){
      stopSpectrumUi();
      try{
        await fetch(`${API_BASE}/spectrum/stop`, { method: 'POST' });
      } catch(err){ /* abaikan */ }
      log('Spektrum dihentikan.', 'warn');
      return;
    }
    try{
      const res = await fetch(`${API_BASE}/spectrum/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host: rtltcpHostInput.value.trim() || undefined,
          port: Number(rtltcpPortInput.value) || undefined,
        }),
      });
      const data = await safeJson(res);
      if (!data.ok){
        log(`Gagal memulai spektrum: ${data.error}`, 'err');
        return;
      }
      activeSpectrumSource = data.source || null;
      baseWfSpanHz = Number(data.wf_span_hz || data.sample_rate_hz) || null;
      serverZoomActive = false;
      if (activeSpectrumSource === 'web888'){
        log(`Spektrum dimulai (Web-888 ${data.host}:${data.port}) — audio HT akan ikut diputar di browser.`, 'ok');
      } else {
        log(`Spektrum dimulai (rtl_tcp ${data.host}:${data.port}).`, 'ok');
      }
      // PERBAIKAN: begitu baru tersambung, radio/Web-888 masih di frekuensi
      // terakhir yang kebetulan tersimpan di perangkat (bisa beda jauh dari
      // frekuensi HT yang tampil di panel, mis. jadi 228.8 MHz padahal
      // panel menampilkan 155.700000). Paksa kirim ulang frekuensi HT yang
      // sedang tampil di panel supaya radio langsung di-tune & terkalibrasi
      // ke frekuensi HT yang benar sejak awal tersambung, bukan ikut
      // frekuensi lama yang tidak sesuai.
      sendFreqToSdr(currentFreq);
      startSpectrum();
    } catch(err){
      log(`Gagal menghubungi backend untuk spektrum: ${err.message}`, 'err');
    }
  });

  rtltcpApplyBtn.addEventListener('click', () => {
    if (!spectrumRunning){
      spectrumToggleBtn.click();
    } else {
      // sudah jalan -> restart dengan konfigurasi baru
      stopSpectrumUi();
      fetch(`${API_BASE}/spectrum/stop`, { method: 'POST' }).finally(() => spectrumToggleBtn.click());
    }
  });

  rtltcpStopBtn.addEventListener('click', async () => {
    if (spectrumRunning) stopSpectrumUi();
    try{
      await fetch(`${API_BASE}/spectrum/stop`, { method: 'POST' });
      log('Koneksi rtl_tcp dihentikan.', 'warn');
    } catch(err){ /* abaikan */ }
  });

  /* ============================================================
     TTS PLAYBACK — GET /tts?text=...
     ============================================================ */
  const playTtsBtn = $('playTtsBtn');

  async function playTtsText(text){
    if (!text) return;
    // PERBAIKAN: sebelumnya status pill "Siap" tidak berubah sama sekali
    // selama proses TTS berjalan (request ke backend + generate audio),
    // jadi user tidak tahu aplikasi sedang bekerja. Sekarang pill mengikuti
    // proses ini juga, sama seperti proses translate/upload lainnya.
    statusPill.textContent = 'Membuat Suara TTS…';
    statusPill.classList.add('busy');
    try{
      log('Meminta audio TTS Indonesia dari server…', 'info');
      const url = `${API_BASE}/tts?text=${encodeURIComponent(text)}`;
      // PERBAIKAN (kecepatan pemutaran): sebelumnya di sini kita fetch()
      // lalu menunggu SELURUH berkas audio selesai diunduh dan diubah jadi
      // Blob dulu (await res.blob()) sebelum <audio> bisa mulai memutar --
      // ini menambah jeda ekstra DI ATAS waktu generate TTS di server.
      // Sekarang URL diserahkan langsung ke elemen <audio> lewat
      // playAudioUrl(), supaya browser bisa mulai membuffer & memutar
      // begitu data pertama datang, tanpa menunggu unduhan selesai 100%.
      // Kalau backend gagal (mis. 400/500), event 'error' pada <audio>
      // (sudah dipasang di atas) yang akan melaporkannya ke log.
      playAudioUrl(url, 'Memutar TTS Indonesia…');
    } catch(err){
      log(`Gagal memutar TTS: ${err.message}`, 'err');
    } finally {
      statusPill.textContent = papuaSiapLabel();
      statusPill.classList.remove('busy');
    }
  }

  playTtsBtn.addEventListener('click', () => {
    const text = translationOutput.value.trim();
    if (!text){
      log('Belum ada teks output untuk diucapkan.', 'err');
      return;
    }
    playTtsText(text);
  });

  /* ============================================================
     VIDEO PENGANTAR — tombol play (sebelumnya tidak ada handler-nya
     sama sekali, sehingga klik tidak melakukan apa pun)
     ============================================================ */
  const introVideoEl = $('myCustomVideo');
  const videoPlayBtn = $('videoPlayBtn');
  const videoCaption = $('videoCaption');

  if (introVideoEl && videoPlayBtn){
    // PERBAIKAN: sebelumnya hanya tag <video> yang dipakai, jadi kalau
    // INTRO_VIDEO_URL diisi link YouTube (atau format lain yang tidak bisa
    // didekode langsung oleh browser) video tidak akan pernah start --
    // tanpa pesan error yang jelas. Sekarang sumbernya dideteksi otomatis:
    // link YouTube/Vimeo dipakaikan iframe embed resmi, sedangkan file
    // video langsung (format apa pun yang didukung browser) tetap lewat
    // tag <video> seperti semula. Container & tombol play (UI) tidak diubah.
    let introIframeEl = null;

    function showIntroIframe(embedUrl){
      if (!introIframeEl){
        introIframeEl = document.createElement('iframe');
        introIframeEl.id = 'myCustomVideoEmbed';
        introIframeEl.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
        introIframeEl.setAttribute('allowfullscreen', '');
        introIframeEl.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border:0;display:block;';
        // Ditaruh tepat setelah elemen <video> di container yang sama,
        // supaya tata letak/UI panel video tidak berubah sama sekali.
        introVideoEl.insertAdjacentElement('afterend', introIframeEl);
      }
      introIframeEl.src = embedUrl;
      introIframeEl.style.display = 'block';
      introVideoEl.pause();
      introVideoEl.style.display = 'none';
    }
    function hideIntroIframe(){
      if (introIframeEl){
        introIframeEl.src = ''; // hentikan playback/unduhan saat ditutup
        introIframeEl.style.display = 'none';
      }
    }

    videoPlayBtn.addEventListener('click', () => {
      if (!INTRO_VIDEO_URL){
        log('Video pengantar belum diatur. Isi INTRO_VIDEO_URL di script.js.', 'warn');
        if (videoCaption) videoCaption.textContent = 'Video pengantar belum tersedia.';
        return;
      }

      const source = resolveVideoSource(INTRO_VIDEO_URL);
      videoPlayBtn.style.display = 'none';

      if (source.type === 'embed'){
        showIntroIframe(source.embedUrl);
        log('Memutar video pengantar (embed YouTube/Vimeo).', 'ok');
        return;
      }

      hideIntroIframe();
      introVideoEl.style.display = 'block';
      if (introVideoEl.getAttribute('src') !== source.directUrl){
        introVideoEl.src = source.directUrl;
      }
      introVideoEl.play().catch(err => {
        log(`Gagal memutar video pengantar: ${err.message}`, 'err');
        introVideoEl.style.display = 'none';
        videoPlayBtn.style.display = 'flex';
      });
    });

    introVideoEl.addEventListener('error', () => {
      // PERBAIKAN: sebelumnya kegagalan MEMUAT video (format/codec tidak
      // didukung, path salah, dll) tidak pernah ditangkap sama sekali --
      // video hanya diam, tombol play tidak muncul lagi, tanpa keterangan
      // apa pun. Sekarang error load ditangani eksplisit dan jelas.
      if (!introVideoEl.currentSrc) return; // belum ada src yang dicoba, abaikan
      log('Video pengantar gagal dimuat -- format/sumber mungkin tidak didukung browser.', 'err');
      if (videoCaption) videoCaption.textContent = 'Video pengantar gagal dimuat. Coba format lain (mp4/webm) atau tautan YouTube/Vimeo.';
      introVideoEl.style.display = 'none';
      videoPlayBtn.style.display = 'flex';
    });

    introVideoEl.addEventListener('pause', () => {
      if (introVideoEl.ended) return;
      videoPlayBtn.style.display = 'flex';
    });
    introVideoEl.addEventListener('ended', () => {
      videoPlayBtn.style.display = 'flex';
      introVideoEl.style.display = 'none';
    });
  }

  /* ============================================================
     INIT
     ============================================================ */
  drawFreqRuler(0, 0, false);
  setSliderFill(freqSlider);
  setSliderFill(bwSlider);
  if (zoomSlider) setSliderFill(zoomSlider);
  if (contrastSlider) setSliderFill(contrastSlider);
  if (volumeSlider) setSliderFill(volumeSlider);
  applyRemoteFreq(currentFreq);
  applyRemoteBw(currentBw);
  showFbwTab('frekuensi');
  showPage('pageHome');
  setRtltcpStatus(false, 'Belum tersambung');

  log('Menghubungkan ke backend…', 'info');
  loadDevices();
  startRmsPolling();
  startSdrPolling();

})();