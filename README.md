# Augur

> A council of legendary investors, summoned on demand. Give it a ticker; read the omens.

```
 █████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗
██╔══██╗██║   ██║██╔════╝ ██║   ██║██╔══██╗
███████║██║   ██║██║  ███╗██║   ██║██████╔╝
██╔══██║██║   ██║██║   ██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
```

*Augur*, n. — a priest of ancient Rome whose office was to read the will of
the gods in the flight of birds. This one reads the tape instead.

Point it at a ticker. Fifteen-plus historical investors — Buffett, Munger,
Graham, Soros, Dalio, Simons, Cathie Wood... — each study the same market
snapshot, each reason in their own voice, each vote independently. A final
synthesis surfaces the consensus, the fractures, and the contrarians worth
hearing.

Works with any **OpenAI-compatible** API (OpenAI, DeepSeek, Moonshot, Together,
Groq, vLLM, Ollama...). Optional **Exa web search** grounds the snapshot in
live data.

> [中文 README](./README.zh-CN.md)

**Not financial advice.** Research and entertainment. The bull-and-bear augury
is for thinking, not for trading.

---

## Pipeline

```
┌────────────────────────────────────────────────────────────────────────────┐
│  $ augur run AAPL --limit N                                                │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │
                 ┌─────────────▼────────────────┐
                 │  Phase 1  Market Snapshot    │
                 │  ─────────────────────────   │
                 │                              │
                 │  ┌─ if EXA_API_KEY set ─┐    │
                 │  │  ① LLM plans 4-6     │    │
                 │  │    search queries    │    │
                 │  │  ② Exa runs them     │    │
                 │  │    in parallel       │    │
                 │  │  ③ LLM synthesizes   │    │
                 │  │    Snapshot from     │    │
                 │  │    search results    │    │
                 │  └──────────────────────┘    │
                 │                              │
                 │  ┌─ else ───────────────┐    │
                 │  │  LLM generates       │    │
                 │  │  Snapshot from       │    │
                 │  │  training knowledge  │    │
                 │  └──────────────────────┘    │
                 │                              │
                 │  Output: shared Snapshot     │
                 └─────────────┬────────────────┘
                               │
                 ┌─────────────▼────────────────┐
                 │  Phase 2  The Auspices       │
                 │  ─────────────────────────   │
                 │                              │
                 │  asyncio.gather over         │
                 │  Semaphore(concurrency):     │
                 │                              │
                 │  ┌──────┐ ┌──────┐ ┌──────┐  │
                 │  │Buffett│ │ Soros│ │ ...  │  │
                 │  └───┬──┘ └──┬───┘ └──┬───┘  │
                 │      │       │        │      │
                 │   research research research │
                 │    model × N calls           │
                 │      │       │        │      │
                 │      ▼       ▼        ▼      │
                 │   PersonaVote (JSON)         │
                 │   • action: buy/hold/sell    │
                 │   • confidence 0-100         │
                 │   • key_reasons / concerns   │
                 │   • reasoning (2-3 ¶)        │
                 │                              │
                 │  Shared system prompt =      │
                 │  framework + snapshot        │
                 │  (identical bytes → prefix   │
                 │   cache hits where supported)│
                 └─────────────┬────────────────┘
                               │
                 ┌─────────────▼────────────────┐
                 │  Phase 3  The Augury         │
                 │  ─────────────────────────   │
                 │                              │
                 │  • Deterministic stats       │
                 │    (counts by action/school, │
                 │     top reasons/concerns)    │
                 │                              │
                 │  • Synthesis model reads all │
                 │    votes and writes the      │
                 │    narrative: consensus,     │
                 │    fractures, contrarians,   │
                 │    mind-changers             │
                 └─────────────┬────────────────┘
                               │
                               ▼
                  reports/AAPL_YYYY-MM-DD.md
```

---

## Setup

```bash
cd augur
python3 -m venv .venv
.venv/bin/pip install -e .

cp .env.example .env              # fill in keys + model IDs
.venv/bin/augur list-personas     # verify install
```

Python 3.11+ required.

### `.env`

```env
# Required: OpenAI-compatible LLM endpoint
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                  # blank for OpenAI; full URL for others

# Required: model IDs for each tier
OPENAI_MODEL_RESEARCH=gpt-4o-mini # runs N× (once per master) — pick cheap + fast
OPENAI_MODEL_SYNTHESIS=gpt-4o     # runs 2× (snapshot + aggregator) — pick quality

# Optional: Exa web search (grounds snapshot in live data)
EXA_API_KEY=                      # get one at https://exa.ai
```

---

## Usage

```bash
# Full council
augur run AAPL

# Subset
augur run TSLA --limit 5
augur run NVDA --schools value,contrarian
augur run BTC --concurrency 5

# Force training-knowledge snapshot even with EXA_API_KEY set
augur run AAPL --no-search

# Inspect the roster
augur list-personas

# Verbose debug logging
augur run AAPL -v
```

Reports land in `reports/<TICKER>_<YYYY-MM-DD>.md`.

---

## Web search

Set `EXA_API_KEY` → automatic. The snapshot becomes LLM-planned-search-and-summarize:

1. Synthesis model generates 4-6 diverse queries for the ticker.
2. Exa executes them in parallel (`numResults=5`, returns text + highlights).
3. Synthesis model reads the aggregated results and writes the structured Snapshot.
4. If search returns zero hits, falls back to LLM-only. If `EXA_API_KEY` is
   unset or `--no-search` is passed, skip search entirely.

**Adding another provider** (Tavily, Serper, Brave, ...):

1. Add a class in `src/augur/search.py` implementing `async def search(query, num_results) -> list[SearchResult]`.
2. Extend `get_provider()` to return it when the relevant env var is set.

Only Exa is implemented today, but the `SearchProvider` Protocol keeps adding
one cheap.

---

## Adding a new master

Drop a YAML under `personas/<school>/<id>.yaml`:

```yaml
id: my_master
name: My Master
school: value              # value | growth | macro | quant | contrarian
era: "1980-2020"
philosophy: |
  Two or three sentences of core belief.
key_metrics:
  - Specific metric 1
  - Specific metric 2
avoids:
  - Specific anti-pattern 1
voice: |
  How they speak: tone, mannerisms, what they quote.
```

IDs must be unique across all YAMLs. Every ID appears verbatim in the augury.

15 masters ship by default across five schools (value, growth, macro, quant,
contrarian). `augur list-personas` shows the full roster.

---

## Project layout

```
src/augur/
  client.py        AsyncOpenAI singleton + model ID getters
  schemas.py       Pydantic: Snapshot, Decision, PersonaVote, RunStats
  personas.py      YAML loading + persona prompt rendering
  search.py        SearchProvider Protocol + ExaSearch impl + factory
  snapshot.py      Phase 1 (plan → search → synthesize, or LLM-only fallback)
  analyst.py       Single master call (research model + JSON via prompt)
  orchestrator.py  Phase 2 fan-out with asyncio.gather + Semaphore
  aggregator.py    Deterministic stats + synthesis-model narrative
  report.py        Markdown rendering
  cli.py           Typer entry point (single async pipeline)
  json_utils.py    Lenient JSON extraction (fences, prose, brace slice)
personas/          Master YAMLs grouped by school
reports/           Generated auguries (gitignored)
```

---

## Implementation notes

- **Model tiers exist for a reason.** Research model runs once per master
  (can be 100+ calls in a big council); synthesis model runs twice per run.
  Cheap-fast at research, strong at synthesis — roughly 10× cost win.
- **The system prompt is constructed once per run and sent identically on
  every master call.** That's the prerequisite for any prefix caching your
  provider might offer (OpenAI, DeepSeek, Moonshot, vLLM with prefix caching,
  etc.).
- **No `response_format={"type": "json_object"}`.** Some OpenAI-compatible
  providers silently drop or mis-handle it. Augur constrains JSON purely via
  prompt rules and parses with a lenient extractor (`json_utils.extract_json`)
  that tolerates markdown fences and surrounding prose.
- **Failed masters are skipped, not fatal.** A JSON parse failure or API
  error on master X means that vote is dropped and the run continues. The
  report footer lists which masters failed.
- **No cost estimate built in.** Cost depends on your provider's pricing.
  `RunStats` reports token counts; multiply by your provider's rates.

---

## Disclaimer

Augur simulates historical investors. It is a research and thinking tool, not
financial advice. Models can be wrong, biased, or out of date. The output is
for imagining how a council of dead investors might argue — not for deciding
what to do with your money. Consult a licensed professional for actual
investment decisions.
