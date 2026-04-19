# Augur

> A council of legendary investors, summoned on demand. Feed it a ticker; read the omens.

```
 █████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗
██╔══██╗██║   ██║██╔════╝ ██║   ██║██╔══██╗
███████║██║   ██║██║  ███╗██║   ██║██████╔╝
██╔══██║██║   ██║██║   ██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
```

*Augur* — in ancient Rome, the priest who read the will of the gods from
the flight of birds. This one reads the tape.

Fifteen historical investors — Buffett, Munger, Graham, Soros, Dalio, Simons,
Cathie Wood… — each study the same market snapshot, each reason in their own
voice, each vote independently. A final editor reconciles consensus with
dissent and writes the augury.

Runs on any **OpenAI-compatible** LLM (OpenAI, DeepSeek, Moonshot, Groq,
Ollama…). A search key (**Exa** or **Tavily**) is required — training data is
too stale for this game.

> [中文 README](./README.zh-CN.md)

**Not financial advice.** Research and entertainment.

---

## The three phases

**The Auspices.** The synthesis model plans 4–6 search queries; Exa or Tavily
runs them in parallel; the model condenses the ~30 hits into a shared
`Snapshot`. Queries stream to the terminal — you see what the oracle chose to
look for.

**The Council.** Augur fans out one call per master, up to ten in flight. Every
call sends a byte-identical system prompt (framework + snapshot) so prefix
caching can kick in. Each master replies with a `PersonaVote` in voice:
buy/hold/sell, confidence, horizon, sizing, reasons, concerns, a 2–3 paragraph
argument. Votes stream back as they land; masters that fail parsing are
skipped, not fatal.

**The Augury.** Local stats tally votes by action and school. The synthesis
model then reads every vote and writes a balanced editor's note — consensus,
fractures, contrarians, what would change minds — into a Markdown report
under `./reports/`.

Typical run: **1–2 minutes**, ~30 search hits, three synthesis calls plus
N research calls (one per master).

---

## Install

**Recommended** — global, one command:

```bash
uv tool install git+https://github.com/xgzlucario/augur.git
augur list-personas   # should show 15 masters
```

From source:

```bash
git clone https://github.com/xgzlucario/augur.git && cd augur
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/augur list-personas
```

Python 3.11+ required.

---

## Configure

Drop a `.env` in the directory you run `augur` from:

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                  # blank for OpenAI; full URL otherwise
OPENAI_MODEL_RESEARCH=gpt-4o-mini # runs N× (once per master) — cheap + fast
OPENAI_MODEL_SYNTHESIS=gpt-4o     # runs 3× (plan / snapshot / narrative) — quality

# Search — required
EXA_API_KEY=                      # https://exa.ai
TAVILY_API_KEY=                   # https://tavily.com
# SEARCH_PROVIDER=exa             # pin when both keys are set
```

Both search keys set? Exa wins unless `SEARCH_PROVIDER=tavily`. Reports land
in `./reports/` under the directory where you invoke `augur`.

---

## Usage

```bash
augur run AAPL                              # full council
augur run TSLA --limit 5                    # subset
augur run NVDA --schools value,contrarian   # one or more schools
augur run BTC --concurrency 5               # dial back parallelism
augur list-personas                          # inspect the roster
augur run AAPL -v                            # verbose logging
```

Reports: `reports/<TICKER>_<YYYY-MM-DD>.md`.

---

## Add a master

Drop a YAML under `personas/<school>/<id>.yaml`:

```yaml
id: my_master
name: My Master
school: value              # value | growth | macro | quant | contrarian
philosophy: |
  A sentence or two of core belief.
key_metrics:
  - Metric 1
avoids:
  - Anti-pattern 1
voice: |
  Tone, mannerisms, what they quote.
```

IDs must be unique. `augur list-personas` lists the current 15 across five
schools (value, growth, macro, quant, contrarian).

---

## Project layout

```
src/augur/
  cli.py           Typer entry + fan-out pipeline
  snapshot.py      Phase 1 — plan → search → synthesize
  analyst.py       One master → one PersonaVote
  aggregator.py    Stats + narrative
  search.py        Exa & Tavily providers
  personas.py      YAML loading + prompt rendering
  schemas.py       Pydantic models
  client.py        AsyncOpenAI + model getters
  report.py        Markdown renderer
  json_utils.py    Lenient JSON extraction
personas/          YAMLs grouped by school (bundled with the package)
reports/           Generated auguries (gitignored)
```

---

## Design notes

- **Two model tiers.** Research runs once per master; synthesis runs three
  times. Cheap-fast below, strong above — roughly 10× cost win at scale.
- **No `response_format`.** Many OpenAI-compatible providers mishandle
  `json_object` mode. Augur constrains JSON purely via prompt and parses with
  a lenient extractor that survives markdown fences and prose wrapping.
- **Fail loud.** A failed query plan or zero search hits terminates with a red
  panel — stale training knowledge is worse than no answer.

---

## Disclaimer

Augur simulates dead investors. Its output is a thinking tool, not an
investment decision. Consult a licensed professional before trading.
