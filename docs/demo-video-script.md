# Demo video script — 3 minutes, shot by shot

Rules recap: **under 3 minutes**, screen recording showing real functionality,
publicly accessible link (unlisted YouTube works). Video quality does not
affect judging — clarity does. Record at 1080p, mic optional but recommended.

**Setup before recording:** `kasauti serve` running with a real
`SERPAPI_API_KEY` **and** a `GEMINI_API_KEY` (or other LLM key) in `.env` —
remove `KASAUTI_OFFLINE`. Do one warm-up run of each demo so the SerpApi cache
makes the recording fast and deterministic. Browser at 100% zoom, dark room
vibes, no bookmarks bar.

---

### 0:00–0:20 — The hook (family group problem)

*Screen: the Kasauti landing page. Speak over it.*

> "Every Indian family group has that one forward. UNESCO gave our anthem an
> award. The government is giving free recharge. This photo is from
> yesterday's floods. Fact-checkers debunk these every day — but the debunk
> never reaches the group. **Kasauti** is the touchstone: paste the forward,
> streak it against the live web, read the mark."

### 0:20–1:05 — Demo 1: the UNESCO anthem hoax (text pipeline)

*Click the **UNESCO anthem 'award'** chip → **Test it on the stone**.*

> "Watch it work. First the Forward Fingerprint — offline heuristics that
> catch the chain-forward DNA: begs to be forwarded, vague authority, all
> caps. Then it extracts the checkable claims and goes to the web — live,
> through SerpApi: Google Search, Google News, and one targeted sweep across
> eight Indian fact-checking desks."

*The certificate slams in: FALSE stamp.*

> "Verdict: FALSE — and look at *why*. Alt News, BOOM, Factly, Vishvas News —
> ranked by a transparent credibility registry. The blogspot page spreading
> the hoax? Bottom of the list, 'unrecognised source'."

### 1:05–1:35 — The reply (the human feature)

*Scroll to the reply card, click **Copy reply**.*

> "And here's the part nobody builds: the awkward conversation. Kasauti
> drafts a polite correction *in the language of the forward* — Hinglish in,
> Hinglish out — receipts attached, no lecturing. One tap, paste it back in
> the group, uncle ki izzat intact."

### 1:35–2:15 — Demo 2: the recycled flood photo (Google Lens)

*Click the **Old photo as new flood** chip (text + image URL) → run.*

> "The biggest lie format in India isn't fake photos — it's *real* photos
> with fake captions. 'Yesterday's Mumbai floods.' Kasauti sends the image to
> **Google Lens through SerpApi** and builds an earliest-appearance timeline…
> There it is: this photo has lived on Wikipedia since **December 2015**.
> It's the Chennai floods, ten years ago. Verdict: OUTDATED."

*Point at the timeline strip with the dated matches.*

### 2:15–2:40 — Beyond the app (CLI + MCP, for the engineers)

*Split or quick cuts: terminal running
`kasauti check "..." --json | head`, then the Claude Desktop config with
`"kasauti": {"command": "kasauti", "args": ["mcp"]}` and Claude answering
"is this forward real?" using the tool.*

> "Everything is one pipeline with four doors: this web app, a CLI that
> emits full JSON reports, a Python library — and an MCP server, so any AI
> assistant can call Kasauti as a fact-checking tool."

### 2:40–3:00 — Close

*Back on the certificate; point at the footer line.*

> "Every check costs three to seven SerpApi searches — the counter's right
> here — so a free key covers a family's worth of forwards every month.
> Fifty-one offline tests, guardrails that stop the AI from claiming more
> than the evidence shows, MIT licensed. Kasauti — check karo, phir forward
> karo."

---

**Recording checklist**
- [ ] Real API keys in `.env`, `KASAUTI_OFFLINE` removed
- [ ] Warm-up run done (cache primed → fast, deterministic demo)
- [ ] Both demo chips verified working live right before recording
- [ ] Timer visible to yourself; hard stop at 2:55
- [ ] Upload as unlisted YouTube video; test the link in an incognito window
