/* Kasauti · shared atmosphere & motion helpers (no dependencies)
   - gold-dust particle canvas
   - hero spotlight that follows the cursor
   - scroll reveals + count-ups
   - nav scroll state
   All of it steps aside for prefers-reduced-motion. */
"use strict";

const KX = (() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function dust(canvas) {
    if (!canvas || reduced) return;
    const ctx = canvas.getContext("2d");
    let w, h, parts = [], raf = 0, running = true;
    const count = () => (window.innerWidth < 720 ? 34 : 80);

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.width = Math.floor(window.innerWidth * dpr);
      h = canvas.height = Math.floor(window.innerHeight * dpr);
      canvas.style.width = window.innerWidth + "px";
      canvas.style.height = window.innerHeight + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      parts = Array.from({ length: count() }, spawn);
    }
    function spawn() {
      return {
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        r: .5 + Math.random() * 1.8,
        vy: -(.06 + Math.random() * .22),
        vx: (Math.random() - .5) * .12,
        a: Math.random() * Math.PI * 2,
        tw: .4 + Math.random() * .6,
        sp: .004 + Math.random() * .01,
      };
    }
    function tick() {
      if (!running) return;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      for (const p of parts) {
        p.a += p.sp; p.y += p.vy; p.x += p.vx + Math.sin(p.a) * .08;
        if (p.y < -6) { p.y = window.innerHeight + 6; p.x = Math.random() * window.innerWidth; }
        if (p.x < -6) p.x = window.innerWidth + 6; else if (p.x > window.innerWidth + 6) p.x = -6;
        const alpha = .25 + .55 * (0.5 + 0.5 * Math.sin(p.a * 2)) * p.tw;
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
        g.addColorStop(0, `rgba(255,236,170,${alpha})`);
        g.addColorStop(.35, `rgba(212,166,63,${alpha * .55})`);
        g.addColorStop(1, "rgba(212,166,63,0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(tick);
    }
    resize();
    window.addEventListener("resize", resize, { passive: true });
    document.addEventListener("visibilitychange", () => {
      running = !document.hidden;
      if (running) tick(); else cancelAnimationFrame(raf);
    });
    tick();
  }

  function spotlight(el) {
    if (!el || reduced) return;
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100).toFixed(2) + "%");
      el.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100).toFixed(2) + "%");
    }, { passive: true });
  }

  function reveal() {
    const els = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window) || reduced) { els.forEach(e => e.classList.add("in")); return; }
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      }
    }, { threshold: .14, rootMargin: "0px 0px -6% 0px" });
    els.forEach(e => io.observe(e));
  }

  function countUp() {
    const els = document.querySelectorAll("[data-count]");
    if (!els.length) return;
    const run = (el) => {
      const target = parseFloat(el.dataset.count), suffix = el.dataset.suffix || "", prefix = el.dataset.prefix || "";
      const dec = (String(el.dataset.count).split(".")[1] || "").length;
      if (reduced) { el.textContent = prefix + target.toFixed(dec) + suffix; return; }
      const t0 = performance.now(), dur = 1400;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
        el.textContent = prefix + (target * e).toFixed(dec) + suffix;
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    if (!("IntersectionObserver" in window)) { els.forEach(run); return; }
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) if (en.isIntersecting) { run(en.target); io.unobserve(en.target); }
    }, { threshold: .5 });
    els.forEach(e => io.observe(e));
  }

  function nav() {
    const n = document.querySelector(".nav");
    if (!n) return;
    const upd = () => n.classList.toggle("scrolled", window.scrollY > 24);
    upd(); window.addEventListener("scroll", upd, { passive: true });
  }

  document.addEventListener("DOMContentLoaded", () => {
    dust(document.getElementById("dust"));
    spotlight(document.querySelector("[data-spotlight]"));
    reveal(); countUp(); nav();
  });

  return { reduced, dust, spotlight, reveal, countUp };
})();
