// Data-driven H5 scene engine for the kids' English season.
// Needs: window.ITEMS / window.COVERS (items.js), window.DUR (voice durations), window.EP (episode spec).
// Exposes window.SEGMENTS {id: {type, dur, cues:[{key,start}]}} and window.renderAt(id, seconds) for capture.mjs.
// Every frame is a pure function of time: no CSS animation, no timers, no Math.random.
"use strict";
(function () {
  const EP = window.EP, D = window.DUR, ITEMS = window.ITEMS, COVERS = window.COVERS, FPS = 24;
  const W = 1280, H = 720, SAFE_BOTTOM = 600;      // subtitles live below y = 610
  const stage = document.getElementById("stage");
  // optional EP.skin = {items:{id:url}, covers:{id:url}, coverFront:{id:url}, bg:{name:url}, brush:url, ground:{bg:y},
  // focus:{id:[x,y]}, noShadow:[id]}: pre-rendered 3D-style images replace the flat vector art, and the engine adds depth
  // cues (ground shadows, real layering, camera drift, a gentle turn). season_lib builds it from assets/skin/manifest.json.
  const SKIN = EP.skin || null, skinOf = (kind, id) => (SKIN && SKIN[kind] && SKIN[kind][id]) || null;
  if (SKIN) stage.classList.add("skin");
  let NOW = 0, GROUND = 0;
  const NS = "http://www.w3.org/2000/svg";
  const ALL = [];
  const el = (tag, cls, html, parent = stage) => {
    const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html;
    parent.appendChild(e); return e;
  };
  for (const k of Object.keys(D)) if (!EP.lines || !(k in EP.lines)) { /* durations may include unused lines */ }

  // ---------- backgrounds ----------
  const BG = {
    outdoor: `<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cdeeff"/><stop offset="1" stop-color="#f3fbff"/></linearGradient></defs>
      <rect width="1280" height="720" fill="url(#sky)"/><circle cx="1120" cy="120" r="64" fill="#ffe08a"/>
      <g fill="#fff"><ellipse cx="230" cy="130" rx="90" ry="34"/><ellipse cx="300" cy="108" rx="60" ry="30"/><ellipse cx="820" cy="90" rx="80" ry="28"/><ellipse cx="760" cy="104" rx="56" ry="24"/></g>
      <path d="M0 560 Q320 440 660 550 T1280 520 V720 H0Z" fill="#c9eab8"/><path d="M0 630 Q360 540 760 630 T1280 610 V720 H0Z" fill="#a9dd98"/>`,
    indoor: `<rect width="1280" height="720" fill="#fff4e3"/><g fill="#ffe7c7">${Array.from({ length: 14 }, (_, i) => `<rect x="${i * 96}" y="0" width="48" height="520"/>`).join("")}</g>
      <rect x="960" y="80" width="220" height="180" rx="16" fill="#cdeeff" stroke="#e8c79a" stroke-width="14"/><path d="M1070 80 V260 M960 170 H1180" stroke="#e8c79a" stroke-width="10"/>
      <rect y="520" width="1280" height="200" fill="#e7c194"/><path d="M0 520 H1280" stroke="#d2a777" stroke-width="10"/>
      ${Array.from({ length: 9 }, (_, i) => `<path d="M${i * 160} 520 L${i * 160 - 80} 720" stroke="#d9b083" stroke-width="5"/>`).join("")}`,
    party: null,  // indoor + bunting, built below
  };
  BG.party = BG.indoor + `<path d="M0 40 Q640 150 1280 40" stroke="#c9a06a" stroke-width="4" fill="none"/>` +
    Array.from({ length: 16 }, (_, i) => { const x = 40 + i * 80, y = 40 + 110 * Math.sin(Math.PI * (x / 1280)) * 0.95;
      const c = ["#e8413c", "#ffd23f", "#3f8fe8", "#4fbf5a"][i % 4];
      return `<path d="M${x - 26} ${y - 4} L${x + 26} ${y - 4} L${x} ${y + 44}Z" fill="${c}"/>`; }).join("");
  const bgEls = {};
  for (const [k, v] of Object.entries(BG)) { const src = skinOf("bg", k);
    bgEls[k] = el("div", "bg", src ? `<img src="${src}" width="1280" height="720" decoding="sync">` : `<svg width="1280" height="720" viewBox="0 0 1280 720">${v}</svg>`); }
  function setBg(name, gray = 0) {
    for (const [k, e] of Object.entries(bgEls)) e.style.opacity = k === name ? 1 : 0;
    bgEls[name].style.filter = gray ? `grayscale(${gray}) brightness(${1 - 0.1 * gray})` : "none";
    if (SKIN) GROUND = (typeof SKIN.ground === "object" ? SKIN.ground[name] : SKIN.ground) || 0;
    const img = bgEls[name].firstElementChild;      // slow camera drift: the backdrop moves, the items do not (parallax)
    if (img && img.tagName === "IMG") img.style.transform =
      `translate(${(Math.sin(NOW * 0.35) * 12).toFixed(2)}px,${(Math.cos(NOW * 0.27) * 5).toFixed(2)}px) scale(${(1.07 + 0.012 * Math.sin(NOW * 0.2)).toFixed(4)})`;
  }

  // ---------- shared props ----------
  const rainbow = el("div", "fx", `<svg width="1280" height="720" viewBox="0 0 1280 720" fill="none" stroke-linecap="round">
    <path pathLength="1" d="M 60 760 A 580 580 0 0 1 1220 760" stroke="#e8413c" stroke-width="38"/>
    <path pathLength="1" d="M 100 760 A 540 540 0 0 1 1180 760" stroke="#ffd23f" stroke-width="38"/>
    <path pathLength="1" d="M 140 760 A 500 500 0 0 1 1140 760" stroke="#4fbf5a" stroke-width="38"/>
    <path pathLength="1" d="M 180 760 A 460 460 0 0 1 1100 760" stroke="#3f8fe8" stroke-width="38"/></svg>`);
  const rainbowArcs = [...rainbow.querySelectorAll("path")];
  function setRainbow(prog, o = 1) {
    put(rainbow, { x: W / 2, y: H / 2, o });
    rainbowArcs.forEach((a, i) => { const u = easeInOut(clamp(prog * 1.3 - i * 0.1));
      a.setAttribute("stroke-dasharray", "1"); a.setAttribute("stroke-dashoffset", String(1 - u)); });
  }
  const ring = el("div", "ring"), flash = el("div", "flash"), qmark = el("div", "qmark", "?");
  // SKIN.anim[id] = {sheet, cols, rows, n, fps}: a looping sprite sheet (a rabbit that really hops, a dog that really
  // runs). The frame is a pure function of time; such items get no extra hop / wiggle from the engine.
  const animOf = id => (SKIN && SKIN.anim && SKIN.anim[id]) || null;
  const IT = id => (animOf(id) ? { ...ITEMS[id], idle: "none", act: "still" } : ITEMS[id]);
  if (SKIN) for (const a of Object.values(SKIN.anim || {})) { const pre = el("img"); pre.src = a.sheet; pre.decoding = "sync"; pre.style.display = "none"; }
  const art = (src, svg) => src ? `<img src="${src}" width="200" height="200" decoding="sync">` : `<svg viewBox="0 0 200 200" width="200" height="200">${svg}</svg>`;
  const shadowFor = e => { e._skin = true; e._sh = el("div", "shadow"); ALL.push(e._sh); return e; };
  // a skinned cover can come in two layers: the whole thing behind the items, and its front wall in front of them,
  // so that a fruit in the basket is in front of the far rim and behind the near one
  const covers = {};
  for (const [k, v] of Object.entries(COVERS)) {
    const src = skinOf("covers", k), front = skinOf("coverFront", k);
    covers[k] = el("div", "obj cover" + (front ? " back" : ""), art(src, v));
    if (src) shadowFor(covers[k]);
    if (front) { covers[k]._front = el("div", "obj cover", art(front, "")); ALL.push(covers[k]._front); }
  }
  // items are created lazily, several copies per id (counting, rows)
  const itemPool = {};
  function itemEl(id, copy = 0) {
    if (!ITEMS[id]) throw new Error("unknown item " + id);
    const key = id + "#" + copy;
    if (!itemPool[key]) {
      const an = animOf(id);
      const e = el("div", "obj", an ? `<div class="anim" style="background-image:url('${an.sheet}');background-size:${an.cols * 200}px ${an.rows * 200}px;transform:scale(${an.zoom || 1})"></div>`
        : art(skinOf("items", id), ITEMS[id].svg));
      if (an) { e._anim = an; e._cell = e.firstElementChild; }
      if (skinOf("items", id)) { if ((SKIN.noShadow || []).includes(id)) e._skin = true; else shadowFor(e); }
      itemPool[key] = e; ALL.push(e);
    }
    return itemPool[key];
  }
  if (SKIN) for (const id of Object.keys(SKIN.items || {})) for (let c = 0; c < 6; c++) itemEl(id, c);   // images must be loaded before capture starts
  const wordPool = {};
  function wordEl(text, color) {
    const key = text + "|" + color;
    if (!wordPool[key]) { const e = el("div", "word", text); e.style.color = color; e._w = null; wordPool[key] = e; ALL.push(e); }
    return wordPool[key];
  }
  const fitScale = (e, maxW) => { if (e._w === null || e._w === undefined) e._w = e.offsetWidth || 1; return Math.min(1, maxW / e._w); };
  const hero = el("div", "hero");
  const letters = [..."FENLO"].map((c, i) => { const e = el("div", "letter", c); e.style.color = ["#e8413c", "#f0b400", "#3f8fe8", "#3fae4b", "#e8413c"][i]; return e; });
  const dots = [0, 1, 2, 3].map(() => el("div", "dot"));
  const sparks = Array.from({ length: 18 }, () => {
    const s = document.createElementNS(NS, "svg"); s.setAttribute("class", "spark"); s.setAttribute("viewBox", "0 0 44 44");
    s.innerHTML = '<path d="M22 2 L27 17 L42 22 L27 27 L22 42 L17 27 L2 22 L17 17Z" fill="#ffd23f" stroke="#fff" stroke-width="2.5"/>';
    stage.appendChild(s); return s; });
  const brush = el("div", "brush", `<svg width="220" height="220" viewBox="0 0 220 220"><g transform="rotate(35 110 110)">
    <rect x="98" y="96" width="24" height="112" rx="10" fill="#b9793a"/><rect x="92" y="74" width="36" height="28" rx="4" fill="#c9ced6"/>
    <path d="M92 76 Q90 34 110 12 Q130 34 128 76Z" fill="#ffe7a3"/><circle cx="110" cy="34" r="26" fill="#fff6c9" opacity=".75"/></g></svg>`);
  if (SKIN && SKIN.brush) brush.innerHTML = `<img src="${SKIN.brush}" width="220" height="220" decoding="sync">`;
  const handPath = "M62 14 C72 10 80 16 80 26 V70 C96 66 122 72 124 92 C126 116 116 140 88 140 H70 C52 140 36 118 30 98 C26 86 42 80 50 92 V26 C50 20 54 16 62 14Z";
  const hand = el("div", "hand", `<svg width="150" height="150" viewBox="0 0 150 150"><path d="${handPath}" fill="#ffd9b0" stroke="#fff" stroke-width="8" stroke-linejoin="round"/>
    <path d="${handPath}" fill="#ffd9b0" stroke="#d99a66" stroke-width="3" stroke-linejoin="round"/></svg>`);
  ALL.push(rainbow, ring, flash, qmark, hero, brush, hand, ...letters, ...dots, ...sparks, ...Object.values(covers));

  // ---------- math (pure functions of time) ----------
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const p = (t, a, b) => clamp((t - a) / (b - a));
  const lerp = (a, b, u) => a + (b - a) * u;
  const easeInOut = u => u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
  const easeOut = u => 1 - Math.pow(1 - u, 3);
  const easeOutBack = u => { const c = 1.9; return u <= 0 ? 0 : u >= 1 ? 1 : 1 + (c + 1) * Math.pow(u - 1, 3) + c * Math.pow(u - 1, 2); };
  const rnd = (i, k) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
  const pulse = (t, starts, len) => { let v = 0; for (const s of starts) { const u = (t - s) / len; if (u > 0 && u < 1) v = Math.max(v, Math.sin(u * Math.PI)); } return v; };
  function put(e, { x, y, s = 1, r = 0, o = 1, sx = 1, ry = 0 }) {
    e.style.opacity = o;
    e.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%) ${ry ? `perspective(700px) rotateY(${ry.toFixed(2)}deg) ` : ""}rotate(${r}deg) scale(${s * sx},${s})`;
  }
  // put() for items and covers. With a skin: a gentle turn in depth, and a soft shadow on the ground under the item
  // (restY = the item's resting centre; the shadow shrinks and fades as the item rises or hovers higher above the ground).
  function putItem(e, o, restY, i = 0) {
    if (!e._skin) return put(e, o);
    if (e._anim) { const k = Math.floor(NOW * e._anim.fps + i * 3) % e._anim.n;
      e._cell.style.backgroundPosition = `${-(k % e._anim.cols) * 200}px ${-Math.floor(k / e._anim.cols) * 200}px`; o = { ...o, ry: 0 }; }
    put(e, { ...o, ry: o.ry ?? Math.sin(NOW * 1.1 + i * 1.7) * 10 });
    if (e._front) put(e._front, o);
    if (!e._sh || restY === undefined || o.o === 0) return;
    const s = o.s ?? 1, bottom = o.y + 92 * s, gy = Math.max(restY + 92 * s + 8, GROUND);
    const k = 1 / (1 + Math.max(0, gy - bottom) / 150);
    put(e._sh, { x: o.x, y: gy, s: s * (0.55 + 0.45 * k), o: (o.o ?? 1) * (0.25 + 0.75 * k) });
  }

  // idle and action motion offsets for an item: returns {dx, dy, r, sx}
  function idleMotion(kind, t, i) {
    switch (kind) {
      case "float": return { dx: Math.sin(t * 1.3 + i) * 6, dy: Math.sin(t * 1.9 + i * 2) * 9, r: Math.sin(t * 1.3 + i) * 4 };
      case "swim": return { dx: Math.sin(t * 1.6 + i) * 14, dy: Math.sin(t * 2.4 + i) * 6, r: Math.sin(t * 2.4 + i) * 5 };
      case "none": return { dx: 0, dy: 0, r: 0 };
      default: return { dx: 0, dy: Math.sin(t * 2.2 + i * 1.3) * 5, r: 0 };
    }
  }
  function actMotion(kind, u) {        // u = seconds since the action started (the action lasts ~1.6 s)
    if (u < 0 || u > 1.6) return { dx: 0, dy: 0, r: 0, sx: 1 };
    const fade = 1 - p(u, 1.3, 1.6);
    switch (kind) {
      case "hop": return { dx: 0, dy: -Math.abs(Math.sin(u * Math.PI * 2.5)) * 60 * fade, r: 0, sx: 1 };
      case "run": return { dx: Math.sin(u * 14) * 10 * fade, dy: -Math.abs(Math.sin(u * 14)) * 14 * fade, r: Math.sin(u * 14) * 4 * fade, sx: 1 };
      case "swim": return { dx: Math.sin(u * 5) * 40 * fade, dy: Math.sin(u * 10) * 10 * fade, r: Math.sin(u * 10) * 8 * fade, sx: 1 };
      case "still": return { dx: 0, dy: 0, r: 0, sx: 1 };
      case "clap": return { dx: 0, dy: 0, r: 0, sx: 1 - 0.45 * Math.abs(Math.sin(u * Math.PI * 3)) * fade };
      case "wiggle": return { dx: 0, dy: 0, r: Math.sin(u * 18) * 9 * fade, sx: 1 };
      default: return { dx: 0, dy: -Math.abs(Math.sin(u * Math.PI * 2)) * 40 * fade, r: 0, sx: 1 };
    }
  }

  const rise = (t, r0) => (t >= r0 ? clamp(easeOutBack(p(t, r0, r0 + 0.5)) * 3) : 0);
  function brushSweep(t, s, X, Y, spread = 240) {
    const LEN = 1.6, tip = u => ({ x: lerp(X - 380, X + 380, u), y: Y - 300 + Math.pow(u - .5, 2) * 320 });
    const u = (t - s) / LEN;
    if (u > 0 && u < 1) { const b = tip(u); put(brush, { x: b.x, y: b.y, r: -25 + u * 40, o: Math.min(1, u * 8, (1 - u) * 8) }); }
    sparks.forEach((sp, i) => {
      const te = s + 0.2 + i * 0.07, k = (t - te) / 0.85;
      if (k <= 0 || k >= 1) return;
      const a = tip(clamp((te - s) / LEN)), e = easeInOut(k);
      put(sp, { x: lerp(a.x, X + (rnd(i, 1) - .5) * spread, e), y: lerp(a.y - 40, Y + (rnd(i, 2) - .5) * 220, e),
        s: 0.5 + rnd(i, 3) * 0.7, r: k * 200, o: Math.sin(k * Math.PI) });
    });
  }
  function burst(t, s, X, Y) {          // sparks flying out of a point (brush ritual, magic moments)
    sparks.forEach((sp, i) => {
      const k = (t - s - i * 0.02) / 0.9; if (k <= 0 || k >= 1) return;
      const a = rnd(i, 4) * Math.PI * 2, d = 80 + rnd(i, 5) * 160, e = easeOut(k);
      put(sp, { x: X + Math.cos(a) * d * e, y: Y + Math.sin(a) * d * e, s: 0.5 + rnd(i, 3) * 0.7, r: k * 240, o: Math.sin(k * Math.PI) });
    });
  }

  // ---------- timeline builders: all timing comes from the real voice durations ----------
  function seq() {
    const cues = []; let t = 0;
    return { cues, at(x) { t = x; return this; }, wait(x) { t += x; return this; },
      say(key) { if (!D[key]) throw new Error("no duration for line " + key); cues.push({ key, start: +t.toFixed(3) }); t += D[key].dur; return this; },
      get t() { return t; } };
  }
  const segItems = seg => seg.items || Array.from({ length: seg.count || 1 }, () => seg.item);

  function buildIntro(seg) {
    const s = seq().at(2.5).say(seg.say || "m_hello");
    return { type: "intro", seg, cues: s.cues, dur: s.t + 1.5 };
  }
  function buildOutro(seg) {
    const s = seq().at(0.9).say(seg.say || "m_bye");
    return { type: "outro", seg, cues: s.cues, dur: s.t + 2.2 };
  }
  function runBeats(s, beats) {
    const out = [];
    for (const b of beats) {
      const bt = { ...b, t: s.t };
      if (b.say) s.say(b.say); else s.wait(b.hold || 1.0);
      bt.end = s.t; s.wait(b.after ?? 1.0); bt.after = s.t; out.push(bt);
    }
    return out;
  }
  function buildTeach(seg) {
    const n = segItems(seg).length, m = { sweep: 0.8, reveal: [] };
    for (let i = 0; i < n; i++) m.reveal.push(1.6 + i * (seg.stagger ?? 0.55));
    const s = seq().at(m.reveal[n - 1] + 1.0);
    m.beats = runBeats(s, seg.beats || []);
    const first = f => m.beats.find(f);
    m.q = first(b => b.q); m.word = first(b => b.word); m.peekUp = first(b => b.word || b.show); m.fill = first(b => b.fill);
    return { type: "teach", seg, m, cues: s.cues, dur: s.t + 0.4 };
  }
  function buildQuiz(seg) {
    const s = seq().at(1.2), rounds = [];
    for (const r0 of seg.rounds) {
      const r = { ...r0 };
      r.ask = s.t; s.say(r0.ask); r.askEnd = s.t;
      s.wait(r0.wait ?? (r0.demo ? 2.4 : 4.0)); r.hit = s.t;
      const answers = Array.isArray(r0.answer) ? r0.answer : (r0.answer ? [r0.answer] : []);
      answers.forEach((a, j) => { if (j) s.wait(0.3); s.say(a); });
      if (!answers.length) s.wait(1.2);
      r.hitEnd = s.t;
      s.wait(1.0); r.clear = s.t; s.wait(0.5); rounds.push(r);
    }
    return { type: "quiz", seg, m: { rounds }, cues: s.cues, dur: s.t + 0.4 };
  }
  function buildChant(seg) {
    // gap: silence after each line (4 s when the line is an instruction the child should act on)
    const slot = Math.max(2.6, Math.max(...seg.lines.map(l => D[l.say].dur)) + (seg.gap ?? 0.45));
    const s = seq(), lines = [], rep = seg.repeat || 2;
    let k = 0;
    for (let r = 0; r < rep; r++) for (const l of seg.lines) {
      s.at(0.8 + k * slot); lines.push({ ...l, start: s.t, d: D[l.say].dur }); s.say(l.say); k++;
    }
    return { type: "chant", seg, m: { lines }, cues: s.cues, dur: 0.8 + k * slot + 0.4 };
  }
  function buildRitual(seg) {   // "My magic paintbrush!": Fenlo raises the brush, the tip bursts into sparkles
    const s = seq().at(0.9).say(seg.say || "m_brush");
    return { type: "ritual", seg, cues: s.cues, dur: s.t + 1.0 };
  }
  const BUILD = { intro: buildIntro, outro: buildOutro, teach: buildTeach, quiz: buildQuiz, chant: buildChant, ritual: buildRitual };
  const SEGMENTS = {};
  for (const seg of EP.segments) {
    const S = BUILD[seg.type](seg);
    S.dur = Math.ceil(S.dur * FPS) / FPS;
    SEGMENTS[seg.id] = S;
  }
  window.SEGMENTS = SEGMENTS;

  // ---------- renderers ----------
  const rowX = n => n === 1 ? [640] : Array.from({ length: n }, (_, i) => 640 + (i - (n - 1) / 2) * Math.min(293, 1100 / n));
  const bgOf = seg => seg.bg || EP.bg || "outdoor";

  function rIntro(t, S) {
    setBg(bgOf(S.seg));
    // 2-second brush ritual: the brush rises and bursts into sparkles
    const up = easeOutBack(p(t, 0.1, 0.8)), out = 1 - p(t, 1.7, 2.1);
    if (out > 0) put(brush, { x: 640, y: lerp(820, 360, up), s: 1.25, r: -10 + Math.sin(t * 6) * 4 * up, o: out });
    burst(t, 0.9, 640, 260);
    setRainbow(p(t, 1.6, 2.8));
    put(hero, { x: 340, y: 400 + Math.sin(t * 2.4) * 8, s: easeOutBack(p(t, 2.0, 2.6)), r: Math.sin(t * 2) * 4, o: p(t, 2.0, 2.1) });
    letters.forEach((l, i) => { const a = 2.3 + i * 0.16, k = p(t, a, a + 0.45);
      if (k > 0) put(l, { x: 600 + i * 122, y: 400 - 14 * pulse(t, [a + 0.9 + i * 0.1], 0.5), s: 0.9 * easeOutBack(k), r: (i % 2 ? 5 : -5) }); });
  }
  function rOutro(t, S) {
    setBg(bgOf(S.seg)); setRainbow(1, 0.3);
    const ids = S.seg.items || [], xs = rowX(ids.length);
    ids.forEach((id, i) => { const it = IT(id), k = easeOutBack(p(t, 0.1 + i * 0.12, 0.6 + i * 0.12));
      const oe = itemEl(id, i); oe.style.clipPath = "none"; oe.style.filter = "none";
      putItem(oe, { x: xs[i], y: 150 + Math.sin(t * 2 + i) * 6, s: 0.8 * k * ((S.seg.scales && S.seg.scales[i]) || 1), o: clamp(k * 3) }, undefined, i);
      const w = wordEl((S.seg.words && S.seg.words[i]) || it.word, it.color);
      const col = ids.length > 1 ? xs[1] - xs[0] : 600;   // keep each label inside its own column
      put(w, { x: xs[i], y: 300, s: 0.5 * k * fitScale(w, Math.min(520, col * 1.8)), o: clamp(k * 3) }); });
    put(hero, { x: 640, y: 480, s: 0.58 * easeOutBack(p(t, 0.6, 1.1)), r: Math.sin(t * 5) * 9, o: p(t, 0.6, 0.7) });
  }

  function rTeach(t, S) {
    const seg = S.seg, m = S.m, ids = segItems(seg), n = ids.length;
    setBg(bgOf(seg), seg.gray ? 1 : 0);
    const X = seg.x ?? 400, Y = seg.y ?? 360, wx = seg.wordX ?? 930, wy = seg.wordY ?? 350;
    const base = seg.scale ?? (n === 1 ? 1.8 : n === 2 ? 1.25 : 1.0);
    const gap = seg.gap ?? (n === 2 ? 250 : 190);
    let grow = 1;
    for (const b of m.beats) if (b.grow) grow = lerp(grow, b.grow, easeInOut(p(t, b.t, b.t + 0.6)));
    const pulses = m.beats.filter(b => b.pulse).map(b => b.t);
    brushSweep(t, m.sweep, X, Y, n > 1 ? 120 + gap * n : 240);
    // cover (basket / bush) for "peek" reveals
    const cov = seg.cover && covers[seg.cover];
    ids.forEach((id, i) => {
      const it = IT(id), e = itemEl(id, i), x = X + (i - (n - 1) / 2) * gap;
      const r0 = m.reveal[i], im = idleMotion(it.idle, t, i);
      let dx = im.dx, dy = im.dy, rot = im.r, sx = 1;
      for (const b of m.beats) if (b.act && (b.act === true || b.act === i + 1)) {
        const am = actMotion(it.act || "hop", t - b.t); dx += am.dx; dy += am.dy; rot += am.r; sx *= am.sx; }
      for (const b of m.beats) if (b.countPulse) { const step = (b.end - b.t) / n;
        dy -= 30 * pulse(t, [b.t + i * step], Math.max(0.35, step)); }
      let s = base * ((seg.scales && seg.scales[i]) || 1) * grow * (1 + 0.12 * pulse(t, pulses, 0.5));
      let o = 1, clip = "none", filter = "none";
      const mode = seg.reveal || "draw";
      if (mode === "draw") { const k = easeOut(p(t, r0, r0 + 0.75)); o = k > 0 ? 1 : 0; clip = `circle(${(k * 75).toFixed(2)}% at 50% 55%)`;
        s *= 0.92 + 0.08 * easeOutBack(p(t, r0, r0 + 0.75)); }
      else if (mode === "pop") { const k = easeOutBack(p(t, r0, r0 + 0.5)); s *= k; o = clamp(k * 3); }
      else if (mode === "color") { o = p(t, 0.3, 0.4); const g = 1 - easeInOut(p(t, r0, r0 + 1.0)); filter = `grayscale(${g}) brightness(${1 + 0.4 * g})`;
        const f = (t - r0) / 0.9; if (f > 0 && f < 1) put(flash, { x, y: Y, s: 0.7 + f * 1.5, o: (1 - f) * 0.6 }); }
      else if (mode === "peek") {
        const up = m.peekUp ? easeOutBack(p(t, m.peekUp.t, m.peekUp.t + 0.6)) : 0, rise = easeOut(p(t, r0, r0 + 0.6));
        // with a two-layer basket the item sits visibly inside it (only its foot is behind the near rim), then lifts out
        const split = cov && cov._front;
        dy += lerp(lerp(150, seg.peekY ?? (split ? 20 : 70), rise), seg.upY ?? (split ? -75 : -40), up);
        o = rise > 0 ? 1 : 0;
      }
      // ghost copies: a pale outline that is "painted in" on the fill beat (the missing third balloon)
      if ((seg.ghost || []).includes(i)) {        // stays a pale outline unless a fill beat paints it in
        const k = m.fill ? easeOut(p(t, m.fill.t, m.fill.t + 0.6)) : 0;
        clip = "none"; o = rise(t, r0) * (0.3 + 0.7 * k);
        filter = k < 1 ? `grayscale(${1 - k}) brightness(${1 + 0.45 * (1 - k)})` : "none";
        if (m.fill) { s *= 1 + 0.18 * pulse(t, [m.fill.t], 0.6);
          const f = (t - m.fill.t) / 0.9; if (f > 0 && f < 1) put(flash, { x, y: Y, s: 0.6 + f * 1.2, o: (1 - f) * 0.6 }); }
      }
      // swapTo: the item turns into another one on the fill beat (portrait without nose -> with nose)
      let swapK = 0;
      if (seg.swapTo && m.fill) {
        swapK = easeInOut(p(t, m.fill.t, m.fill.t + 0.45));
        const se = itemEl(seg.swapTo, 9);
        se.style.clipPath = "none"; se.style.filter = "none";
        put(se, { x: x + dx, y: Y + dy, s: s * (1 + 0.12 * pulse(t, [m.fill.t], 0.6)), r: rot, o: swapK * (o > 0 ? 1 : 0), sx });
        const f = (t - m.fill.t) / 0.9; if (f > 0 && f < 1) put(flash, { x, y: Y, s: 0.6 + f * 1.2, o: (1 - f) * 0.6 });
        burst(t, m.fill.t, x, Y);
      }
      e.style.clipPath = clip; e.style.filter = filter;
      putItem(e, { x: x + dx, y: Y + dy, s, r: rot, o: o * (1 - swapK), sx }, mode === "peek" && cov ? undefined : Y, i);
    });
    if (cov && (seg.reveal === "peek")) {   // one cover in front of all the hiding items
      const ck = easeOutBack(p(t, 0.2, 0.7)), wide = n > 1 ? 1 + 0.32 * (n - 1) : 1;
      putItem(cov, { x: X, y: Y + 150, s: 1.9 * ck, sx: wide, o: clamp(ck * 3), ry: 0 }, Y + 150);
    }
    // question mark from the question beat until the answer word appears
    if (m.q) { const end = m.word ? m.word.t : m.q.after;
      const qo = p(t, m.q.t, m.q.t + 0.25) * (1 - p(t, end - 0.25, end));
      if (qo > 0) put(qmark, { x: wx, y: 340 + Math.sin(t * 3) * 10, s: easeOutBack(p(t, m.q.t, m.q.t + 0.45)), r: Math.sin(t * 2) * 6, o: qo }); }
    if (m.word) {
      const it = ITEMS[ids[0]], w = wordEl(seg.word || it.word, seg.color || it.color), wp = p(t, m.word.t, m.word.t + 0.45);
      if (wp > 0) put(w, { x: wx, y: wy, s: easeOutBack(wp) * fitScale(w, seg.wordMax ?? 600) * (1 + 0.14 * pulse(t, pulses, 0.5)) });
    }
    // pointing hand (TPR demo / "point to")
    for (const b of m.beats) if (b.point) {
      const id = ids[0], it = ITEMS[id], f = (SKIN && SKIN.focus && SKIN.focus[id]) || it.focus || [100, 100];
      const tx = X + (f[0] - 100) * base * grow, ty = Y + (f[1] - 100) * base * grow;
      const k = easeInOut(p(t, b.t, b.t + 1.0)), o = p(t, b.t, b.t + 0.3) * (1 - p(t, b.after - 0.3, b.after));
      if (o > 0) put(hand, { x: lerp(640, tx + 40, k), y: lerp(700, ty + 70, k) + 6 * pulse(t, [b.t + 1.0], 0.4), o });
    }
  }

  // quiz items are item ids, or {key, id, scale, word} when the same item appears in two sizes (big ball / small ball)
  const qItem = q => (typeof q === "string" ? { key: q, id: q, scale: 1 } : { scale: 1, ...q, key: q.key || q.id });
  function rQuiz(t, S) {
    const seg = S.seg, rounds = S.m.rounds, list = seg.items.map(qItem), ids = list.map(q => q.key), xs = rowX(ids.length), Y = 380;
    const sc = seg.scale ?? (ids.length <= 2 ? 1.25 : ids.length === 3 ? 1.1 : 0.95);
    setBg(bgOf(seg));
    const act = rounds.find(r => t >= r.hit && t < r.clear);
    list.forEach((q, i) => {
      const id = q.key, it = IT(q.id), e = itemEl(q.id, i), pop = easeOutBack(p(t, 0.15 + i * 0.12, 0.7 + i * 0.12)), im = idleMotion(it.idle, t, i);
      let s = sc * q.scale * pop, o = clamp(pop * 3), dx = im.dx, dy = im.dy, rot = im.r, sx = 1, dim = 0;
      if (act) {
        const k = easeOutBack(p(t, act.hit, act.hit + 0.4)) * (1 - p(t, act.clear - 0.3, act.clear));
        if (act.target === id) {
          s *= 1 + 0.3 * k; put(ring, { x: xs[i], y: Y, s: (0.6 + 0.5 * k) * sc * Math.max(0.7, q.scale) / 0.95, o: clamp(k) });
          const w = wordEl(act.word || q.word || it.word, it.color);
          put(w, { x: xs[i], y: Y - 205 * sc * Math.max(0.75, q.scale) / 0.95, s: 0.6 * clamp(k) * fitScale(w, 420), o: clamp(k) });
          if (act.act) { const am = actMotion(it.act || "hop", t - act.hit); dx += am.dx; dy += am.dy; rot += am.r; sx = am.sx; }
        } else if (e._skin) dim = clamp(k);      // image items stay solid: they lose colour instead of turning see-through
        else o *= 1 - 0.6 * clamp(k);
      }
      e.style.clipPath = "none"; e.style.filter = dim ? `grayscale(${0.45 * dim}) brightness(${1 + 0.18 * dim}) opacity(${1 - 0.35 * dim})` : "none";
      putItem(e, { x: xs[i] + dx, y: Y + dy, s, r: rot, o, sx }, Y, i);
    });
    for (const r of rounds) {
      if (!ids.includes(r.target)) throw new Error("quiz target not in row: " + r.target);
      const x = xs[ids.indexOf(r.target)];
      if (r.demo) {
        const k = easeInOut(p(t, r.askEnd, r.askEnd + 1.6)), o = p(t, r.ask, r.ask + 0.3) * (1 - p(t, r.clear - 0.3, r.clear));
        if (o > 0) put(hand, { x: lerp(640, x + 30, k), y: lerp(680, Y + 170, k) + 6 * pulse(t, [r.hit], 0.4), s: 1 - 0.1 * pulse(t, [r.hit], 0.4), o });
      } else if (t >= r.askEnd && t < r.hit + 0.2) {   // thinking timer: dots fill during the pause
        const pause = r.hit - r.askEnd;
        dots.forEach((d, j) => { const k = p(t, r.askEnd + j * pause / 4, r.askEnd + j * pause / 4 + 0.3);
          put(d, { x: 565 + j * 50, y: 110, s: 0.6 + 0.4 * easeOutBack(k), o: (0.3 + 0.7 * k) * (1 - p(t, r.hit, r.hit + 0.2)) }); });
      }
    }
  }

  function rChant(t, S) {
    const seg = S.seg;
    setBg(bgOf(seg));
    if (seg.lines.some(l => l.show)) return rChantGroups(t, S);
    const ids = seg.items, xs = rowX(ids.length), Y = 280;
    const sc = ids.length <= 3 ? 1.1 : 0.95;
    const line = S.m.lines.find(l => t >= l.start && t < l.start + l.d + 0.5);
    ids.forEach((id, i) => {
      const it = IT(id), e = itemEl(id), pop = easeOutBack(p(t, 0.1 + i * 0.1, 0.6 + i * 0.1)), im = idleMotion(it.idle, t, i);
      let y = Y + im.dy, s = sc * pop;
      if (line && line.item === id) {
        const u = p(t, line.start, line.start + line.d), k = easeOutBack(p(t, line.start, line.start + 0.3)) * (1 - p(t, line.start + line.d + 0.2, line.start + line.d + 0.5));
        y -= Math.abs(Math.sin(u * Math.PI * 3)) * 50; s *= 1 + 0.25 * k;
        const w = wordEl(line.word || it.word, it.color);
        put(w, { x: xs[i], y: Y + 190, s: 0.6 * clamp(k) * fitScale(w, 440), o: clamp(k) });
      }
      e.style.clipPath = "none"; e.style.filter = "none";
      putItem(e, { x: xs[i] + im.dx, y, s, r: im.r, o: clamp(pop * 3) }, Y, i);
    });
  }

  // chant where each line shows its own group of items (e.g. 1, 2, then 3 balloons); the previous group leaves first
  function rChantGroups(t, S) {
    const lines = S.m.lines, Y = 300;
    let cur = 0;
    for (let i = 0; i < lines.length; i++) if (t >= lines[i].start - 0.5) cur = i;
    const l = lines[cur], ids = l.show, xs = rowX(ids.length);
    const appear = l.start - 0.5, next = lines[cur + 1] ? lines[cur + 1].start - 0.5 : S.dur + 1;
    const out = 1 - p(t, next - 0.25, next);
    ids.forEach((id, i) => {
      const it = IT(id), e = itemEl(id, i), im = idleMotion(it.idle, t, i);
      const k = easeOutBack(p(t, appear + i * 0.08, appear + 0.4 + i * 0.08));
      const u = p(t, l.start, l.start + l.d);
      const step = l.d / ids.length, hop = pulse(t, [l.start + i * step], Math.max(0.35, step));
      e.style.clipPath = "none"; e.style.filter = "none";
      putItem(e, { x: xs[i] + im.dx, y: Y + im.dy - 40 * hop - (u > 0 && u < 1 ? 0 : 0), s: (ids.length > 2 ? 1.0 : 1.15) * (l.scale ?? 1) * k * (1 + 0.15 * hop),
        r: im.r, o: clamp(k * 3) * out }, Y, i);
    });
    if (l.word === "") return;   // no label for this line (e.g. a group with no single word to show)
    const it0 = ITEMS[ids[0]], w = wordEl(l.word || it0.word, l.color || it0.color);
    const wk = easeOutBack(p(t, l.start, l.start + 0.35)) * out;
    put(w, { x: 640, y: 540, s: 0.62 * clamp(wk) * fitScale(w, 600), o: clamp(wk) });
  }

  function rRitual(t, S) {
    setBg(bgOf(S.seg));
    put(hero, { x: 520, y: 380 + Math.sin(t * 2.4) * 6, s: 1.05 * easeOutBack(p(t, 0.1, 0.6)), r: Math.sin(t * 2) * 3, o: p(t, 0.1, 0.2) });
    const up = easeOutBack(p(t, 0.4, 1.0));
    put(brush, { x: 800, y: lerp(760, 300, up), s: 1.3, r: -8 + Math.sin(t * 7) * 5 * up, o: p(t, 0.4, 0.5) });
    burst(t, 1.0, 830, 210);
    const glow = pulse(t, [1.0, 1.9], 0.8);
    if (glow > 0) put(flash, { x: 830, y: 210, s: 0.5 + 0.4 * glow, o: 0.7 * glow });
  }
  const RENDER = { intro: rIntro, outro: rOutro, teach: rTeach, quiz: rQuiz, chant: rChant, ritual: rRitual };
  window.renderAt = function (id, t) {
    for (const e of ALL) e.style.opacity = 0;
    NOW = t;
    const S = SEGMENTS[id]; RENDER[S.type](t, S);
  };

  // realtime preview when the page is opened directly (?seg=<id> loops one segment)
  if (!new URLSearchParams(location.search).has("capture")) {
    const only = new URLSearchParams(location.search).get("seg");
    const order = only ? [only] : Object.keys(SEGMENTS);
    let i = 0, t0 = performance.now();
    (function tick(now) {
      let t = (now - t0) / 1000;
      if (t >= SEGMENTS[order[i]].dur) { i = (i + 1) % order.length; t0 = now; t = 0; }
      window.renderAt(order[i], t); requestAnimationFrame(tick);
    })(t0);
  }
})();
