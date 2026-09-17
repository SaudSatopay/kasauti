/* Kasauti landing — hero stamping loop, ticker, typed reply, demo deep-links. */
"use strict";

(function () {
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Bundled copy (US Navy photo, public domain) for the page's own visuals…
  const TSUNAMI = "assets/tsunami-2004.jpg";
  // …but the live Lens demo must hand Google a public URL to fetch.
  const TSUNAMI_FULL = "https://upload.wikimedia.org/wikipedia/commons/8/80/US_Navy_050102-N-9593M-040_A_village_near_the_coast_of_Sumatra_lays_in_ruin_after_the_Tsunami_that_struck_South_East_Asia.jpg";

  const DEMOS = {
    unesco: {
      text: "Good news!! 🇮🇳🇮🇳 UNESCO has declared our JANA GANA MANA the BEST NATIONAL ANTHEM in the world!! 🎉🎉 Be proud to be an Indian 🙏🙏 Forward this to every Indian, don't let this news stop with you!!",
    },
    cyclone: {
      text: "⚠️ CYCLONE ALERT ⚠️ Massive destruction on the Tamil Nadu coast happening RIGHT NOW!! Army has been deployed. Media is hiding the real situation. Share this photo with everyone before it gets deleted!!",
      image: TSUNAMI_FULL,
    },
  };

  /* ── Hero scenes ── */
  const SCENES = [
    {
      text: "UNESCO has declared our JANA GANA MANA the BEST NATIONAL ANTHEM in the world!! 🇮🇳🎉 Forward to every Indian!!",
      chips: ["Begs to be forwarded", "Vague authority", "ALL CAPS"],
      verdict: "FALSE", hi: "फर्ज़ी", cls: "false",
      reply: "🙏 Maine check kiya — UNESCO aisa koi award deta hi nahi. 2008 se chal rahi purani afwaah hai.",
    },
    {
      text: "⚠️ CYCLONE ALERT ⚠️ Massive destruction on the coast RIGHT NOW!! Media is hiding this. Share before it gets deleted!!",
      image: TSUNAMI,
      chips: ["'Media is hiding it'", "Will be deleted", "Photo · 2004"],
      verdict: "OUTDATED", hi: "पुरानी खबर", cls: "outdated",
      reply: "🙏 Yeh photo 2004 ki tsunami ki hai, aaj ki nahi. Cyclone updates IMD se lein.",
    },
    {
      text: "Modi Sarkar is giving FREE ₹719 recharge for 3 months!! 💯 Click the link and forward to 10 groups to activate!!",
      chips: ["Too good to be true", "Forward to activate", "Phishing link"],
      verdict: "FALSE", hi: "फर्ज़ी", cls: "false",
      reply: "🙏 Yeh phishing link hai — PIB Fact Check ne isse fake bataya hai. Click mat karna.",
    },
  ];

  function sceneHTML(s) {
    const chips = s.chips.map((c, i) => `<span style="--i:${i}">${esc(c)}</span>`).join("");
    return `<div class="scene">
      <div class="msg"><span class="fwd">↪ Forwarded many times</span>${s.image ? `<img src="${esc(s.image)}" alt="">` : ""}${esc(s.text)}
        <div class="fp-pops">${chips}</div><span class="time">9:41 PM</span></div>
      <div class="ink-mini ${s.cls}"></div>
      <div class="stamp-mini ${s.cls}">${esc(s.verdict)}<span class="hi">${esc(s.hi)}</span></div>
      <div class="reply">${esc(s.reply)}<span class="time">9:43 PM ✓✓</span></div>
    </div>`;
  }

  function initScenes() {
    const host = document.getElementById("scenes");
    if (!host) return;
    host.innerHTML = SCENES.map(sceneHTML).join("");
    const scenes = host.querySelectorAll(".scene");
    let i = 0;
    const show = (k) => { scenes.forEach(s => s.classList.remove("active")); scenes[k].classList.add("active"); };
    show(0);
    if (REDUCED) return;
    setInterval(() => { i = (i + 1) % scenes.length; show(i); }, 6800);
  }

  /* ── Ticker: duplicate for a seamless loop ── */
  function initTicker() {
    const track = document.getElementById("ticker-track");
    if (!track) return;
    track.innerHTML += track.innerHTML;
  }

  /* ── Typed reply demo ── */
  function initTyped() {
    const el = document.getElementById("typed");
    if (!el) return;
    const text = "🙏 Uncle ji, maine yeh check kiya — UNESCO aisa koi award deta hi nahi, yeh 2008 se chal rahi afwaah hai. Alt News aur Vishvas News dono ne fact-check kiya hai: altnews.in/unesco-anthem. Aage forward na karein toh behtar. 🙂";
    if (REDUCED) { el.textContent = text; return; }
    let started = false;
    const start = () => {
      if (started) return; started = true;
      let k = 0;
      const tick = () => {
        el.textContent = text.slice(0, k++);
        if (k <= text.length) setTimeout(tick, 22 + Math.random() * 30);
      };
      setTimeout(tick, 500);
    };
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((en) => { if (en.some(e => e.isIntersecting)) { start(); io.disconnect(); } }, { threshold: .4 });
      io.observe(el.closest(".reply-demo") || el);
    } else start();
  }

  /* ── Demo deep-links into the checker ── */
  function initDemoLinks() {
    document.querySelectorAll("[data-demo]").forEach(a => {
      const d = DEMOS[a.dataset.demo];
      if (!d) return;
      const q = new URLSearchParams({ text: d.text, auto: "1" });
      if (d.image) q.set("image", d.image);
      a.href = "/app?" + q.toString();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initScenes(); initTicker(); initTyped(); initDemoLinks();
  });
})();
