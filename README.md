# Augur

> *In ancient Rome, an augur was the priest who interpreted the will of the gods by observing the flight of birds. No senator dared vote on any state matter before consulting the augury first.*
>
> *This augur doesn't read birds. It reads the tape.*

```
 █████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗
██╔══██╗██║   ██║██╔════╝ ██║   ██║██╔══██╗
███████║██║   ██║██║  ███╗██║   ██║██████╔╝
██╔══██║██║   ██║██║   ██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
    a council of masters, summoned on demand
```

> [中文 README](./README.zh-CN.md)

**Augur** convenes a council of 18 of the most legendary investors in history — Buffett, Munger, Graham, Soros, Dalio, Simons, Cathie Wood, Michael Burry, and more — each delivering a verdict on your chosen ticker strictly through the lens of their own investment philosophy. No master defers to another, no opinion is watered down for consensus. A final editor synthesizes all votes, surfaces the most critical disagreements, and writes the final augury.

You don't get a generic answer. You get the full argument that produces one.

**Not financial advice. For research and entertainment purposes only.**

---

## Why a council, not just an oracle?

Ask any generic LLM for a stock opinion, and you'll get the watered-down average of every hot take on the internet — equivocal, over-hedged, instantly forgettable. Real investing signal never lives in the middle of the bell curve. It lives in the disagreements between exceptional minds who think wildly differently, and have proven their judgment right enough times to matter.

Augur brings those disagreements front and center. Buffett would look at the exact same spreadsheet as Cathie Wood and reach the opposite conclusion — not out of ignorance, but out of fundamentally different core beliefs. 18 masters, 18 unique lenses, one single ticker. The augury is what you can only see when you put all of them in the same room.

---

## The Three Acts

### I · The Auspices

A dedicated research model generates 4-6 targeted search queries — the exact questions a professional analyst would ask first — which are executed in parallel via Exa or Tavily. All results are condensed into a single, unbiased **market snapshot**: what the company does, how its price has moved recently, where it stands in its sector, and the current macro backdrop.

Every claim in the snapshot is grounded in real-time web results. Stale training data is never used as the sole source of truth.

### II · The Council

The snapshot is presented to all 18 masters simultaneously. Each receives the *exact same briefing* and replies in their signature voice with a `PersonaVote`: **buy / hold / sell**, time horizon, recommended position size, core reasoning, key concerns, and 2-3 paragraphs of in-character analysis.

All votes are fully independent. Buffett never sees Soros's opinion. Graham never sees Wood's take. The disagreements are genuine because deliberation happens entirely in private.

Up to 10 masters run in parallel; on a fast LLM, the full council returns results in under a minute.

### III · The Augury

A senior synthesis model reads every single vote, weighs the perspectives of different schools of thought against each other, and composes the final **augury**: a one-sentence verdict plus a balanced narrative covering consensus points, core fractures, the most striking contrarian opinions, and key catalysts that would change the masters' minds.

The full transcript — every master's individual reasoning, vote distribution by school, most frequently cited reasons and concerns — is saved as a Markdown report you can read, share, or integrate into your own analysis workflow.

---

## The Council

18 masters across 5 distinct schools of thought:

| School | Masters |
|---|---|
| **Value** | Buffett · Munger · Graham · Klarman · Marks · Grantham |
| **Growth** | Lynch · Fisher · Wood · Sleep |
| **Macro** | Soros · Dalio · Druckenmiller |
| **Quant** | Simons · Asness |
| **Contrarian** | Templeton · Dreman · Burry |

Each persona is defined in a simple YAML file describing their core philosophy, preferred metrics, red flags they avoid, and unique voice. Adding your own custom master takes just 10 lines.

---

## Quick Start

```bash
uv tool install git+https://github.com/xgzlucario/augur.git
augur list-personas        # Verify all 18 masters are available
augur run AAPL             # Convene the full council
```

Augur requires two sets of credentials: an LLM provider and a search provider. Add them to a `.env` file in the directory where you will run Augur:

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                   # Leave blank for OpenAI; fill full URL for other compatible providers
OPENAI_MODEL_RESEARCH=gpt-4o-mini  # Cheap & fast — called once per master
OPENAI_MODEL_SYNTHESIS=gpt-4o      # Higher capability — called 3 times per run

EXA_API_KEY=                       # Get from https://exa.ai
TAVILY_API_KEY=                    # Get from https://tavily.com
```

Any OpenAI-compatible API provider works. A typical full run takes 1-2 minutes, costs roughly $1 in token fees plus a small number of search calls, and saves reports to `./reports/<TICKER>_<YYYY-MM-DD>.md`.

---

## Usage

```bash
augur run AAPL                              # Full council vote
augur run TSLA --limit 5                    # Use only top 5 masters
augur run NVDA --schools value,contrarian   # Restrict to specific schools of thought
augur run BTC --concurrency 5               # Reduce parallelism for rate-limited providers
augur run AAPL --lang zh                    # Output narrative in Chinese
augur run AAPL -v                           # Enable verbose logging
```

The `--lang` flag supports `en` (default), `zh`, `ja`, `ko`, `es`, `fr`, `de`, `pt`, `ru`, and any other language your LLM understands. Free text fields follow the selected language, while structural fields (action, position size, ticker) remain in English for compatibility with downstream tooling.

---

## Add Your Own Master

Create a new YAML file under `personas/<school>/<id>.yaml`:

```yaml
id: my_master
name: My Master
school: value              # value | growth | macro | quant | contrarian
philosophy: |
  One or two sentences describing their core investment belief.
key_metrics:
  - List of metrics they prioritize above all else
avoids:
  - List of patterns or red flags they will never invest in
voice: |
  Description of their tone, mannerisms, and famous quotes they're known for.
```

Your new master will automatically appear in `augur list-personas` on the next run. All persona IDs must be unique across the entire corpus.

---

## Disclaimer

Augur simulates historical investor personas for research and educational purposes only. All outputs are thinking tools, not investment advice. Markets have no obligation to match any model's predictions. Always consult a licensed financial professional before making investment decisions.