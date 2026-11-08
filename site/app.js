/* WhoKey story page. All first-party, no network, no storage. */
(function () {
  'use strict';
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const docEl = document.documentElement, C = globalThis.WKCrypto;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const ss = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
  const lerp = (a, b, t) => a + (b - a) * t;
  const hex = b => [...b].map(x => x.toString(16).padStart(2, '0')).join('');
  const utf8 = s => new TextEncoder().encode(s);

  /* ---------- language and OS ---------- */
  const lEn = $('#l-en'), lRu = $('#l-ru');
  const isEn = () => lEn.checked;
  const syncLang = () => { docEl.lang = isEn() ? 'en' : 'ru'; };
  if (!/^ru|^be|^uk|^kk/i.test(navigator.language || 'ru')) lEn.checked = true;
  syncLang();
  let onLang = () => {}, newLanguage = () => {};
  [lEn, lRu].forEach(x => x.addEventListener('change', () => { syncLang(); updateDoorStat(); newLanguage(); onLang(); }));

  const ua = navigator.userAgent, plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
  const os = /Android|iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(plat) && navigator.maxTouchPoints > 1) ? 'phone'
    : /Windows/i.test(ua) ? 'win' : /Mac/i.test(plat) || /Macintosh/i.test(ua) ? 'mac' : /Linux|X11/i.test(ua) ? 'linux' : '';
  const OS = {
    mac: ['macOS (Apple Silicon)', 'WhoKey.Installer.dmg', '~/Library/Application Support/EduPasswords/vault.dat'],
    win: ['Windows', 'WhoKey.Installer.exe', '%APPDATA%\\EduPasswords\\vault.dat'],
    linux: ['Linux x86-64', 'WhoKey-linux-x86_64.tar.gz', '~/.local/share/EduPasswords/vault.dat'],
  };
  const note = $('#os-note');
  if (OS[os]) {
    const [name, file] = OS[os];
    $('#cta').href = 'https://github.com/kichike/whokey/releases/latest/download/' + file;
    $('#cta-ru').textContent = 'Скачать для ' + name;
    $('#cta-en').textContent = 'Download for ' + name;
    $(`.dlc[data-os=${os}]`).classList.add('me');
    note.hidden = false;
    note.innerHTML = `<span class="ru">Похоже, вам подойдёт ${name}: этот вариант подсвечен. Если у вас другой процессор или система, смотрите требования на карточках.</span><span class="en">${name} looks like your match, so it is highlighted. If your processor or system differs, check the requirements on the cards.</span>`;
  } else if (os === 'phone') {
    $('#cta-ru').textContent = 'Версии для компьютера';
    $('#cta-en').textContent = 'Desktop versions';
    note.hidden = false;
    note.innerHTML = '<span class="ru">Для телефона WhoKey нет: только macOS, Windows и Linux. Откройте эту страницу на компьютере.</span><span class="en">WhoKey has no phone version: only macOS, Windows and Linux. Open these links on a computer.</span>';
  }
  const pathText = (OS[os] || OS.mac)[2];
  $$('[data-v=path]').forEach(e => { e.textContent = pathText; });
  docEl.classList.toggle('lg', !!(navigator.userAgentData && navigator.userAgentData.brands.some(b => /Chromium/.test(b.brand))) && matchMedia('(pointer:fine) and (min-width:900px)').matches);

  // specular highlight follows the pointer across glass
  if (!reduced && matchMedia('(pointer:fine)').matches) {
    // Один ореол на всю страницу: идёт за курсором и виден только на плитках, поэтому нигде
    // не остаётся. Положение считаем для всех плиток сразу: пятно плавно переходит с одной на другую.
    const panes = $$('.glass'); let px = -9999, py = -9999, pending = 0;
    const paint = () => {
      pending = 0;
      panes.forEach(g => {
        const r = g.getBoundingClientRect();
        if (r.bottom < 0 || r.top > innerHeight) return;
        g.style.setProperty('--mx', (px - r.left) + 'px'); g.style.setProperty('--my', (py - r.top) + 'px');
      });
    };
    const later = () => { if (!pending) pending = requestAnimationFrame(paint); };
    addEventListener('pointermove', e => { px = e.clientX; py = e.clientY; later(); }, { passive: true });
    addEventListener('scroll', later, { passive: true });
    docEl.addEventListener('pointerleave', () => { px = py = -9999; later(); });
  }
  new IntersectionObserver(es => es.forEach(e => docEl.classList.toggle('dim', e.isIntersecting)), { rootMargin: '-35% 0px -35% 0px' }).observe($('#honest'));

  /* ---------- the real demo: Argon2id + Fernet on a made-up password ---------- */
  const PIXEL = document.documentElement.dataset.style === 'pixel', TF = PIXEL ? 'WhoPixel' : 'Meslo', GR = innerWidth < 900 ? 2 : 4;
  // придуманные примеры: свои для каждого языка
  const PASSWORDS = {
    ru: ['пельмени-42', 'кот-на-крыше', 'чайник-в-туре', 'три-кактуса-9', 'борщ-на-орбите', 'тапки-в-космосе', 'самовар-на-луне', 'шапка-ушанка-5', 'гречка-с-маслом-7'],
    en: ['zebra-tuba-7', 'pickle-on-mars', 'three-cactus-9', 'toast-in-orbit', 'sleepy-walrus-4', 'disco-teapot', 'cosmic-waffle-8', 'banana-radio', 'moon-socks-3'],
  };
  const examples = () => PASSWORDS[isEn() ? 'en' : 'ru'];
  const DEMO = { m: 1024, t: 3, p: 1 };
  const state = { pw: examples()[0], salt: crypto.getRandomValues(new Uint8Array(16)), key: null, trace: null, token: null, ms: 0 };

  function derive(pw) {
    return C.argon2id({ password: utf8(pw), salt: state.salt, t: DEMO.t, m: DEMO.m, p: DEMO.p, len: 32, trace: true });
  }
  async function compute() {
    const t0 = performance.now();
    const r = derive(state.pw);
    state.ms = performance.now() - t0;
    state.key = r.tag;
    state.trace = r.trace;
    $$('[data-v=pw]').forEach(e => { e.textContent = state.pw; });
    $$('[data-v=key]').forEach(e => { e.textContent = hex(state.key); });
    if (C.hasSubtle()) {
      const plain = utf8(JSON.stringify({ site: 'example.com', login: 'demo', password: state.pw }));
      state.token = await C.fernetEncrypt(state.key, plain, Math.floor(Date.now() / 1000));
      state.tokenStr = C.b64u(state.token);
      $$('[data-v=token]').forEach(e => { e.textContent = state.tokenStr; });
      docEl.classList.add('live');
      await runDoor();
    }
    drawStaticGrid();
  }

  /* ---------- "one character off" ---------- */
  let doorPos = -1, doorStat = null;
  function shiftChar(ch) {
    if (/[0-9]/.test(ch)) return String((+ch + 1) % 10);
    if (ch === '-') return '_';
    const ru = 'абвгдежзийклмнопрстуфхцчшщыэюя', en = 'abcdefghijklmnopqrstuvwxyz';
    const set = ru.includes(ch) ? ru : en, i = set.indexOf(ch);
    return i < 0 ? 'x' : set[(i + 1) % set.length];
  }
  async function runDoor(advance) {
    const pw = state.pw;
    if (advance || doorPos < 0 || doorPos >= pw.length) doorPos = advance ? (doorPos + 3) % pw.length : pw.length - 1;
    const other = pw.slice(0, doorPos) + shiftChar(pw[doorPos]) + pw.slice(doorPos + 1);
    const t0 = performance.now();
    const kb = C.argon2id({ password: utf8(other), salt: state.salt, t: DEMO.t, m: DEMO.m, p: DEMO.p, len: 32 }).tag;
    const ms = performance.now() - t0;
    const ha = hex(state.key), hb = hex(kb);
    let bits = 0;
    state.key.forEach((x, i) => { let v = x ^ kb[i]; while (v) { bits += v & 1; v >>= 1; } });
    $('#d-a').textContent = pw;
    const elB = $('#d-b'); elB.textContent = '';
    [...other].forEach((ch, i) => { const n = i === doorPos ? document.createElement('b') : document.createTextNode(ch); if (i === doorPos) n.textContent = ch; elB.append(n); });
    $('#d-ka').textContent = ha;
    const elK = $('#d-kb'); elK.textContent = '';
    [...hb].forEach((ch, i) => { if (ch !== ha[i]) { const b = document.createElement('b'); b.textContent = ch; elK.append(b); } else elK.append(ch); });
    const good = await C.fernetDecrypt(state.key, state.token);
    const bad = await C.fernetDecrypt(kb, state.token);
    doorStat = { bits, ms: Math.round(ms), good: !!good, bad: !!bad };
    updateDoorStat();
  }
  function updateDoorStat() {
    if (!doorStat) return;
    const s = doorStat, en = isEn();
    $('#d-ra').textContent = s.good ? (en ? 'Signature matches, the file opens.' : 'Подпись совпала, файл открылся.') : '?';
    $('#d-rb').textContent = s.bad ? '?' : (en ? "Signature doesn't match, the file stays shut." : 'Подпись не совпала, файл не открылся.');
    $('#d-stat').textContent = en
      ? `${s.bits} of 256 key bits differ. Computed here just now, in ${s.ms} ms on this device with the demo settings.`
      : `Разных битов ключа: ${s.bits} из 256. Посчитано на этом устройстве за ${s.ms} мс, настройки демо.`;
  }

  /* ---------- static picture of the memory (reduced motion, or no WebGL) ---------- */
  const shadeColor = v => { const t = v / 255; return [lerp(38, 240, t * t), lerp(29, 90, t), lerp(92, 240, t)]; };
  function drawStaticGrid() {
    if (docEl.classList.contains('fx') || !state.trace) return;
    const cv = $('#sgrid'); cv.hidden = false;
    const g = cv.getContext('2d'), q = state.trace.q, side = Math.round(Math.sqrt(q)), s = cv.width / side;
    for (let i = 0; i < q; i++) {
      const c = shadeColor(state.trace.shade[(state.trace.t - 1) * q + i]);
      g.fillStyle = `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
      g.fillRect((i % side) * s, Math.floor(i / side) * s, s - 1, s - 1);
    }
    g.strokeStyle = 'rgba(255,255,255,.75)'; g.lineWidth = 1;
    const cen = i => [(i % side + .5) * s, (Math.floor(i / side) + .5) * s], p = (state.trace.t - 1) * q;
    for (let i = q - 24; i < q; i++) {
      const [a, b] = cen(i), [e, f] = cen(state.trace.refs[p + i]);
      g.beginPath(); g.moveTo(a, b); g.lineTo(e, f); g.stroke();
    }
  }

  /* ---------- cinema: is it possible here? ---------- */
  let gl = null;
  if (!reduced) {
    const glCanvas = $('#gl');
    try { gl = glCanvas.getContext('webgl', { alpha: true, antialias: false, powerPreference: 'default', premultipliedAlpha: true }); } catch (e) { gl = null; }
  }
  if (gl && innerHeight >= 500) docEl.classList.add('fx');
  const start = () => {
    const after = () => compute().catch(() => {}).then(() => { if (gl) rebuildDemoFormations(); });
    $('#dice').hidden = false;
    $('#d-next').hidden = false;
    newLanguage = () => { state.pw = examples()[0]; doorPos = -1; after(); };
    $('#dice').addEventListener('click', () => {
      state.pw = examples()[(examples().indexOf(state.pw) + 1) % examples().length];
      doorPos = -1;
      after();
    });
    $('#d-next').addEventListener('click', () => { if (state.token) { runDoor(true); if (window.whoSound) whoSound.door(); } });
    if (gl) initStage().catch(() => { gl = null; docEl.classList.remove('fx'); }).then(() => setTimeout(after, 30)); else setTimeout(after, 30);
  };

  /* ---------- particles ---------- */
  let rebuildDemoFormations = () => {};
  async function initStage() {
    const lowEnd = (navigator.deviceMemory && navigator.deviceMemory <= 2) || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 3);
    const narrow = () => innerWidth < 900;
    const N = lowEnd ? 3000 : narrow() ? 7000 : 15000;
    const bloom = !lowEnd;
    const stage = $('#stage'), glC = $('#gl'), arcC = $('#arcs'), arc = arcC.getContext('2d');

    const prog = (vs, fs) => {
      const p = gl.createProgram();
      for (const [t, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
        const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
        gl.attachShader(p, s);
      }
      gl.linkProgram(p);
      const u = {}, a = {};
      for (let i = 0, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); i < n; i++) { const k = gl.getActiveUniform(p, i).name; u[k] = gl.getUniformLocation(p, k); }
      for (let i = 0, n = gl.getProgramParameter(p, gl.ACTIVE_ATTRIBUTES); i < n; i++) { const k = gl.getActiveAttrib(p, i).name; a[k] = gl.getAttribLocation(p, k); }
      return { p, u, a };
    };
    const PP = prog(`
      attribute vec3 aA; attribute vec4 aB; attribute vec3 aS;
      uniform vec2 uRes; uniform float uMix,uT,uJit,uDpr,uSize,uAlpha,uW,uSpread; uniform vec3 uPtr;
      varying float vC,vA;
      void main(){
        float w=uW;
        float l=clamp((uMix-aB.w*(1.-w))/w,0.,1.); l=l*l*(3.-2.*l);
        vec2 p=mix(aA.xy,aB.xy,l);
        float tr=sin(l*3.14159), ang=aS.x*6.283+uT*.7+p.y*.006;
        p+=vec2(cos(ang),sin(ang*1.3))*(tr*uSpread*(50.+170.*aS.y));
        p+=vec2(sin(uT*1.1+aS.x*40.),cos(uT*.9+aS.y*40.))*(.22+uJit*9.)*(.5+aS.z);
        if(uPtr.z>0.){vec2 d=p-uPtr.xy;float e=length(d);p+=d/max(e,1.)*uPtr.z*26.*exp(-e*e/3500.);}
        vC=mix(aA.z,aB.z,l);
        vA=uAlpha*(.45+.55*aS.z);
        ${PIXEL ? `p=floor(p/${GR}.+.5)*${GR}.;` : ''}
        gl_Position=vec4(p.x/uRes.x*2.-1.,1.-p.y/uRes.y*2.,0.,1.);
        gl_PointSize=${PIXEL ? `${GR}.*.9*uDpr` : 'uSize*uDpr*(.7+.6*aS.y)'};
      }`, `
      precision mediump float; varying float vC,vA; uniform float uSoft;
      void main(){
        float d=length(gl_PointCoord-.5)*2.; float a=${PIXEL ? 'vA+uSoft*0.+d*0.' : 'smoothstep(1.,uSoft,d)*vA'};
        vec3 c=mix(vec3(.72,.66,1.),vec3(.96,.28,.94),vC);
        gl_FragColor=vec4(c*a,a);
      }`);
    const GP = prog(`
      attribute vec2 aP; attribute float aI; attribute vec3 aS;
      uniform vec2 uRes,uCen; uniform float uF,uCell,uDpr,uAlpha,uCol,uAny; uniform vec3 uCur,uPrev;
      varying vec3 vC; varying float vA;
      void main(){
        bool done=aI<uF;
        float v=dot(aS,done?uCur:uPrev);
        float flash=done?smoothstep(.016,0.,uF-aI):0.;
        vec3 c=mix(vec3(.13,.1,.36),vec3(.62,.5,.96),smoothstep(0.,.55,v));
        c=mix(c,vec3(.94,.28,.94),smoothstep(.55,1.,v));
        vC=c+flash*vec3(.55,.35,.5);
        vA=uAlpha*((done||uAny>.5)?1.:.1);
        vec2 p=mix(aP,uCen,uCol*uCol);
        gl_Position=vec4(p.x/uRes.x*2.-1.,1.-p.y/uRes.y*2.,0.,1.);
        gl_PointSize=uCell*uDpr*(1.-uCol*.7)*(.84+flash*.5);
      }`, `
      precision mediump float; varying vec3 vC; varying float vA;
      void main(){ vec2 q=abs(gl_PointCoord-.5)*2.; float a=smoothstep(1.,.82,max(q.x,q.y))*vA; gl_FragColor=vec4(vC*a,a);}`);

    const buf = gl.createBuffer(), seed = gl.createBuffer(), gbuf = gl.createBuffer();
    const data = new Float32Array(N * 7);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
    const sd = new Float32Array(N * 3).map(() => Math.random());
    gl.bindBuffer(gl.ARRAY_BUFFER, seed); gl.bufferData(gl.ARRAY_BUFFER, sd, gl.STATIC_DRAW);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, PIXEL ? gl.ONE_MINUS_SRC_ALPHA : gl.ONE);
    gl.clearColor(0, 0, 0, 0);

    const keyImg = new Image(); keyImg.src = 'assets/key.webp';
    await Promise.all([
      new Promise(r => { keyImg.onload = keyImg.onerror = r; }),
      Promise.race([Promise.all([document.fonts.load(`700 40px ${TF}`, 'Жz'), document.fonts.load('400 13px Meslo')]), new Promise(r => setTimeout(r, 1500))]),
    ]);

    /* ---------- formations: where every particle wants to be ---------- */
    let W = 0, H = 0, dpr = 1, isNarrow = false, F = {}, rect = {}, gridGeom = null;
    const off = document.createElement('canvas');
    const offg = off.getContext('2d', { willReadFrequently: true });
    function samplePixels(draw, w, h) {
      off.width = Math.max(1, Math.ceil(w)); off.height = Math.max(1, Math.ceil(h));
      offg.clearRect(0, 0, off.width, off.height);
      draw(offg);
      const d = offg.getImageData(0, 0, off.width, off.height).data, pts = [];
      for (let y = 0; y < off.height; y++) for (let x = 0; x < off.width; x++) if (d[(y * off.width + x) * 4 + 3] > 140) pts.push(x, y);
      return pts;
    }
    function form(n, fn) {
      const f = new Float32Array(n * 4);
      for (let i = 0; i < n; i++) fn(i, f, i * 4);
      return f;
    }
    const fromPts = (pts, x0, y0, h, ordFn) => {
      const out = form(N, (i, f, o) => {
        if (!pts.length) { f[o] = x0; f[o + 1] = y0; return; }
        const k = Math.floor(Math.random() * pts.length / 2) * 2;
        const x = x0 + pts[k] + Math.random(), y = y0 + pts[k + 1] + Math.random();
        f[o] = x; f[o + 1] = y; f[o + 2] = clamp((y - y0) / h);
        f[o + 3] = ordFn ? ordFn(x, y) : Math.random();
      });
      out.glow = clamp((pts.length / 2) / N * (isNarrow ? 3.4 : 2.6), .3, 1);
      return out;
    };
    function keyForm(cx, cy, h, ord) {
      const ar = (keyImg.naturalWidth || 170) / (keyImg.naturalHeight || 331), w = h * ar;
      const pts = samplePixels(g => g.drawImage(keyImg, 0, 0, w, h), w, h);
      return fromPts(pts, cx - w / 2, cy - h / 2, h, ord);
    }
    function textPts(lines, maxW, maxFs) {
      offg.font = `700 100px ${TF}, monospace`;
      const widest = Math.max(...lines.map(l => offg.measureText(l).width));
      const fs = Math.min(maxFs, Math.floor(100 * maxW / widest));
      const lh = fs * 1.3, w = Math.ceil(widest * fs / 100) + 4, h = Math.ceil(lh * lines.length + 4);
      const pts = samplePixels(g => {
        g.font = `700 ${fs}px ${TF}, monospace`; g.fillStyle = '#fff'; g.textBaseline = 'top';
        lines.forEach((l, i) => g.fillText(l, 0, i * lh + 1));
      }, w, h);
      return { pts, w, h, fs };
    }

    function measure() {
      W = stage.clientWidth; H = stage.clientHeight;
      isNarrow = W < 900;
      dpr = Math.min(devicePixelRatio || 1, isNarrow || lowEnd ? 1.75 : 2);
      glC.width = arcC.width = Math.round(W * dpr); glC.height = arcC.height = Math.round(H * dpr);
      gl.viewport(0, 0, glC.width, glC.height);
      $$('.fx .act:not(.hero) .card').forEach(c => {
        const h = c.offsetHeight;
        c.style.setProperty('--st', (isNarrow ? H - h - 12 : Math.max(76, (H - h) / 2)) + 'px');
      });
      const top = 66;
      const vrFor = sel => {
        if (!isNarrow) { const x = Math.max(24, W * .05) + Math.min(430, W * .38) + 30; return { x, y: top + 6, w: W - x - 96, h: H - top - 30 }; }
        const c = $(sel + ' .card');
        return { x: 14, y: top, w: W - 28, h: Math.max(120, H - c.offsetHeight - top - 22) };
      };
      rect = { hero: vrFor('.hero'), a1: vrFor('.a1'), a2: vrFor('.a2'), a3: vrFor('.a3'), a4: vrFor('.a4') };
      if (!isNarrow) { const hw = Math.min(720, W * .56); rect.hero = { x: Math.max(24, W * .05) + hw + 10, y: 80, w: W - (Math.max(24, W * .05) + hw + 40), h: H - 120 }; }
    }

    function buildStatic() {
      const R0 = rect.hero;
      F.scatter = form(N, (i, f, o) => {
        const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * Math.max(W, H) * .7;
        f[o] = R0.x + R0.w / 2 + Math.cos(a) * r; f[o + 1] = R0.y + R0.h / 2 + Math.sin(a) * r; f[o + 2] = Math.random(); f[o + 3] = Math.random();
      });
      const kh = Math.min(R0.h * .96, isNarrow ? 300 : 560);
      F.key = keyForm(R0.x + R0.w / 2, R0.y + R0.h / 2, kh);
      const R2 = rect.a2;
      F.key2 = keyForm(R2.x + R2.w / 2, R2.y + R2.h * .42, Math.min(R2.h * .62, 400));
    }
    function buildDemo() {
      const R1 = rect.a1;
      const login = $('#s-login');
      const lw = Math.min(R1.w, 400), lh = login.offsetHeight || 190;
      login.style.width = lw + 'px';
      const textBlockH = Math.min(R1.h - lh - 16, isNarrow ? 90 : 150);
      const lTop = R1.y + (R1.h - lh - textBlockH - 16) / 2 + textBlockH + 16;
      login.style.left = (R1.x + (R1.w - lw) / 2) + 'px'; login.style.top = lTop + 'px';
      const t = textPts([state.pw], R1.w * .96, Math.min(textBlockH * .8, isNarrow ? 44 : 84));
      const tx = R1.x + (R1.w - t.w) / 2, ty = lTop - 16 - t.h;
      F.pw = fromPts(t.pts, tx, ty, t.h, x => clamp((x - tx) / t.w));
      rect.pw = { x: tx, y: ty, w: t.w, h: t.h };
      const cx = tx + t.w / 2, cy = ty + t.h / 2, sx = R1.w * 1.02 / t.w;
      F.pwS = form(N, (i, f, o) => {
        f[o] = cx + (F.pw[o] - cx) * sx; f[o + 1] = cy + (F.pw[o + 1] - cy) * (.55 + .5 * Math.abs(F.pw[o] - cx) / (t.w / 2));
        f[o + 2] = F.pw[o + 2]; f[o + 3] = Math.abs(F.pw[o] - cx) / (t.w / 2) * .6 + Math.random() * .1;
      });
      // the memory
      const R2 = rect.a2, q = DEMO.m, side = Math.round(Math.sqrt(q));
      // место под подписью: на телефоне она занимает две-три строки и не должна залезать на карточку
      const capH = W < 370 ? 74 : isNarrow ? 54 : 28;
      const gs = Math.min(R2.w, R2.h - capH - 6, 640), cell = gs / side;
      const gx = R2.x + (R2.w - gs) / 2, gy = R2.y + (R2.h - gs - capH) / 2;
      gridGeom = { gx, gy, gs, cell, side, q };
      const hud = $('#s-grid');
      hud.style.left = R2.x + 'px'; hud.style.width = R2.w + 'px'; hud.style.top = (gy + gs + 8) + 'px';
      F.grid = form(N, (i, f, o) => {
        const c = Math.floor(Math.random() * q);
        f[o] = gx + (c % side + Math.random()) * cell; f[o + 1] = gy + (Math.floor(c / side) + Math.random()) * cell;
        f[o + 2] = (f[o + 1] - gy) / gs; f[o + 3] = c / q * .8 + Math.random() * .2;
      });
      if (state.trace) {
        const g = new Float32Array(q * 6), tr = state.trace.shade;
        for (let i = 0; i < q; i++) {
          g[i * 6] = gx + (i % side + .5) * cell; g[i * 6 + 1] = gy + (Math.floor(i / side) + .5) * cell;
          g[i * 6 + 2] = i / q;
          g[i * 6 + 3] = tr[i] / 255; g[i * 6 + 4] = tr[q + i] / 255; g[i * 6 + 5] = tr[2 * q + i] / 255;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, gbuf); gl.bufferData(gl.ARRAY_BUFFER, g, gl.STATIC_DRAW);
      }
      const ko = $('#s-key'), kw = Math.min(R2.w, 560);
      ko.style.width = kw + 'px'; ko.style.left = (R2.x + (R2.w - kw) / 2) + 'px';
      ko.style.top = (R2.y + Math.min(R2.h * .78, R2.h - (isNarrow ? 92 : 100))) + 'px';

      // the entry, then its token as a field of bits, next to a small key
      const R3 = rect.a3;
      const kh = isNarrow ? 56 : 96;
      // частиц ровно столько, чтобы ключ был виден: при большем числе они складываются в белое пятно
      const split = Math.min(Math.floor(N * .16), Math.floor(kh * kh * .09));
            const tt = textPts(['example.com', 'demo', state.pw], R3.w * .96, isNarrow ? 26 : 52);
      const tokBoxH = isNarrow ? 122 : 110;
      const avail = R3.h - kh - tokBoxH - 18;
      const scale = Math.min(1, avail / tt.h);
      const fieldH = Math.min(avail, isNarrow ? 250 : 300);
      const ty3 = R3.y + (R3.h - (kh + 8 + fieldH + 12 + tokBoxH)) / 2 + kh + 8 + (fieldH - tt.h * scale) / 2;
      const by = ty3 - (fieldH - tt.h * scale) / 2;
      const tx3 = R3.x + (R3.w - tt.w * scale) / 2;
      const keySmall = keyForm(R3.x + 16 + kh * .26, by - 8 - kh / 2, kh);
      const body = fromPts(tt.pts, tx3, ty3, tt.h, x => x);
      F.entry = form(N, (i, f, o) => {
        if (i < split) { for (let k = 0; k < 4; k++) f[o + k] = keySmall[o + k]; f[o + 3] = 0; return; }
        f[o] = tx3 + (body[o] - tx3) * scale; f[o + 1] = ty3 + (body[o + 1] - ty3) * scale; f[o + 2] = body[o + 2]; f[o + 3] = Math.random();
      });
      const bytes = state.token || utf8(state.pw.repeat(40));
      const bx = R3.x + 4, bw = R3.w - 8, bh = fieldH;
      const nBits = bytes.length * 8, ratio = bw / bh;
      const cols = Math.round(Math.sqrt(nBits * ratio)), rows = Math.ceil(nBits / cols), cw = bw / cols, ch = bh / rows;
      const on = [];
      for (let b = 0; b < nBits; b++) if (bytes[b >> 3] & (128 >> (b & 7))) on.push(b);
      F.bits = form(N, (i, f, o) => {
        if (i < split) { for (let k = 0; k < 4; k++) f[o + k] = keySmall[o + k]; f[o + 3] = 0; return; }
        const b = on[Math.floor(Math.random() * on.length)], x = bx + ((b % cols) + .2 + Math.random() * .6) * cw, y = by + (Math.floor(b / cols) + .2 + Math.random() * .6) * ch;
        f[o] = x; f[o + 1] = y; f[o + 2] = (y - by) / bh; f[o + 3] = (x - bx) / bw;
      });
      rect.bits = { x: bx, y: by, w: bw, h: bh };
      const slab = $('#s-slab');
      slab.style.width = (isNarrow ? 54 : 96) + 'px'; slab.style.height = (bh + 30) + 'px'; slab.style.top = (by - 15) + 'px'; slab.style.left = '0';
      const tok = $('#s-token');
      tok.style.left = R3.x + 'px'; tok.style.width = R3.w + 'px'; tok.style.top = (by + bh + 12) + 'px';

      // the file
      const R4 = rect.a4, cardH = isNarrow ? 84 : 92;
      const fh = Math.min(R4.h - cardH - 20, isNarrow ? 240 : 400), fw = fh * .78;
      const pts = samplePixels(g => {
        const lw2 = Math.max(4, fw * .022), r = fw * .07, fold = fw * .26, x = lw2, y = lw2, w = fw - 2 * lw2, h = fh - 2 * lw2;
        g.strokeStyle = '#fff'; g.fillStyle = '#fff'; g.lineWidth = lw2; g.lineJoin = 'round';
        g.beginPath(); g.moveTo(x + r, y); g.lineTo(x + w - fold, y); g.lineTo(x + w, y + fold); g.lineTo(x + w, y + h - r);
        g.quadraticCurveTo(x + w, y + h, x + w - r, y + h); g.lineTo(x + r, y + h); g.quadraticCurveTo(x, y + h, x, y + h - r); g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y); g.closePath(); g.stroke();
        g.beginPath(); g.moveTo(x + w - fold, y); g.lineTo(x + w - fold, y + fold); g.lineTo(x + w, y + fold); g.stroke();
        let fs = fw * .17; g.font = `700 ${fs}px ${TF}, monospace`; g.textAlign = 'center'; g.textBaseline = 'middle';
        g.fillText('vault.dat', fw / 2, fh * .62);
      }, fw, fh);
      const fy = R4.y + (R4.h - cardH - 12 - fh) / 2;
      F.file = fromPts(pts, R4.x + (R4.w - fw) / 2, fy, fh);
      const fc = $('#s-file'), cw2 = Math.min(R4.w, 560);
      fc.style.width = cw2 + 'px'; fc.style.left = (R4.x + (R4.w - cw2) / 2) + 'px'; fc.style.top = (fy + fh + 12) + 'px';
      fillToken();
      seg = null;
    }

    /* ---------- token text ---------- */
    const tokEls = $$('#tok i');
    let tokParts = ['', '', '', ''], tokShown = -1;
    function fillToken() {
      const s = state.tokenStr || '';
      if (!s) return;
      const n = state.token.length, c = b => Math.floor(b * 4 / 3);
      tokParts = [s.slice(0, c(9)), s.slice(c(9), c(25)), s.slice(c(25), c(n - 32)), s.slice(c(n - 32))];
      tokShown = -1;
    }
    function showToken(frac) {
      const total = tokParts.join('').length, shown = Math.round(total * frac);
      if (shown === tokShown) return;
      tokShown = shown;
      let left = shown;
      tokParts.forEach((p, i) => { tokEls[i].textContent = p.slice(0, left); left = Math.max(0, left - p.length); });
    }

    /* ---------- timeline (c = act index + progress within the act) ---------- */
    const SEG = [
      [1.02, 1.5, 'key', 'pw', .2, .75],
      [1.74, 2.0, 'pw', 'pwS', .5, .12],
      [2.0, 2.13, 'pwS', 'grid', .45, .6],
      [2.8, 2.98, 'grid', 'key2', .45, .7],
      [3.03, 3.2, 'key2', 'entry', .45, 1],
      [3.28, 3.8, 'entry', 'bits', .14, .12],
      [4.0, 4.34, 'bits', 'file', .45, .8],
    ];
    let seg = null, acts = [], storyEnd = 0;
    function metrics() {
      const sy = scrollY;
      acts = $$('.act').map(a => { const r = a.getBoundingClientRect(); return { top: r.top + sy, h: r.height }; });
      const st = $('#story').getBoundingClientRect();
      storyEnd = st.top + sy + st.height - H;
    }
    const clock = y => {
      const m = y + H * .5;
      for (let i = acts.length - 1; i >= 0; i--) if (m >= acts[i].top) return i + clamp((m - acts[i].top) / acts[i].h);
      return 0;
    };
    function upload(a, b) {
      const A = F[a], B = F[b];
      for (let i = 0; i < N; i++) {
        const o = i * 7, k = i * 4;
        data[o] = A[k]; data[o + 1] = A[k + 1]; data[o + 2] = A[k + 2];
        data[o + 3] = B[k]; data[o + 4] = B[k + 1]; data[o + 5] = B[k + 2]; data[o + 6] = B[k + 3];
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferSubData(gl.ARRAY_BUFFER, 0, data);
    }
    const show = (el, a, tr) => {
      const on = a > .004;
      if (on !== el._on) { el.style.visibility = on ? 'visible' : 'hidden'; el._on = on; }
      if (on && a !== el._a) { el.style.opacity = a.toFixed(3); el._a = a; }
      if (on && tr !== undefined && tr !== el._t) { el.style.transform = tr; el._t = tr; }
    };
    const fades = (c, a, b, d = .05) => ss(a, a + d, c) * (1 - ss(b - d, b, c));

    /* ---------- render loop ---------- */
    const els = { login: $('#s-login'), dots: $('#dots'), grid: $('#s-grid'), key: $('#s-key'), slab: $('#s-slab'), token: $('#s-token'), file: $('#s-file'), pass: $('#h-pass'), blk: $('#h-blk'), addr: $('#h-addr'), bar: $('#bar') };
    const rail = $$('#rail li');
    const ptr = { x: -1e4, y: 0, z: 0, t: 0 };
    if (matchMedia('(pointer:fine)').matches) addEventListener('pointermove', e => { ptr.x = e.clientX; ptr.y = e.clientY; ptr.t = 1; }, { passive: true });

    let sm = scrollY, last = performance.now(), t0 = last, visible = true, arcsDirty = false, lastDots = -1, lastHud = '';
    new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }).observe($('#story'));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) kick(); });
    let raf = 0, lost = false;
    function kick() { if (!raf && !lost) { last = performance.now(); raf = requestAnimationFrame(frame); } }
    addEventListener('scroll', kick, { passive: true });

    function drawArcs(pass, f) {
      const G = gridGeom, tr = state.trace;
      if (!tr || !G) return;
      arc.setTransform(dpr, 0, 0, dpr, 0, 0);
      arc.clearRect(0, 0, W, H);
      arc.globalCompositeOperation = 'lighter';
      arc.lineCap = 'round';
      const cur = Math.floor(f * G.q), L = isNarrow ? 16 : 30;
      for (let k = 0; k < L; k++) {
        const idx = cur - k;
        if (idx < 2) break;
        const ref = tr.refs[pass * G.q + idx];
        if (ref === 65535) continue;
        const x1 = G.gx + (idx % G.side + .5) * G.cell, y1 = G.gy + (Math.floor(idx / G.side) + .5) * G.cell;
        const x2 = G.gx + (ref % G.side + .5) * G.cell, y2 = G.gy + (Math.floor(ref / G.side) + .5) * G.cell;
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, nx = -(y2 - y1), ny = x2 - x1;
        const a = (1 - k / L);
        const dep = !(pass === 0 && idx < G.q / 2);
        arc.strokeStyle = dep ? `rgba(240,92,240,${.85 * a})` : `rgba(160,220,255,${.85 * a})`;
        arc.lineWidth = 1.1 + 1.1 * a;
        if (PIXEL) { // кривая из квадратиков
          arc.fillStyle = arc.strokeStyle; const cx = mx + nx * .22, cy = my + ny * .22, n = Math.max(6, Math.hypot(x2 - x1, y2 - y1) / 5 | 0);
          for (let t = 0; t <= n; t++) { const u = t / n, v = 1 - u; arc.fillRect(Math.round((v * v * x1 + 2 * v * u * cx + u * u * x2) / 4) * 4, Math.round((v * v * y1 + 2 * v * u * cy + u * u * y2) / 4) * 4, 3, 3); }
        } else { arc.beginPath(); arc.moveTo(x1, y1); arc.quadraticCurveTo(mx + nx * .22, my + ny * .22, x2, y2); arc.stroke(); }
      }
      arcsDirty = true;
    }

    function frame(now) {
      raf = 0;
      if (!visible || document.hidden || lost) return;
      const dt = Math.min(.05, (now - last) / 1000); last = now;
      const y = scrollY, prev = sm;
      sm += (y - sm) * (1 - Math.exp(-dt * 8));
      if (Math.abs(y - sm) < .3) sm = y;
      const vel = Math.min(1, Math.abs(sm - prev) / (dt * 2600 + .001));
      const t = (now - t0) / 1000, c = clock(sm);
      els.bar.style.transform = `scaleX(${clamp(sm / storyEnd).toFixed(4)})`;

      // which pair of formations
      let A = 'scatter', B = 'key', mix = Math.min(1, t / 1.8), mixW = .45, spread = 1;
      for (const s of SEG) if (c >= s[0]) { A = s[2]; B = s[3]; mixW = s[4]; spread = s[5]; mix = clamp((c - s[0]) / (s[1] - s[0])); }
      const pair = A + '>' + B;
      if (pair !== seg && F[A] && F[B]) { upload(A, B); seg = pair; }

      // grid and particle visibility
      const gAlpha = ss(2.09, 2.15, c) * (1 - ss(2.86, 2.95, c));
      const gCol = ss(2.8, 2.95, c);
      const uProg = clamp((c - 2.15) / .64) * DEMO.t;
      const glowA = F[A].glow === undefined ? 1 : F[A].glow, glowB = F[B].glow === undefined ? 1 : F[B].glow;
      const pAlpha = ((1 - ss(2.11, 2.18, c)) + ss(2.8, 2.88, c)) * lerp(glowA, glowB, mix);

      gl.clear(gl.COLOR_BUFFER_BIT);
      const pointer = ptr.t ? 1 : 0;
      if (pAlpha > .01) {
        gl.useProgram(PP.p);
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.enableVertexAttribArray(PP.a.aA); gl.vertexAttribPointer(PP.a.aA, 3, gl.FLOAT, false, 28, 0);
        gl.enableVertexAttribArray(PP.a.aB); gl.vertexAttribPointer(PP.a.aB, 4, gl.FLOAT, false, 28, 12);
        gl.bindBuffer(gl.ARRAY_BUFFER, seed);
        gl.enableVertexAttribArray(PP.a.aS); gl.vertexAttribPointer(PP.a.aS, 3, gl.FLOAT, false, 0, 0);
        gl.uniform2f(PP.u.uRes, W, H); gl.uniform1f(PP.u.uMix, mix); gl.uniform1f(PP.u.uT, t); gl.uniform1f(PP.u.uJit, vel); gl.uniform1f(PP.u.uDpr, dpr);
        gl.uniform3f(PP.u.uPtr, ptr.x, ptr.y, pointer); gl.uniform1f(PP.u.uW, mixW); gl.uniform1f(PP.u.uSpread, spread);
        const base = isNarrow ? 1.7 : 2.1;
        if (bloom) {
          gl.uniform1f(PP.u.uSize, base * 5); gl.uniform1f(PP.u.uAlpha, .06 * pAlpha); gl.uniform1f(PP.u.uSoft, 0);
          gl.drawArrays(gl.POINTS, 0, N);
        }
        gl.uniform1f(PP.u.uSize, base); gl.uniform1f(PP.u.uAlpha, .85 * pAlpha); gl.uniform1f(PP.u.uSoft, .35);
        gl.drawArrays(gl.POINTS, 0, N);
      }
      if (gAlpha > .01 && gridGeom && state.trace) {
        const pass = Math.min(DEMO.t - 1, Math.floor(uProg)), f = uProg >= DEMO.t ? 1 : uProg - pass;
        const G = gridGeom;
        gl.useProgram(GP.p);
        gl.bindBuffer(gl.ARRAY_BUFFER, gbuf);
        gl.enableVertexAttribArray(GP.a.aP); gl.vertexAttribPointer(GP.a.aP, 2, gl.FLOAT, false, 24, 0);
        gl.enableVertexAttribArray(GP.a.aI); gl.vertexAttribPointer(GP.a.aI, 1, gl.FLOAT, false, 24, 8);
        gl.enableVertexAttribArray(GP.a.aS); gl.vertexAttribPointer(GP.a.aS, 3, gl.FLOAT, false, 24, 12);
        gl.uniform2f(GP.u.uRes, W, H); gl.uniform2f(GP.u.uCen, G.gx + G.gs / 2, G.gy + G.gs * .46);
        gl.uniform1f(GP.u.uF, f); gl.uniform1f(GP.u.uCell, G.cell); gl.uniform1f(GP.u.uDpr, dpr); gl.uniform1f(GP.u.uAlpha, gAlpha); gl.uniform1f(GP.u.uCol, gCol);
        gl.uniform1f(GP.u.uAny, pass > 0 ? 1 : 0);
        const m = i => [i === 0 ? 1 : 0, i === 1 ? 1 : 0, i === 2 ? 1 : 0];
        gl.uniform3fv(GP.u.uCur, m(pass)); gl.uniform3fv(GP.u.uPrev, m(Math.max(0, pass - 1)));
        gl.drawArrays(gl.POINTS, 0, G.q);
        const en = isEn(), blk = Math.min(G.q, Math.floor(f * G.q));
        const hud = `${pass + 1}/${f}/${blk}/${en}`;
        if (hud !== lastHud) {
          lastHud = hud;
          els.pass.textContent = (en ? 'pass ' : 'проход ') + (pass + 1) + '/' + DEMO.t;
          els.blk.textContent = (en ? 'block ' : 'блок ') + blk + '/' + G.q;
          els.addr.textContent = pass === 0 && blk < G.q / 2 ? (en ? "references don't depend on the password" : 'ссылки не зависят от пароля') : (en ? 'references depend on the data' : 'ссылки зависят от данных');
        }
        if (uProg > 0 && uProg < DEMO.t && gCol === 0) drawArcs(pass, f);
        else if (arcsDirty) { arc.clearRect(0, 0, W, H); arcsDirty = false; }
      } else if (arcsDirty) { arc.clearRect(0, 0, W, H); arcsDirty = false; }

      // DOM on the stage
      const typed = clamp((c - 1.02) / .46);
      show(els.login, fades(c, 1.0, 1.98, .06));
      const n = Math.round(typed * state.pw.length);
      if (n !== lastDots) { els.dots.textContent = '•'.repeat(n); lastDots = n; }
      show(els.grid, fades(c, 2.12, 2.86, .03));
      show(els.key, fades(c, 2.88, 3.2, .05));
      const sweepD = clamp((mix - mixW / 2) / (1 - mixW));
      aurora(c);
      if (B === 'bits') {
        const rb = rect.bits, slabW = isNarrow ? 54 : 96;
        const x = rb.x - slabW / 2 + (rb.w) * sweepD;
        show(els.slab, ss(0, .08, mix) * (1 - ss(.92, 1, mix)), `translate3d(${x.toFixed(1)}px,0,0)`);
      } else show(els.slab, 0);
      show(els.token, fades(c, 3.26, 3.96, .05));
      if (B === 'bits') showToken(sweepD);
      show(els.file, ss(4.22, 4.34, c));
      const ci = Math.floor(c);
      rail.forEach((li, i) => li.classList.toggle('on', i + 1 === ci));
      if (window.whoSound) whoSound.frame({ c, speed: vel, dots: n, grid: gAlpha, uProg, passes: DEMO.t, sealing: B === 'bits' && mix > 0 && mix < 1, sealProgress: sweepD });

      // keep drawing while something is alive: intro, inertia, shimmer in view
      if (visible) raf = requestAnimationFrame(frame);
    }

    const auroraEls = $$('.aurora i');
    function aurora(c) {
      const k = Math.round(c * 200);
      if (k === aurora.k) return;
      aurora.k = k;
      // each act has its own light: indigo while typing, magenta in the memory, cold for the file
      auroraEls[0].style.transform = `translate3d(${(c * 9 - 12).toFixed(1)}vw,${(Math.sin(c * 1.1) * 14).toFixed(1)}vh,0)`;
      auroraEls[1].style.transform = `translate3d(${(-c * 11).toFixed(1)}vw,${(10 + Math.cos(c * 1.4) * 18).toFixed(1)}vh,0)`;
      auroraEls[1].style.opacity = (0.55 + .45 * ss(1.8, 2.5, c) * (1 - ss(3.1, 4, c))).toFixed(2);
    }

    function layoutAll() {
      if (lost) return;
      measure();
      buildStatic();
      buildDemo();
      metrics();
    }
    rebuildDemoFormations = () => { if (lost) return; lastHud = ''; buildDemo(); metrics(); };
    layoutAll();
    onLang = () => { layoutAll(); seg = null; };
    let rt = 0, lastW = innerWidth, lastH = innerHeight;
    addEventListener('resize', () => {
      // phones change height when the address bar hides: not a reason to rebuild
      if (innerWidth === lastW && Math.abs(innerHeight - lastH) < 130) return;
      lastW = innerWidth; lastH = innerHeight;
      // видеокарту у страницы отняли: остаётся спокойная версия без частиц, иначе вместо сцены будет пустота
      if (lost) { drawStaticGrid(); return; }
      clearTimeout(rt);
      if (innerHeight < 500) { docEl.classList.remove('fx'); visible = false; drawStaticGrid(); return; }
      docEl.classList.add('fx');
      rt = setTimeout(() => { layoutAll(); seg = null; visible = true; kick(); }, 180);
    });
    addEventListener('load', metrics);
    gl.canvas.addEventListener('webglcontextlost', e => {
      e.preventDefault();
      lost = true; clearTimeout(rt); cancelAnimationFrame(raf); raf = 0;
      docEl.classList.remove('fx'); drawStaticGrid();
    });
    kick();
  }

  start();
})();
