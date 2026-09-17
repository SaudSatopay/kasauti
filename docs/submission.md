# Submission pack — SerpApi India Hackathon 2026

Deadline: **October 5, 2026, 23:59 IST**. Submit at the hackathon site
(sign in with GitHub). Eligibility: participants must be 18+ **and reside in
India**; teams of 1–5. Copy-paste answers below, then fill the personal
fields.

---

**Project name:** Kasauti (कसौटी)

**One-liner:** The touchstone for WhatsApp forwards — an evidence-first
misinformation checker for India that verifies viral claims and recycled
images against live search, and drafts the polite correction you can actually
send back to the family group.

**Track:** Knowledge & Public Interest *(news literacy — also fits AI Agents;
pick one at submission time)*

**Repository:** `https://github.com/SaudSatopay/kasauti` *(must be public —
verify in incognito)*

**Demo video:** *(unlisted YouTube link — verify in incognito; under 3 min;
script in [demo-video-script.md](demo-video-script.md))*

---

**Project description (paste into the form):**

> India's most-forwarded lies follow a pattern: a hoax award, a fake
> government scheme, a miracle cure, or a real photo recycled with a false
> caption. Kasauti (कसौटी — "touchstone") is where you test them. Paste any
> forward — Hindi, Hinglish or English, with or without an image — and a
> six-stage pipeline goes to work: offline "Forward Fingerprint" heuristics
> spot chain-message DNA; an LLM splits the text into atomic checkable
> claims; SerpApi retrieves live evidence through four strategies (Google
> Search organic results, Google News coverage, a site: sweep across eight
> Indian fact-checking desks, and Google Lens reverse-image search that
> exposes recycled photos via an earliest-appearance timeline); a transparent
> credibility registry weighs every source; an LLM judge issues per-claim
> verdicts under deterministic guardrails that forbid confidence the evidence
> doesn't support; and finally Kasauti drafts a warm, non-preachy correction
> in the language of the forward, receipts attached. It ships as a web app,
> CLI, Python library and MCP server (so any AI assistant gains a
> fact-checking tool), runs usefully on a free SerpApi key (~3–7 searches per
> check, budget counter on every report), degrades gracefully to a fully
> rule-based mode with no LLM key, and carries 51 offline tests plus CI that
> spend zero API credits.

**Which SerpApi products are used, and why they matter (form asks this
explicitly):**

> Google Search API — organic web evidence per claim, India-localised
> (google.co.in, gl=in); also powers a targeted `site:` sweep across
> altnews.in, boomlive.in, factly.in, vishvasnews.com, newschecker.in,
> factcrescendo.com, factcheck.afp.com and pib.gov.in, which is usually the
> decisive evidence. Google News API — freshness signal: real events leave a
> news trail, hoaxes leave a trail of debunks. Google Lens API — reverse
> image search that catches India's single most common misinformation
> format, the old photo recycled as breaking news, by dating the image's
> earlier appearances. SerpApi is the project's entire evidence layer; every
> citation in every verdict came through it. Structured JSON (titles, links,
> sources, dates) is precisely the input a credibility-weighting pipeline
> needs — no scraping, no CAPTCHAs, one clean module (src/kasauti/serp.py).

**Prior existence disclosure:** Built from scratch for this hackathon
(September 2026). No prior codebase.

**AI tools disclosure (required):** Developed with AI pair-programming
assistance (Claude Code by Anthropic) for code authoring under human
direction and review. At runtime the tool optionally uses a user-supplied LLM
(Gemini/OpenAI/Anthropic/Groq/Ollama) for claim extraction, verdict drafting
and reply drafting; all evidence retrieval, credibility weighting and
confidence guardrails are deterministic, reviewable code.

**Setup instructions:** In the README — clone, `pip install -e .`, set
`SERPAPI_API_KEY` in `.env`, `kasauti serve`. Works on a free SerpApi key;
LLM optional.

---

**Lead participant fields (fill yourself):** name · email · phone ·
occupation · experience. Team members (up to 4 more): names + emails.
⚠️ Remember: every member must be 18+, reside in India, and have contributed.

**Pre-submission checklist**
- [ ] Repo public; open the URL logged out to confirm
- [ ] `README.md` renders correctly on GitHub (badges, mermaid diagram)
- [ ] Fresh-clone test on a clean machine: quickstart works exactly as written
- [ ] Live run with a real SerpApi key: both demo chips succeed
- [ ] Demo video < 3:00, link public/unlisted, opens in incognito
- [ ] No secrets anywhere in the repo or video (`git log -p | findstr /i "api_key"` sanity pass; `.env` is gitignored)
- [ ] Track selected; disclosures pasted; Rules & T&C accepted
