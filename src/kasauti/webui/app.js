/* Kasauti web UI — streams the pipeline's progress, then renders the
   assay certificate. Vanilla JS, no build step. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);

const LABELS = {
  true: "TRUE", mostly_true: "MOSTLY TRUE", misleading: "MISLEADING",
  false: "FALSE", outdated: "OUTDATED", unverified: "UNVERIFIED", satire: "SATIRE",
};
const LABEL_HINDI = {
  true: "सही", mostly_true: "लगभग सही", misleading: "भ्रामक",
  false: "फर्ज़ी", outdated: "पुरानी खबर", unverified: "अपुष्ट", satire: "व्यंग्य",
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const h = await res.json();
    const banner = $("#banner");
    if (!h.serpapi) {
      banner.hidden = false;
      banner.className = "banner error";
      banner.innerHTML =
        "No SerpApi key found. Add <code>SERPAPI_API_KEY</code> to your <code>.env</code> " +
        '(free key: <a href="https://serpapi.com/manage-api-key" target="_blank" rel="noopener">serpapi.com</a>).';
    } else if (!h.llm) {
      banner.hidden = false;
      banner.className = "banner";
      banner.innerHTML =
        "Running in <strong>rule-based mode</strong> (no LLM key found). Verdicts will be " +
        "conservative. Add a <code>GEMINI_API_KEY</code> / <code>OPENAI_API_KEY</code> for full analysis.";
    }
  } catch { /* server not ready — ignore */ }
}

async function loadExamples() {
  try {
    const res = await fetch("/api/examples");
    const examples = await res.json();
    const holder = $("#chips");
    for (const ex of examples.slice(0, 4)) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = "✦ " + ex.name;
      b.addEventListener("click", () => {
        $("#text").value = ex.text || "";
        $("#image").value = ex.image_url || "";
        $("#text").focus();
      });
      holder.appendChild(b);
    }
  } catch { /* fine without examples */ }
}

function addLog(stage, detail) {
  const li = document.createElement("li");
  li.innerHTML = `<strong>${esc(stage)}</strong> · ${esc(detail)}`;
  $("#log-lines").appendChild(li);
  li.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function evidenceRow(e) {
  const date = e.date ? e.date.slice(0, 10) : (e.date_raw || "");
  return `<li>
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

function render(report) {
  const el = $("#result");
  const label = report.overall_label;
  const conf = Math.round(report.overall_confidence * 100);
  const claimsById = Object.fromEntries(report.claims.map(c => [c.id, c]));

  const fp = report.fingerprint || { score: 0, level: "low", signals: [] };
  const fpSignals = fp.signals.map(s =>
    `<li>${esc(s.label)}<small>${esc(s.detail)}</small></li>`).join("");

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
    lensBlock = `
      <div class="section-title">Image check · Google Lens</div>
      <div class="lens-note">${esc(report.image.note || "")}</div>
      ${strip ? `<div class="lens-strip">${strip}</div>` : ""}`;
  }

  const evidence = (report.evidence || []).slice(0, 12).map(evidenceRow).join("");

  const replyBlock = report.suggested_reply ? `
    <div class="section-title">Reply for the group</div>
    <div class="reply-card">
      <div id="reply-text">${esc(report.suggested_reply)}</div>
      <div class="reply-actions">
        <button id="copy-reply" type="button">📋 Copy reply</button>
      </div>
    </div>` : "";

  el.innerHTML = `
  <div class="certificate">
    <div class="cert-head">
      <div class="cert-title">ASSAY CERTIFICATE<small>कसौटी · EVIDENCE-FIRST VERIFICATION</small></div>
      <div class="stamp ${esc(label)}">${LABELS[label] || label}<br>
        <span style="font-family:var(--font-hindi);font-size:.55em;letter-spacing:.2em">${LABEL_HINDI[label] || ""}</span>
      </div>
    </div>

    ${report.overall_summary ? `<p class="cert-summary">“${esc(report.overall_summary)}”</p>` : ""}
    ${report.translation_en ? `<p class="cert-translation"><strong>Translation:</strong> ${esc(report.translation_en)}</p>` : ""}

    <div class="confidence">
      <span class="label">Evidence confidence</span>
      <div class="streakbar"><i id="confbar"></i></div>
      <div class="pct">${conf}% · based on ${report.evidence.length} sources</div>
    </div>

    ${fp.signals.length ? `
      <div class="section-title">Forward fingerprint</div>
      <div class="fp-meter">
        <span class="fp-score">${fp.score}<small>/100</small></span>
        <span class="fp-level fp-${esc(fp.level)}">${esc(fp.level)} viral markers</span>
      </div>
      <ul class="fp-signals">${fpSignals}</ul>` : ""}

    ${report.verdicts.length ? `<div class="section-title">Claims on the stone</div>${verdictBlocks}` : ""}

    ${lensBlock}

    ${evidence ? `<div class="section-title">Evidence · credibility-ranked</div>
      <ul class="evidence-list">${evidence}</ul>` : ""}

    ${replyBlock}

    <div class="cert-foot">
      <span>${report.searches_used} SerpApi searches${report.offline ? " (offline fixtures)" : ""}</span>
      <span>${report.llm_used ? "LLM-assisted" : "rule-based mode"}</span>
      <span>${report.elapsed_s}s</span>
      <span>Kasauti assists judgement — read the evidence.</span>
    </div>
  </div>`;

  el.hidden = false;
  requestAnimationFrame(() => { $("#confbar").style.width = conf + "%"; });

  const copyBtn = $("#copy-reply");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(report.suggested_reply);
        copyBtn.textContent = "✅ Copied — ab bhejo!";
        setTimeout(() => (copyBtn.textContent = "📋 Copy reply"), 2500);
      } catch {
        copyBtn.textContent = "Select & copy manually";
      }
    });
  }
  el.scrollIntoView({ block: "start", behavior: "smooth" });
}

async function runCheck() {
  const text = $("#text").value.trim();
  const image = $("#image").value.trim();
  if (!text && !image) { $("#text").focus(); return; }

  const btn = $("#go");
  btn.disabled = true;
  $("#result").hidden = true;
  $("#log").hidden = false;
  $("#log-lines").innerHTML = "";
  addLog("start", "Placing the message on the stone…");

  try {
    const res = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, image_url: image || null }),
    });
    if (!res.ok || !res.body) throw new Error("Server error " + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (!line) continue;
        let msg;
        try { msg = JSON.parse(line); } catch { continue; }
        if (msg.type === "event") addLog(msg.stage, msg.detail);
        else if (msg.type === "report") render(msg.report);
        else if (msg.type === "error") {
          const banner = $("#banner");
          banner.hidden = false; banner.className = "banner error";
          banner.textContent = msg.message;
        }
      }
    }
  } catch (err) {
    const banner = $("#banner");
    banner.hidden = false; banner.className = "banner error";
    banner.textContent = "Check failed: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

$("#go").addEventListener("click", runCheck);
$("#text").addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runCheck();
});

loadHealth();
loadExamples();
