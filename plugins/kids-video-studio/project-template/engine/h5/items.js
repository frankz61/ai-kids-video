// Season-wide vector item library for the H5 engine. Every item is drawn in a 200x200 viewBox.
// ITEMS[id] = { svg, word, color, idle, act, focus:[x,y] (point the hand at, in viewBox units) }
// idle: bob | float | swim | none      act: hop | run | swim | clap | wiggle | none
"use strict";
(function () {
  const INK = "#2b2b2b";
  const face = (x, y, s = 1, smile = true) =>   // small cute face used on fruit and toys
    `<g transform="translate(${x} ${y}) scale(${s})"><circle cx="-14" cy="0" r="6" fill="${INK}"/><circle cx="14" cy="0" r="6" fill="${INK}"/>` +
    (smile ? `<path d="M-12 14 Q0 26 12 14" stroke="${INK}" stroke-width="4.5" fill="none" stroke-linecap="round"/>` : "") + `</g>`;

  // ---------- fox heads: Fenlo, his family, and the feelings faces ----------
  function fox(o = {}) {
    const fur = o.fur || "#f28a2e", inner = o.inner || "#7a3b12";
    let eyes, mouth, extra = "", top = "";
    switch (o.eyes || "open") {
      case "happy": eyes = `<path d="M60 102 Q72 88 84 102 M116 102 Q128 88 140 102" stroke="${INK}" stroke-width="7" fill="none" stroke-linecap="round"/>`; break;
      case "closed": eyes = `<path d="M60 100 Q72 108 84 100 M116 100 Q128 108 140 100" stroke="${INK}" stroke-width="6" fill="none" stroke-linecap="round"/>`; break;
      case "sad": eyes = `<circle cx="72" cy="102" r="9" fill="${INK}"/><circle cx="128" cy="102" r="9" fill="${INK}"/>` +
        `<path d="M58 92 L84 82 M142 92 L116 82" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>`; break;
      default: eyes = `<circle cx="72" cy="100" r="10" fill="${INK}"/><circle cx="128" cy="100" r="10" fill="${INK}"/>` +
        `<circle cx="75" cy="96" r="3.5" fill="#fff"/><circle cx="131" cy="96" r="3.5" fill="#fff"/>`;
    }
    switch (o.mouth || "smile") {
      case "big": mouth = `<path d="M82 146 Q100 172 118 146 Z" fill="#c2413b" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>`; break;
      case "frown": mouth = `<path d="M86 158 Q100 146 114 158" stroke="${INK}" stroke-width="5" fill="none" stroke-linecap="round"/>`; break;
      case "tongue": mouth = `<path d="M84 146 Q100 160 116 146" stroke="${INK}" stroke-width="5" fill="none" stroke-linecap="round"/>` +
        `<path d="M104 152 Q118 150 120 162 Q118 172 108 166 Z" fill="#ef6f8a"/>`; break;
      case "o": mouth = `<ellipse cx="100" cy="154" rx="7" ry="8" fill="${INK}"/>`; break;
      default: mouth = `<path d="M86 148 Q100 162 114 148" stroke="${INK}" stroke-width="5" fill="none" stroke-linecap="round"/>`;
    }
    if (o.glasses) extra += `<g fill="none" stroke="#5b4636" stroke-width="5"><circle cx="72" cy="100" r="17"/><circle cx="128" cy="100" r="17"/><path d="M89 100 H111"/></g>`;
    if (o.mustache) extra += `<path d="M100 142 Q86 136 74 146 Q86 150 100 146 Q114 150 126 146 Q114 136 100 142Z" fill="#fff" stroke="#d8d8d8" stroke-width="2"/>`;
    if (o.bow) extra += `<g transform="translate(150 40) rotate(20)"><path d="M0 0 L-22 -14 L-22 14Z M0 0 L22 -14 L22 14Z" fill="#ef6f8a"/><circle r="7" fill="#d9466b"/></g>`;
    if (o.tie) extra += `<g transform="translate(100 192)"><path d="M0 0 L-22 -12 L-22 12Z M0 0 L22 -12 L22 12Z" fill="#3f8fe8"/><circle r="6" fill="#2567bd"/></g>`;
    if (o.bun) top += `<circle cx="100" cy="34" r="20" fill="#e6e6e6" stroke="#cfcfcf" stroke-width="3"/>`;
    if (o.scarf) extra += `<path d="M42 168 Q100 196 158 168 L156 190 Q100 214 44 190Z" fill="#f4ead4" stroke="#e2d4b4" stroke-width="3"/>`;
    if (o.zzz) extra += `<text x="150" y="58" font-family="Nunito,sans-serif" font-weight="900" font-size="34" fill="#6c8bd6">Z</text>` +
      `<text x="172" y="34" font-family="Nunito,sans-serif" font-weight="900" font-size="24" fill="#6c8bd6">z</text>`;
    if (o.rumble) extra += `<path d="M24 150 q6 -6 12 0 t12 0 M152 150 q6 -6 12 0 t12 0" stroke="#e08a3a" stroke-width="4" fill="none" stroke-linecap="round"/>`;
    return top +
      `<path d="M38 82 L52 14 L92 54Z M162 82 L148 14 L108 54Z" fill="${fur}"/>` +
      `<path d="M50 70 L58 30 L80 54Z M150 70 L142 30 L120 54Z" fill="${inner}"/>` +
      `<ellipse cx="100" cy="112" rx="74" ry="66" fill="${fur}"/>` +
      `<path d="M100 120 C70 112 40 124 34 140 C46 170 76 182 100 182 C124 182 154 170 166 140 C160 124 130 112 100 120Z" fill="#fff"/>` +
      eyes + (o.nonose ? "" : `<ellipse cx="100" cy="132" rx="11" ry="8" fill="${INK}"/>`) + mouth + extra;
  }
  const frame = inner => `<rect x="6" y="6" width="188" height="188" rx="34" fill="#fff7e6" stroke="#f0c36a" stroke-width="8"/>` +
    `<g transform="translate(18 16) scale(0.82)">${inner}</g>`;
  // highlight ring for the "touch your ..." items (drawn on top of Fenlo's face)
  const glow = (cx, cy, rx, ry) => `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="none" stroke="#ffd23f" stroke-width="7" stroke-dasharray="14 9"/>`;

  // ---------- fruit ----------
  const apple = `<path d="M100 62 C100 45 106 32 118 24" stroke="#7a4a21" stroke-width="9" fill="none" stroke-linecap="round"/>` +
    `<path d="M106 40 Q132 26 146 44 Q124 54 106 40Z" fill="#4fbf5a"/>` +
    `<path d="M100 60 C70 35 20 55 25 110 C28 160 70 188 100 172 C130 188 172 160 175 110 C180 55 130 35 100 60Z" fill="#e8413c"/>` +
    `<ellipse cx="58" cy="92" rx="11" ry="20" fill="#fff" opacity=".35" transform="rotate(18 58 92)"/>` + face(100, 114);
  const banana = `<path d="M150 34 C176 70 168 140 112 168 C76 186 40 176 22 158 C64 162 110 146 128 104 C138 80 140 56 136 38Z" fill="#ffd23f" stroke="#e6b100" stroke-width="5" stroke-linejoin="round"/>` +
    `<path d="M136 38 L140 22 L152 26 L150 36Z" fill="#7a5a1e"/><path d="M22 158 L14 162 L20 168Z" fill="#7a5a1e"/>` + face(104, 136, 0.85);
  const pear = `<path d="M100 40 C100 30 104 22 112 16" stroke="#7a4a21" stroke-width="8" fill="none" stroke-linecap="round"/>` +
    `<path d="M100 42 C78 42 72 66 76 84 C56 100 40 124 44 148 C50 180 80 188 100 188 C120 188 150 180 156 148 C160 124 144 100 124 84 C128 66 122 42 100 42Z" fill="#b5d936" stroke="#93b51f" stroke-width="4"/>` +
    `<ellipse cx="70" cy="128" rx="9" ry="18" fill="#fff" opacity=".35"/>` + face(100, 138);
  const strawberry = `<path d="M100 54 C50 50 30 90 44 124 C58 160 86 186 100 190 C114 186 142 160 156 124 C170 90 150 50 100 54Z" fill="#e8413c"/>` +
    [[70, 86], [100, 78], [130, 86], [60, 116], [140, 116], [80, 150], [120, 150], [100, 172]].map(([x, y]) =>
      `<ellipse cx="${x}" cy="${y}" rx="3.5" ry="5" fill="#ffe08a"/>`).join("") +
    `<path d="M100 58 L72 38 L90 52 L82 30 L100 50 L118 30 L110 52 L128 38Z" fill="#3fae4b"/>` + face(100, 118);

  // ---------- animals ----------
  const cat = `<path d="M50 74 L56 24 L92 58Z M150 74 L144 24 L108 58Z" fill="#8f97a3"/><path d="M60 64 L62 38 L82 58Z M140 64 L138 38 L118 58Z" fill="#f2a6b6"/>` +
    `<ellipse cx="100" cy="112" rx="70" ry="62" fill="#a9b0bb"/>` +
    `<circle cx="74" cy="102" r="10" fill="${INK}"/><circle cx="126" cy="102" r="10" fill="${INK}"/><circle cx="77" cy="98" r="3.5" fill="#fff"/><circle cx="129" cy="98" r="3.5" fill="#fff"/>` +
    `<path d="M94 126 L106 126 L100 134Z" fill="#ef6f8a"/><path d="M100 134 Q92 146 84 140 M100 134 Q108 146 116 140" stroke="${INK}" stroke-width="4" fill="none" stroke-linecap="round"/>` +
    `<path d="M40 126 H70 M40 140 H70 M130 126 H160 M130 140 H160" stroke="#5f6670" stroke-width="3" stroke-linecap="round"/>`;
  const dog = `<path d="M40 70 C20 90 26 140 52 146 C60 120 60 94 62 76Z M160 70 C180 90 174 140 148 146 C140 120 140 94 138 76Z" fill="#8a5a33"/>` +
    `<ellipse cx="100" cy="110" rx="64" ry="62" fill="#c98b55"/><ellipse cx="100" cy="146" rx="36" ry="28" fill="#f3dcc0"/>` +
    `<circle cx="76" cy="100" r="10" fill="${INK}"/><circle cx="124" cy="100" r="10" fill="${INK}"/><circle cx="79" cy="96" r="3.5" fill="#fff"/><circle cx="127" cy="96" r="3.5" fill="#fff"/>` +
    `<ellipse cx="100" cy="132" rx="13" ry="9" fill="${INK}"/><path d="M100 140 V150 M88 152 Q100 160 112 152" stroke="${INK}" stroke-width="4" fill="none" stroke-linecap="round"/>` +
    `<path d="M106 156 Q110 172 100 172 Q92 170 96 158Z" fill="#ef6f8a"/>`;
  const rabbit = `<ellipse cx="74" cy="44" rx="16" ry="44" fill="#f4f4f4" stroke="#e2e2e2" stroke-width="3"/><ellipse cx="126" cy="44" rx="16" ry="44" fill="#f4f4f4" stroke="#e2e2e2" stroke-width="3"/>` +
    `<ellipse cx="74" cy="46" rx="7" ry="30" fill="#f6b7c6"/><ellipse cx="126" cy="46" rx="7" ry="30" fill="#f6b7c6"/>` +
    `<ellipse cx="100" cy="130" rx="62" ry="56" fill="#fafafa" stroke="#e2e2e2" stroke-width="3"/>` +
    `<circle cx="78" cy="122" r="9" fill="${INK}"/><circle cx="122" cy="122" r="9" fill="${INK}"/><circle cx="81" cy="118" r="3" fill="#fff"/><circle cx="125" cy="118" r="3" fill="#fff"/>` +
    `<path d="M94 140 L106 140 L100 147Z" fill="#ef6f8a"/><path d="M100 147 Q92 158 86 154 M100 147 Q108 158 114 154" stroke="${INK}" stroke-width="4" fill="none" stroke-linecap="round"/>` +
    `<ellipse cx="66" cy="148" rx="10" ry="6" fill="#f6b7c6" opacity=".7"/><ellipse cx="134" cy="148" rx="10" ry="6" fill="#f6b7c6" opacity=".7"/>`;
  const fish = `<path d="M150 100 L192 66 L186 100 L192 134Z" fill="#2567bd"/>` +
    `<ellipse cx="96" cy="100" rx="66" ry="46" fill="#3f8fe8"/><path d="M80 56 Q100 34 124 58Z M84 144 Q100 162 120 142Z" fill="#2567bd"/>` +
    `<path d="M98 62 Q116 100 98 138" stroke="#9cc9f7" stroke-width="7" fill="none" stroke-linecap="round"/>` +
    `<circle cx="62" cy="92" r="11" fill="#fff"/><circle cx="60" cy="92" r="6" fill="${INK}"/><path d="M40 112 Q48 118 56 112" stroke="${INK}" stroke-width="4" fill="none" stroke-linecap="round"/>`;

  // ---------- counting, toys, food ----------
  const balloon = c => `<path d="M100 150 Q92 168 104 182 Q114 196 100 200" stroke="#8a8f98" stroke-width="3" fill="none"/>` +
    `<path d="M100 18 C56 18 40 56 44 86 C50 124 80 146 100 150 C120 146 150 124 156 86 C160 56 144 18 100 18Z" fill="${c}"/>` +
    `<path d="M92 150 L108 150 L100 160Z" fill="${c}"/><ellipse cx="76" cy="62" rx="10" ry="20" fill="#fff" opacity=".4" transform="rotate(20 76 62)"/>`;
  const ball = `<circle cx="100" cy="104" r="80" fill="#e8413c"/><path d="M100 24 C70 60 70 148 100 184" stroke="#ffd23f" stroke-width="22" fill="none"/>` +
    `<path d="M24 92 C70 80 130 80 178 96" stroke="#fff" stroke-width="16" fill="none"/><circle cx="100" cy="104" r="80" fill="none" stroke="#c2312c" stroke-width="5"/>` +
    `<ellipse cx="66" cy="62" rx="12" ry="22" fill="#fff" opacity=".35" transform="rotate(30 66 62)"/>`;
  const car = `<path d="M30 120 L52 76 Q58 66 70 66 L132 66 Q144 66 150 76 L170 120Z" fill="#3f8fe8"/><path d="M62 82 L74 82 L74 112 L50 112Z M86 82 L128 82 Q134 82 138 88 L150 112 L86 112Z" fill="#cfe8ff"/>` +
    `<rect x="14" y="110" width="172" height="44" rx="18" fill="#e8413c"/><circle cx="58" cy="156" r="22" fill="${INK}"/><circle cx="58" cy="156" r="9" fill="#c9ced6"/>` +
    `<circle cx="144" cy="156" r="22" fill="${INK}"/><circle cx="144" cy="156" r="9" fill="#c9ced6"/><rect x="170" y="120" width="14" height="10" rx="3" fill="#ffd23f"/>`;
  const milk = `<path d="M60 40 L140 40 L130 184 Q100 192 70 184Z" fill="#eef6ff" stroke="#b9cbe0" stroke-width="5" stroke-linejoin="round"/>` +
    `<path d="M64 76 L136 76 L130 180 Q100 188 70 180Z" fill="#fff"/><path d="M64 76 Q82 66 100 76 T136 76" stroke="#dbe7f4" stroke-width="4" fill="none"/>` + face(100, 128, 0.85);
  const bread = `<path d="M40 92 C24 50 70 30 100 40 C130 30 176 50 160 92 L156 176 Q100 186 44 176Z" fill="#c98b55"/>` +
    `<path d="M54 94 C44 64 76 52 100 58 C124 52 156 64 146 94 L142 166 Q100 174 58 166Z" fill="#f6ddb0"/>` + face(100, 118, 0.85);
  const eggs = `<ellipse cx="70" cy="118" rx="44" ry="58" fill="#fff8ec" stroke="#e8d8bb" stroke-width="4"/>` +
    `<ellipse cx="132" cy="122" rx="44" ry="56" fill="#fff8ec" stroke="#e8d8bb" stroke-width="4"/>` + face(70, 120, 0.7) + face(132, 124, 0.7);
  const juice = `<path d="M56 40 L144 40 L132 184 Q100 192 68 184Z" fill="#eaf6ff" stroke="#b9cbe0" stroke-width="5" stroke-linejoin="round"/>` +
    `<path d="M62 80 L138 80 L131 180 Q100 188 69 180Z" fill="#ffb02e"/><path d="M120 12 L106 120" stroke="#e8413c" stroke-width="9" stroke-linecap="round"/>` +
    `<circle cx="150" cy="56" r="22" fill="#ffd23f" stroke="#f0a400" stroke-width="4"/><path d="M150 36 V76 M130 56 H170" stroke="#f0a400" stroke-width="3"/>` + face(100, 132, 0.85);
  const hands = `<g id="lh"><path d="M28 172 L44 112 C46 98 40 70 52 66 C62 64 64 80 66 92 L72 50 C74 38 90 40 88 54 L86 84 L92 44 C94 32 110 34 108 48 L104 90 L112 60 C114 50 128 52 126 64 L114 120 C110 150 96 172 84 182Z" fill="#f28a2e" stroke="#b5561a" stroke-width="4" stroke-linejoin="round"/></g>` +
    `<g transform="translate(200 0) scale(-1 1)"><path d="M28 172 L44 112 C46 98 40 70 52 66 C62 64 64 80 66 92 L72 50 C74 38 90 40 88 54 L86 84 L92 44 C94 32 110 34 108 48 L104 90 L112 60 C114 50 128 52 126 64 L114 120 C110 150 96 172 84 182Z" fill="#f28a2e" stroke="#b5561a" stroke-width="4" stroke-linejoin="round"/></g>`;

  // ---------- covers (things items hide behind) ----------
  const basket = `<path d="M10 70 L190 70 L172 170 Q100 186 28 170Z" fill="#c98b55" stroke="#8a5a33" stroke-width="6" stroke-linejoin="round"/>` +
    `<path d="M24 100 H178 M30 130 H172 M60 72 L66 176 M100 72 V182 M140 72 L134 176" stroke="#8a5a33" stroke-width="5"/>` +
    `<rect x="4" y="58" width="192" height="22" rx="11" fill="#a86f40" stroke="#8a5a33" stroke-width="5"/>`;
  const bush = `<g fill="#4fbf5a" stroke="#3a9c46" stroke-width="5"><circle cx="46" cy="120" r="44"/><circle cx="100" cy="96" r="54"/><circle cx="154" cy="120" r="44"/><rect x="10" y="120" width="180" height="70" rx="30"/></g>` +
    `<circle cx="70" cy="108" r="6" fill="#ef6f8a"/><circle cx="128" cy="86" r="6" fill="#ffd23f"/><circle cx="150" cy="132" r="6" fill="#ef6f8a"/>`;

  // finish-line banner (episode 7: the paintbrush's new trick)
  const finish = `<path d="M18 30 V196 M182 30 V196" stroke="#8a5a33" stroke-width="10" stroke-linecap="round"/>` +
    `<path d="M18 40 Q100 70 182 40 V96 Q100 126 18 96Z" fill="#fff" stroke="#2b2b2b" stroke-width="4"/>` +
    Array.from({ length: 8 }, (_, i) => { const x = 18 + i * 20.5;
      return `<rect x="${x}" y="${52 + (i % 2) * 22 + Math.sin(i / 7 * Math.PI) * 20}" width="20.5" height="22" fill="#2b2b2b"/>`; }).join("");
  // blocks (episode 9: Fenlo's tower falls over)
  const blocks = `<rect x="20" y="140" width="56" height="50" rx="6" fill="#e8413c"/><rect x="84" y="150" width="50" height="40" rx="6" fill="#3f8fe8"/>` +
    `<rect x="132" y="120" width="48" height="48" rx="6" fill="#ffd23f" transform="rotate(24 156 144)"/><rect x="60" y="96" width="44" height="40" rx="6" fill="#4fbf5a" transform="rotate(-18 82 116)"/>`;

  // the same blocks stacked up again (episode 9: rebuilt with help)
  const tower = `<rect x="60" y="148" width="80" height="44" rx="6" fill="#e8413c"/><rect x="70" y="104" width="60" height="44" rx="6" fill="#3f8fe8"/>` +
    `<rect x="76" y="62" width="48" height="42" rx="6" fill="#ffd23f"/><rect x="82" y="22" width="36" height="40" rx="6" fill="#4fbf5a"/>`;

  // ice cream (episode 9: the reason Fenlo is happy, then sad, then happy again)
  const icecream = `<path d="M62 96 L100 192 L138 96Z" fill="#e0a85a" stroke="#b9793a" stroke-width="5" stroke-linejoin="round"/>` +
    `<circle cx="100" cy="66" r="48" fill="#f7a8c0"/><circle cx="84" cy="50" r="10" fill="#fff" opacity=".6"/>`;
  const icecreamDrop = `<ellipse cx="100" cy="168" rx="84" ry="22" fill="#f7a8c0"/><circle cx="92" cy="150" r="34" fill="#f7a8c0"/>` +
    `<path d="M84 128 L150 60 L172 96Z" fill="#e0a85a" stroke="#b9793a" stroke-width="5" stroke-linejoin="round"/>`;

  const ITEMS = {
    icecream: { svg: icecream, word: "", color: "#e2809a", act: "hop" },
    icecream_drop: { svg: icecreamDrop, word: "", color: "#e2809a", act: "wiggle", idle: "none" },
    finish: { svg: finish, word: "", color: "#2b2b2b" },
    blocks: { svg: blocks, word: "", color: "#2b2b2b", act: "wiggle" },
    // episode 1 (kept identical to the EP01 page)
    apple: { svg: apple, word: "apple", color: "#e8413c" },
    duck: { svg: `<path d="M36 122 L10 100 L44 104Z" fill="#f5bd1f"/><ellipse cx="95" cy="135" rx="66" ry="46" fill="#ffd23f"/><circle cx="140" cy="76" r="38" fill="#ffd23f"/><path d="M172 68 L199 80 L172 92Z" fill="#f58a1f"/><circle cx="150" cy="66" r="6.5" fill="${INK}"/><ellipse cx="84" cy="136" rx="32" ry="22" fill="#f5bd1f"/>`, word: "duck", color: "#f0b400" },
    bird: { svg: `<path d="M44 108 L8 92 L14 128Z" fill="#2567bd"/><path d="M88 164 V184 M112 164 V184" stroke="#f58a1f" stroke-width="6" stroke-linecap="round"/><ellipse cx="100" cy="114" rx="62" ry="54" fill="#3f8fe8"/><ellipse cx="110" cy="130" rx="36" ry="30" fill="#9cc9f7"/><path d="M62 96 Q28 128 70 152 Q98 130 62 96Z" fill="#2567bd"/><circle cx="126" cy="90" r="7" fill="${INK}"/><path d="M158 98 L188 108 L158 120Z" fill="#f58a1f"/>`, word: "bird", color: "#3f8fe8" },
    frog: { svg: `<ellipse cx="42" cy="176" rx="26" ry="10" fill="#3a9c46"/><ellipse cx="158" cy="176" rx="26" ry="10" fill="#3a9c46"/><ellipse cx="100" cy="130" rx="72" ry="52" fill="#4fbf5a"/><ellipse cx="100" cy="150" rx="40" ry="24" fill="#a9e6ae"/><circle cx="66" cy="76" r="25" fill="#4fbf5a"/><circle cx="134" cy="76" r="25" fill="#4fbf5a"/><circle cx="66" cy="74" r="14" fill="#fff"/><circle cx="134" cy="74" r="14" fill="#fff"/><circle cx="68" cy="76" r="7" fill="${INK}"/><circle cx="132" cy="76" r="7" fill="${INK}"/><path d="M66 126 Q100 152 134 126" stroke="${INK}" stroke-width="5" fill="none" stroke-linecap="round"/>`, word: "frog", color: "#3fae4b", act: "hop" },
    // counting
    balloon_red: { svg: balloon("#e8413c"), word: "balloon", color: "#e8413c", idle: "float" },
    balloon_blue: { svg: balloon("#3f8fe8"), word: "balloon", color: "#3f8fe8", idle: "float" },
    balloon_yellow: { svg: balloon("#ffd23f"), word: "balloon", color: "#f0b400", idle: "float" },
    balloon_green: { svg: balloon("#4fbf5a"), word: "balloon", color: "#3fae4b", idle: "float" },
    // fruit
    banana: { svg: banana, word: "banana", color: "#f0b400" },
    pear: { svg: pear, word: "pear", color: "#7fae1c" },
    strawberry: { svg: strawberry, word: "strawberry", color: "#e8413c" },
    // animals
    cat: { svg: cat, word: "cat", color: "#7a828e", act: "wiggle" },
    dog: { svg: dog, word: "dog", color: "#a8693a", act: "run" },
    rabbit: { svg: rabbit, word: "rabbit", color: "#e2809a", act: "hop" },
    fish: { svg: fish, word: "fish", color: "#3f8fe8", idle: "swim", act: "swim" },
    // Fenlo's face, with the part to touch highlighted
    fenlo: { svg: fox({ scarf: true }), word: "Fenlo", color: "#f28a2e" },
    fenlo_nonose: { svg: fox({ scarf: true, nonose: true }) + glow(100, 132, 22, 18), word: "nose", color: "#f0b400", focus: [100, 132] },
    head: { svg: fox({ scarf: true }) + glow(100, 66, 82, 46), word: "head", color: "#e8413c", focus: [100, 40] },
    eyes: { svg: fox({ scarf: true }) + glow(100, 100, 58, 24), word: "eyes", color: "#3f8fe8", focus: [128, 100] },
    nose: { svg: fox({ scarf: true }) + glow(100, 132, 22, 18), word: "nose", color: "#f0b400", focus: [100, 132] },
    mouth: { svg: fox({ scarf: true }) + glow(100, 152, 28, 16), word: "mouth", color: "#3fae4b", focus: [100, 152] },
    // actions (performed by friends from earlier episodes)
    hands: { svg: hands, word: "clap", color: "#e8413c", act: "clap" },
    fenlo_framed: { svg: frame(fox({ scarf: true })), word: "Fenlo", color: "#f28a2e" },
    tower: { svg: tower, word: "", color: "#2b2b2b", act: "hop" },
    // family portraits (Fenlo's own family)
    mom: { svg: frame(fox({ bow: true, fur: "#f39a45" })), word: "mom", color: "#e2809a" },
    dad: { svg: frame(fox({ tie: true, fur: "#e57a24" })), word: "dad", color: "#3f8fe8" },
    grandma: { svg: frame(fox({ bun: true, glasses: true, fur: "#f0b07a" })), word: "grandma", color: "#a86fd6" },
    grandpa: { svg: frame(fox({ glasses: true, mustache: true, fur: "#e9a06a" })), word: "grandpa", color: "#3fae4b" },
    // feelings
    happy: { svg: fox({ eyes: "happy", mouth: "big", scarf: true }), word: "happy", color: "#f0b400", act: "hop" },
    sad: { svg: fox({ eyes: "sad", mouth: "frown", scarf: true }), word: "sad", color: "#3f8fe8" },
    hungry: { svg: fox({ mouth: "tongue", scarf: true, rumble: true }), word: "hungry", color: "#e08a3a", act: "wiggle" },
    sleepy: { svg: fox({ eyes: "closed", mouth: "o", scarf: true, zzz: true }), word: "sleepy", color: "#6c8bd6" },
    // food
    milk: { svg: milk, word: "milk", color: "#6c8bd6" },
    bread: { svg: bread, word: "bread", color: "#a8693a" },
    eggs: { svg: eggs, word: "eggs", color: "#e0a400" },
    juice: { svg: juice, word: "juice", color: "#f08a00" },
    // toys
    ball: { svg: ball, word: "ball", color: "#e8413c", act: "hop" },
    car: { svg: car, word: "car", color: "#3f8fe8", act: "run" },
  };
  const COVERS = { basket, bush };
  window.ITEMS = ITEMS;
  window.COVERS = COVERS;
})();
