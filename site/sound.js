// Звук страницы. Выключен, пока человек сам не нажмёт кнопку, и ничего не запоминает.
// Звуковых файлов нет: всё синтезируется прямо в браузере.
window.whoSound = (() => {
  let ctx = null, master, analyser, enabled = false;
  let jumping = false, settled = true, settleTimer = 0;
  let lastNoteAt = 0, lastDots = -1, lastStep = -1, lastSeal = -1, lastPass = 0, lastC = 0, thudArmed = true;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  // ноты мажорной пентатоники: любые из них звучат вместе без фальши
  const SCALE = [0, 2, 4, 7, 9];
  const note = (index, base = 220) => base * 2 ** ((SCALE[((index % 5) + 5) % 5] + 12 * Math.floor(index / 5)) / 12);

  function build() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    ctx = new AC();
    master = ctx.createGain(); master.gain.value = .55;
    const limiter = ctx.createDynamicsCompressor();
    analyser = ctx.createAnalyser(); analyser.fftSize = 1024;
    master.connect(limiter); limiter.connect(analyser); analyser.connect(ctx.destination);
    const noise = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate), data = noise.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    ctx.noiseBuffer = noise;
    return true;
  }

  function tone(freq, length, volume, type = 'sine', when = 0, endFreq = 0) {
    const t = ctx.currentTime + when, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (endFreq) o.frequency.exponentialRampToValueAtTime(endFreq, t + length);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(volume, t + .006); g.gain.exponentialRampToValueAtTime(.0001, t + length);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + length + .02);
  }

  function burst(freq, length, volume, when = 0) {
    const t = ctx.currentTime + when, s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = ctx.noiseBuffer; f.type = 'bandpass'; f.frequency.value = freq; f.Q.value = 3;
    g.gain.setValueAtTime(volume, t); g.gain.exponentialRampToValueAtTime(.0001, t + length);
    s.connect(f); f.connect(g); g.connect(master); s.start(t, Math.random() * 1.5, length + .02);
  }

  const key = () => { burst(1700 + Math.random() * 900, .035, .35); tone(190 + Math.random() * 40, .03, .05, 'triangle'); };
  // растяжение: мягкие деревянные ноты, узор идёт вверх вместе с заполнением памяти
  const pluck = index => { const f = note(index); tone(f, .34, .085, 'sine'); tone(f * 4, .05, .012, 'sine'); };
  // шифрование: низкие спокойные удары, когда плита проходит по записи
  const bell = index => { const f = note(index, 110); tone(f, 1.3, .1, 'sine'); tone(f * 2, .7, .025, 'sine'); };
  const chord = () => [261.6, 329.6, 392].forEach((f, i) => tone(f, .9, .05, 'sine', i * .035));
  const thud = () => { tone(115, .42, .36, 'sine', 0, 42); burst(240, .1, .22); };
  const unlock = () => { burst(2600, .03, .3); tone(880, .1, .05, 'triangle', .05); tone(1320, .16, .04, 'sine', .1); };
  const deny = () => { tone(130, .12, .13, 'triangle'); tone(98, .2, .15, 'triangle', .13); };

  // каждый кадр истории: c — положение на шкале прокрутки, speed — скорость прокрутки от 0 до 1
  function frame({ c, speed, dots, grid, uProg, passes, sealing, sealProgress }) {
    if (!enabled || !ctx) return;
    const now = performance.now();
    // прыжок по ссылке из меню пролетает всю историю за секунду: молчим, пока страница не встанет
    if (jumping && settled && speed < .02) jumping = false;
    const loud = !jumping;
    if (dots > lastDots && lastDots >= 0 && loud) key();
    lastDots = dots;

    if (grid > .01 && uProg > 0 && uProg < passes) {
      // шаг зависит от места на странице, а не от времени: стоишь — тихо, листаешь назад — те же ноты
      const step = Math.floor(uProg * 16), pass = Math.floor(uProg);
      if (step !== lastStep && lastStep >= 0 && now - lastNoteAt > 85) {
        const within = step % 16;
        if (loud) pluck(pass * 2 + [0, 2, 4, 3, 5, 7, 6, 8][within % 8] + (within >> 3) * 2);
        lastNoteAt = now;
      }
      lastStep = step;
      if (pass > lastPass && loud) chord();
      lastPass = pass;
    } else {
      lastStep = -1;
      if (c < 2.1) lastPass = 0;
      if (c > 2.8 && lastC <= 2.8 && loud) chord();
    }

    if (sealing) {
      const seal = Math.floor(clamp(sealProgress) * 6);
      if (seal !== lastSeal && lastSeal >= 0 && now - lastNoteAt > 160) { if (loud) bell(seal); lastNoteAt = now; }
      lastSeal = seal;
    } else lastSeal = -1;

    if (c >= 4.3 && lastC < 4.3 && thudArmed) { if (loud) thud(); thudArmed = false; }
    if (c < 4.1) thudArmed = true;
    lastC = c;
  }

  function door() {
    if (!enabled || !ctx) return;
    unlock();
    setTimeout(() => { if (enabled) deny(); }, 300);
  }

  function toggle() {
    if (!ctx && !build()) return false;
    enabled = !enabled;
    if (enabled) { ctx.resume(); lastDots = -1; tone(660, .1, .08, 'sine'); tone(990, .14, .06, 'sine', .07); }
    else { setTimeout(() => { if (!enabled) ctx.suspend(); }, 250); }
    return enabled;
  }

  // ссылка внутри страницы («Скачать», «Честно», логотип): дальше прокрутка — не человека
  document.addEventListener('click', e => {
    const link = e.target.closest && e.target.closest('a[href^="#"]');
    if (link && !e.defaultPrevented) { jumping = true; settled = false; clearTimeout(settleTimer); settleTimer = setTimeout(() => { settled = true; }, 250); }
  });
  addEventListener('scroll', () => {
    if (!jumping) return;
    settled = false; clearTimeout(settleTimer);
    settleTimer = setTimeout(() => { settled = true; }, 250);
  }, { passive: true });
  // человек сам взялся за прокрутку — снова его звук
  for (const type of ['wheel', 'touchstart', 'keydown']) addEventListener(type, () => { jumping = false; }, { passive: true });

  document.addEventListener('visibilitychange', () => {
    if (!ctx || !enabled) return;
    if (document.hidden) ctx.suspend(); else ctx.resume();
  });

  const button = document.getElementById('snd');
  if (button && (window.AudioContext || window.webkitAudioContext)) {
    button.hidden = false;
    const hint = document.getElementById('snd-hint');
    if (hint) hint.hidden = false;
    button.addEventListener('click', () => {
      const on = toggle();
      button.setAttribute('aria-pressed', String(on));
      if (hint) hint.hidden = on; // звук уже включён — просить больше незачем
    });
  }
  return { frame, door, get state() { return ctx ? ctx.state : 'none'; }, level() { if (!analyser) return 0; const a = new Float32Array(analyser.fftSize); analyser.getFloatTimeDomainData(a); return Math.max(...a.map(Math.abs)); } };
})();
