# Kasauti — architecture notes

A deeper tour than the README, for reviewers who want to know *why* the
pipeline is shaped the way it is.

## Design goals

1. **Evidence-first, model-second.** LLMs draft; deterministic code decides
   what they're allowed to claim. A misinformation checker that hallucinates
   is worse than none.
2. **Runs on a free SerpApi key.** Every design choice is audited against a
   250-search monthly budget.
3. **Zero-friction judging.** One required key, graceful degradation without
   an LLM, offline fixtures for tests, `kasauti serve` and you're looking at
   the demo.
4. **India-shaped.** Hinglish and Devanagari in the heuristics, Indian
   fact-check desks in the registry, `google.co.in` localisation, and a reply
   generator tuned for family-group diplomacy.

## The pipeline, stage by stage

### 1. Forward Fingerprint (`fingerprint.py`)

Pure-regex heuristics over the raw text — no API, no model, ~1 ms. Each rule
carries a weight and a human explanation; the sum (capped at 100) maps to
low/medium/high. Patterns cover English, romanised Hinglish and Devanagari
("जल्दी शेयर", "har group me bhejo", "media won't show this").

Why it exists: (a) instant feedback while searches run; (b) the *explanations*
teach users to spot the pattern themselves — the news-literacy goal; (c) it
feeds the judge prompt as context but never decides a verdict alone.

### 2. Claim extraction (`claims.py`)

The LLM path returns strict JSON: dominant language, English translation,
one-sentence summary, and ≤ `KASAUTI_MAX_CLAIMS` (default 2, hard cap 4)
atomic claims, each with two search queries from different angles. Fact-check
phrasing is stripped from queries (the sweep strategy owns that space, and
"fact check" in a query biases organic results toward fact-check pages,
double-counting the signal).

The fallback path cleans the text (URLs, "forwarded as received", markdown
noise), truncates, and searches it directly — crude but budget-identical.

### 3. Retrieval (`serp.py`)

Four strategies, three engines, all through the official `serpapi` client:

| Strategy | Engine | Params that matter |
|---|---|---|
| Organic web | `google` | `google_domain=google.co.in`, `gl=in`, `num=10` |
| News | `google_news` | `gl=in` |
| Fact-check sweep | `google` | `q = <query> (site:altnews.in OR … OR site:pib.gov.in)` |
| Reverse image | `google_lens` | `url=<image>`, `type=all`, `country=in` |

Per claim, the three text strategies run in a thread pool; Lens runs alongside.
Latency ≈ one round trip, not four.

Infrastructure in the same module:

- **Budget counter** — `searches_used` travels into every `Report`; the UI
  prints it. Honesty about cost is a feature.
- **Disk cache** (`.kasauti_cache/`, sha256 of params, 22 h TTL) — iterating on
  the same forward during development costs zero credits. Cache hits don't
  increment the budget counter because they don't cost anything.
- **Offline fixtures** — `KASAUTI_OFFLINE=1` serves bundled SerpApi-shaped
  JSON matched by keyword overlap (engine-scoped, ties broken by specificity).
  The entire test suite and CI run this way. Fixtures are clearly marked
  (`"status": "Success (bundled fixture)"`) and never used in live checks.

### 4. Evidence (`evidence.py`, `sources.py`)

Normalisation flattens engine-specific shapes (including `google_news` nested
`stories`) into one record. Dedup is two-pass: canonical-URL exact match, then
fuzzy title match (`difflib` > 0.9) within a domain to kill syndicated copies.

Scoring: `credibility_weight × (0.45 + 0.55 × relevance) × recency_factor`,
where relevance is stopword-filtered token overlap between claim and
title+snippet. Two deliberate asymmetries:

- **Fact-checkers and official sources are never punished for age.** A 2023
  debunk of a 2016 hoax is decisive in 2026 — recycled hoaxes are the genre.
- **A relevant fact-checker gets a flat bonus** so volume can never outrank
  it: ten blog posts spreading a hoax must not bury one Alt News debunk.

The registry (`sources.py`) is a plain, PR-able dict of ~90 domains in seven
tiers. It classifies publisher *type*, not editorial stance. Unknown domains
get weight 0.35 — weak evidence, not anti-evidence. Satire domains are their
own tier because "forward takes The Onion/Faking News literally" is a real
and recurring verdict.

### 5. Verdict (`verdict.py`)

The judge prompt receives a numbered evidence table with tier labels and
dates, plus the Lens timeline when present. It must return a label from the
fixed vocabulary, confidence, a ≤70-word rationale citing `[En]` ids, and the
citation list.

Then the guardrails run — *after* the model, unconditionally:

| Situation | Enforcement |
|---|---|
| No valid citations | label → `unverified`, confidence ≤ 0.35 |
| Only unknown-tier citations | confidence ≤ 0.55 |
| `true`/`false` above 0.8 | requires a fact-checker or official citation |
| Any cited satire-tier source | label → `satire` |
| Cited ids not in the table | dropped before all other checks |

Every intervention is recorded in `guardrail_notes` and shown in the UI —
calibration you can see.

The no-LLM fallback is deliberately conservative: fact-check-tier results
whose *headlines* carry debunk language ("no,", "fake", "hoax", "फर्जी"…) can
produce `false` at 0.6–0.7; everything else stays `unverified` with the
evidence laid out. Headlines are the only text we can trust without reading
the page, so that's all the fallback reads.

Overall verdict = worst label among claims with confidence ≥ 0.45 (all claims
if none clear the bar) — a forward that is half true and half false is a
false forward.

### 6. Reply (`reply.py`)

LLM path: ≤75 words, same language as the forward, warm, one emoji max,
blame-the-message-not-the-sender, 1–2 highest-credibility links. Fallback:
per-label templates in English and Hinglish. This stage exists because the
social cost of correction — not the absence of facts — is why misinformation
wins in group chats.

## Interfaces

One `check()` function, four doors — `cli.py` (rich terminal certificates,
`--json` for scripting), `server.py` (FastAPI; `POST /api/check` streams
NDJSON progress events then the report, so the UI narrates the agent's work
live), `mcp_server.py` (FastMCP `verify_forward` tool over stdio), and the
Python API.

The web UI is two static pages with no build step: `/` is the landing page
(`webui/index.html` — the hero, the hoax ticker, the pipeline walkthrough,
the credibility ladder and the SerpApi engines section) and `/app` is the
checker (`webui/app.html`). The checker accepts deep links —
`/app?text=…&image=…&auto=1` — which the landing page's "run this exact
check" buttons use, and which make reproducible screenshots trivial. Static
files are served with `Cache-Control: no-cache` so a browser always
revalidates (cheap ETag 304s) and never shows a stale stylesheet after an
update.

## Testing philosophy

51 tests, all offline, all key-free: heuristics per language, tiering, every
observed SerpApi date format, dedup/ranking asymmetries, every guardrail,
both fallbacks, the streaming server contract, and two end-to-end fixture
runs (text hoax → FALSE; recycled image → 2015 timeline). CI (GitHub Actions,
Python 3.10 + 3.12) runs the suite with no secrets configured — by design it
can't spend credits.

## Honest limitations

- Rule-based mode reads headlines, not article bodies; it says so in its
  rationales.
- The registry is a curated starting point, not a census of Indian media;
  regional-language desks are underrepresented (roadmap).
- Lens matches often lack machine-readable dates; the timeline uses what's
  dated and shows the rest as context.
- Kasauti evaluates *claims against reporting*, not novel private facts — if
  nobody has reported it, the honest answer is `unverified`, and that's what
  it returns.
