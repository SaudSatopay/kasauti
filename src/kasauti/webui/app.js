/* Kasauti checker — streams the pipeline's progress, then renders the
   assay certificate with a staged, cinematic reveal. Vanilla JS, no build. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const LABELS = {
  true: "TRUE", mostly_true: "MOSTLY TRUE", misleading: "MISLEADING",
  false: "FALSE", outdated: "OUTDATED", unverified: "UNVERIFIED", satire: "SATIRE",
};
const LABEL_HINDI = {
  true: "सही", mostly_true: "लगभग सही", misleading: "भ्रामक",
  false: "फर्ज़ी", outdated: "पुरानी खबर", unverified: "अपुष्ट", satire: "व्यंग्य",
};
const LEVEL_COLOR = { low: "#2f8a55", medium: "#d07f22", high: "#c23b2e" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function showBanner(html, isError) {
  const b = $("#banner");
  b.hidden = false; b.className = "banner" + (isError ? " error" : ""); b.innerHTML = html;
}

async function loadHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    if (!h.serpapi) {
      showBanner('No SerpApi key found. Add <code>SERPAPI_API_KEY</code> to your <code>.env</code> ' +
        '(free key: <a href="https://serpapi.com/manage-api-key" target="_blank" rel="noopener">serpapi.com</a>).', true);
    } else if (!h.llm) {
      showBanner('Running in <strong>rule-based mode</strong> (no LLM key found). Verdicts will be conservative. ' +
        'Add a <code>GEMINI_API_KEY</code> / <code>OPENAI_API_KEY</code> for full analysis.', false);
    }
  } catch { /* server not ready */ }
}

async function loadExamples() {
  try {
    const examples = await (await fetch("/api/examples")).json();
    const holder = $("#chips");
    for (const ex of examples.slice(0, 4)) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = "✦ " + ex.name;
      b.addEventListener("click", () => {
        $("#text").value = ex.text || ""; $("#image").value = ex.image_url || ""; $("#text").focus();
      });
      holder.appendChild(b);
    }
  } catch { /* fine without */ }
}

function addLog(stage, detail) {
  const li = document.createElement("li");
  li.innerHTML = `<strong>${esc(stage)}</strong> · ${esc(detail)}`;
  $("#log-lines").appendChild(li);
  li.scrollIntoView({ block: "nearest", behavior: REDUCED ? "auto" : "smooth" });
}

function evidenceRow(e, i) {
  const date = e.date ? e.date.slice(0, 10) : (e.date_raw || "");
  return `<li style="--i:${i}">
    <a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.title)}</a>
    <div class="ev-meta">
      <span class="ev-id">[${esc(e.id)}]</span>
      <span class="tier tier-${esc(e.credibility.tier)}">${esc(e.credibility.label.split("·")[0].trim())}</span>
      <span>${esc(e.source_name || e.domain)}</span>
      ${date ? `<span>${esc(date)}</span>` : ""}
      <span>via ${esc(e.channel)}</span>
    </div>
  </li>`;
}

function gaugeHTML(fp) {
  const C = (2 * Math.PI * 52).toFixed(2);
  const color = LEVEL_COLOR[fp.level] || "#d4a63f";
  return `<div class="gauge-box">
    <svg class="gauge" viewBox="0 0 120 120" aria-hidden="true">
      <defs><linearGradient id="gg" x1="0" x2="1"><stop offset="0" stop-color="#d4a63f"/><stop offset="1" stop-color="${color}"/></linearGradient></defs>
      <circle class="track" cx="60" cy="60" r="52"/>
      <circle class="arc" id="fp-arc" cx="60" cy="60" r="52" stroke="url(#gg)" stroke-dasharray="${C}" stroke-dashoffset="${C}"/>
    </svg>
    <div class="gauge-num" style="color:${color}">${fp.score}</div>
    <small>/ 100</small>
  </div>`;
}

function render(report) {
  const el = $("#result");
  const label = report.overall_label;
  const conf = Math.round(report.overall_confidence * 100);
  const claimsById = Object.fromEntries(report.claims.map(c => [c.id, c]));
  const fp = report.fingerprint || { score: 0, level: "low", signals: [] };
  let stage = 0;

  const fpSignals = fp.signals.map(s => `<li>${esc(s.label)}<small>${esc(s.detail)}</small></li>`).join("");

  const verdictBlocks = report.verdicts.map(v => {
    const c = claimsById[v.claim_id] || {};
    const cited = (v.citation_ids || []).join(", ");
    const notes = (v.guardrail_notes || []).length
      ? `<div class="notes">🛡 ${v.guardrail_notes.map(esc).join(" · ")}</div>` : "";
    return `<details class="claim" open>
      <summary>
        <span class="verdict-chip vc-${esc(v.label)}">${LABELS[v.label] || v.label}</span>
        <span>${esc(c.text_en || v.claim_id)}</span>
        <span class="conf">${Math.round(v.confidence * 100)}%</span>
      </summary>
      <div class="body">${esc(v.rationale)}${cited ? ` <em>(${esc(cited)})</em>` : ""}${notes}</div>
    </details>`;
  }).join("");

  let lensBlock = "";
  if (report.image) {
    const strip = (report.image.matches || []).filter(m => m.thumbnail).slice(0, 8).map(m =>
      `<a href="${esc(m.link || "#")}" target="_blank" rel="noopener">
         <img src="${esc(m.thumbnail)}" alt="" loading="lazy">
         <span class="d">${esc(m.domain || "")}${m.date ? " · " + esc(m.date.slice(0, 10)) : ""}</span>
       </a>`).join("");
    lensBlock = `<div class="stage" style="--i:${stage++}">
      <div class="section-title">Image check · Google Lens</div>
      <div class="lens-note">${esc(report.image.note || "")}</div>
      ${strip ? `<div class="lens-strip">${strip}</div>` : ""}
    </div>`;
  }

  // Top-ranked rows, plus anything a verdict actually cites and every Lens
  // match — a citation the reader can't see is worth nothing.
  const cited = new Set(report.verdicts.flatMap(v => v.citation_ids || []));
  const evidence = (report.evidence || [])
    .filter((e, i) => i < 12 || cited.has(e.id) || e.channel === "lens")
    .map(evidenceRow).join("");

  el.innerHTML = `
  <div class="certificate">
    <div class="cert-head">
      <div class="cert-title">ASSAY CERTIFICATE<small>कसौटी · EVIDENCE-FIRST VERIFICATION</small></div>
      <div class="stamp-wrap ${esc(label)}">
        <span class="ink"></span>
        <div class="stamp ${esc(label)}">${LABELS[label] || label}<span class="hi">${LABEL_HINDI[label] || ""}</span></div>
      </div>
    </div>

    <div class="stage" style="--i:${stage++}">
      ${report.overall_summary ? `<p class="cert-summary">“${esc(report.overall_summary)}”</p>` : ""}
      ${report.translation_en ? `<p class="cert-translation"><strong>Translation:</strong> ${esc(report.translation_en)}</p>` : ""}
    </div>

    <div class="cert-row stage" style="--i:${stage++}">
      <div class="confidence">
        <span class="label">Evidence confidence</span>
        <div class="streakbar"><i id="confbar"></i></div>
        <div class="pct">${conf}% · based on ${report.evidence.length} sources</div>
      </div>
      ${fp.signals.length ? `<div class="gauge-wrap">${gaugeHTML(fp)}
        <div><div class="fp-level fp-${esc(fp.level)}">${esc(fp.level)} viral markers</div>
        <div style="font-family:var(--font-caps);font-size:.6rem;letter-spacing:.28em;color:var(--ink-soft);margin-top:6px">FORWARD FINGERPRINT</div></div></div>` : ""}
    </div>

    ${fp.signals.length ? `<div class="stage" style="--i:${stage++}"><ul class="fp-signals">${fpSignals}</ul></div>` : ""}

    ${report.verdicts.length ? `<div class="stage" style="--i:${stage++}"><div class="section-title">Claims on the stone</div>${verdictBlocks}</div>` : ""}

    ${lensBlock}

    ${evidence ? `<div class="stage" style="--i:${stage++}"><div class="section-title">Evidence · credibility-ranked</div>
      <ul class="evidence-list">${evidence}</ul></div>` : ""}

    ${report.suggested_reply ? `<div class="stage" style="--i:${stage++}">
      <div class="section-title">Reply for the group</div>
      <div class="reply-card">
        <div id="reply-text"><span class="typing"><span></span><span></span><span></span></span></div>
        <div class="reply-actions" id="reply-actions" hidden>
          <button id="copy-reply" type="button">📋 Copy reply</button>
        </div>
      </div></div>` : ""}

    <div class="cert-foot stage" style="--i:${stage++}">
      <span><b>${report.searches_used}</b> SerpApi searches${report.offline ? " (offline fixtures)" : ""}</span>
      <span>${report.llm_used ? "LLM-assisted" : "rule-based mode"}</span>
      <span>${report.elapsed_s}s</span>
      <span>Kasauti assists judgement — read the evidence.</span>
    </div>
  </div>`;

  el.hidden = false;
  requestAnimationFrame(() => {
    const bar = $("#confbar"); if (bar) bar.style.width = conf + "%";
    const arc = $("#fp-arc");
    if (arc) {
      const C = 2 * Math.PI * 52;
      requestAnimationFrame(() => { arc.style.strokeDashoffset = (C * (1 - fp.score / 100)).toFixed(2); });
    }
  });

  if (report.suggested_reply) {
    const revealReply = () => {
      $("#reply-text").textContent = report.suggested_reply;
      $("#reply-actions").hidden = false;
      $("#copy-reply").addEventListener("click", async () => {
        const btn = $("#copy-reply");
        try {
          await navigator.clipboard.writeText(report.suggested_reply);
          btn.textContent = "✅ Copied — ab bhejo!";
          setTimeout(() => (btn.textContent = "📋 Copy reply"), 2500);
        } catch { btn.textContent = "Select & copy manually"; }
      });
    };
    setTimeout(revealReply, REDUCED ? 0 : 1500 + stage * 120);
  }

  el.scrollIntoView({ block: "start", behavior: REDUCED ? "auto" : "smooth" });
}

async function runCheck() {
  const text = $("#text").value.trim();
  const image = $("#image").value.trim();
  if (!text && !image) { $("#text").focus(); return; }

  const btn = $("#go"), log = $("#log");
  btn.disabled = true;
  $("#result").hidden = true;
  $("#banner").hidden = true;
  log.hidden = false; log.classList.remove("done");
  $("#log-lines").innerHTML = "";
  addLog("start", "Placing the message on the stone…");

  try {
    const res = await fetch("/api/check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, image_url: image || null }),
    });
    if (!res.ok || !res.body) throw new Error("Server error " + res.status);
    const reader = res.body.getReader(), decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, idx).trim(); buffer = buffer.slice(idx + 1);
        if (!line) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        if (msg.type === "event") { addLog(msg.stage, msg.detail); if (msg.stage === "done") log.classList.add("done"); }
        else if (msg.type === "report") { log.classList.add("done"); render(msg.report); }
        else if (msg.type === "error") { log.classList.add("done"); showBanner(esc(msg.message), true); }
      }
    }
  } catch (err) {
    log.classList.add("done");
    showBanner("Check failed: " + esc(err.message), true);
  } finally {
    btn.disabled = false;
  }
}

$("#go").addEventListener("click", runCheck);
$("#text").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runCheck(); });

// Deep links: /app?text=...&image=...&auto=1  (used by the landing page demo buttons)
(function fromQuery() {
  const q = new URLSearchParams(location.search);
  if (q.get("text")) $("#text").value = q.get("text");
  if (q.get("image")) $("#image").value = q.get("image");
  if (q.get("auto") === "1" && ($("#text").value || $("#image").value)) setTimeout(runCheck, 400);
})();

loadHealth();
loadExamples();
