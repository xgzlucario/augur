# Augur

> *In ancient Rome, an augur was the priest who read the will of the gods from the flight of birds. Before any matter of state, no senator dared vote without first consulting the augury.*
>
> *This one reads the tape.*

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

**Augur** convenes a council of eighteen of history's most consequential
investors — Buffett, Munger, Graham, Soros, Dalio, Simons, Cathie Wood,
Burry — and asks each, in their own voice, to render a verdict on the
ticker you give it. Each master reasons strictly within their own school of
thought. None defers to the others. A final editor reconciles the votes,
surfaces the dissent, and writes the augury.

You don't get an answer. You get the argument that produces one.

**Not financial advice. Research and entertainment.**

---

## Why a council, and not just an oracle?

Ask any general-purpose model what it thinks of a stock and you'll get the
average of the internet — equivocal, hedged, forgettable. The signal in
investing has never lived in averages. It lives in the *disagreements*
between people who think very differently and have each been right enough,
often enough, to be worth listening to.

Augur restores the disagreement. Buffett would have looked at the same
spreadsheet as Cathie Wood and reached the opposite conclusion — not from
ignorance, but from philosophy. Eighteen masters, eighteen lenses, one
ticker. The augury is what you can see only when you put them in the same
room.

---

## The Three Acts

### I · The Auspices

A research model plans four to six search queries — the questions a real
analyst would ask first — and Exa or Tavily executes them in parallel.
The hits are condensed into a single, balanced **market snapshot**: what
the company is, how the price has moved, where it sits in its sector, and
what the macro backdrop looks like.

Every claim in the snapshot is grounded in a live web result. Stale
training knowledge is never enough.

### II · The Council

The snapshot is laid before all eighteen masters at once. Each receives
the *same* briefing and replies in their own voice with a `PersonaVote`:
**buy / hold / sell**, time horizon, position size, key reasons, concerns,
and two or three paragraphs of reasoning in-character.

They vote independently. Buffett doesn't see Soros. Graham doesn't see
Wood. The dissent is real because the deliberation is private.

Up to ten masters reason in parallel; on a fast model the full council
returns in under a minute.

### III · The Augury

A senior editor — the synthesis model — reads every vote, weighs the
schools against each other, and composes the **augury**: a one-sentence
verdict and a balanced narrative covering consensus, fractures, the most
striking contrarian voices, and the catalysts that would change minds.

The full transcript — every master's individual reasoning, the vote
distribution by school, the most cited reasons and concerns — is written
to a Markdown report you can read, share, or feed into your own analysis.

---

## The Council

Eighteen masters across five schools of thought:

| School | Masters |
|---|---|
| **Value** | Buffett · Munger · Graham · Klarman · Marks · Grantham |
| **Growth** | Lynch · Fisher · Wood · Sleep |
| **Macro** | Soros · Dalio · Druckenmiller |
| **Quant** | Simons · Asness |
| **Contrarian** | Templeton · Dreman · Burry |

Each persona is a YAML file describing a philosophy, the metrics they
worship, the patterns they refuse to touch, and the cadence of their
voice. Adding your own takes ten lines.

---

## Quick Start

```bash
uv tool install git+https://github.com/xgzlucario/augur.git
augur list-personas        # confirm the eighteen are present
augur run AAPL             # convene the council
```

Augur needs two keys: an LLM provider and a search provider. Drop them in
a `.env` file in the directory where you'll run it:

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                   # blank for OpenAI; full URL for others
OPENAI_MODEL_RESEARCH=gpt-4o-mini  # cheap & fast — runs once per master
OPENAI_MODEL_SYNTHESIS=gpt-4o      # strong — runs three times per session

EXA_API_KEY=                       # https://exa.ai
TAVILY_API_KEY=                    # https://tavily.com
```

Any OpenAI-compatible provider works. A typical run takes one to two
minutes and costs roughly a dollar in tokens plus a handful of search
calls. Reports land under `./reports/<TICKER>_<YYYY-MM-DD>.md`.

---

## Usage

```bash
augur run AAPL                              # full council
augur run TSLA --limit 5                    # subset
augur run NVDA --schools value,contrarian   # one or more schools
augur run BTC --concurrency 5               # dial back parallelism
augur run AAPL --lang zh                    # narrative in Chinese
augur run AAPL -v                           # verbose logging
```

`--lang` accepts `en` (default), `zh`, `ja`, `ko`, `es`, `fr`, `de`, `pt`,
`ru`, or any language name the model understands. Free-text fields follow
the chosen language; structural fields (action, sizing, ticker) stay
English so downstream tooling keeps working.

---

## Add a Master

Drop a YAML under `personas/<school>/<id>.yaml`:

```yaml
id: my_master
name: My Master
school: value              # value | growth | macro | quant | contrarian
philosophy: |
  A sentence or two of core belief.
key_metrics:
  - The metrics they care about most
avoids:
  - The patterns they refuse to touch
voice: |
  Tone, mannerisms, the lines they're known for.
```

`augur list-personas` will pick them up on the next run. IDs must be
unique across the corpus.

---

## Disclaimer

Augur simulates historical investor personas for research and educational
purposes only. The verdicts are a thinking tool, not an investment
decision. Markets owe no one a reading. Consult a licensed professional
before putting capital to work.
