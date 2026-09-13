# SignalPath

Turn observational data into a ranked, explainable sales queue. Cybersecurity
is the first vertical, not the product.

A **vertical** is a sales motion: its own signal catalog, weights, attribution
rules, eval set, and prompt. The engine (identity, rollup, gating, tracing,
outreach skill) stays the same.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run app.py
```

Default vertical is `cybersecurity` (`VERTICAL=cybersecurity`). The dashboard
works without an API key. To enable outreach drafting:

```bash
cp .env.example .env
export OPENAI_API_KEY="..."
```

## Verify

```bash
ruff check .
pytest
python evals/run_evals.py
```

## Add another business use case

1. `config/verticals/<id>.yaml` — weights, gate, prompt path, identity denylists.
2. `src/verticals/<id>.py` — `extract_record_signals(record, rules)`.
3. Register it in `src/verticals/__init__.py` (`EXTRACTORS`).
4. Add labelled accounts under `evals/datasets/` and run
   `python evals/run_evals.py --vertical <id> --labels ...`.
5. Set `VERTICAL=<id>`.

Do not put industry-specific ports, CPE logic, or ICP weights in `src/scoring.py`.

## Data safety

`data/b2_download_file_by_id` is ignored by git. V1 uses
`data/readable/shodan_100.jsonl`. Raw payloads never enter prompts or traces.

## Design

- `PLANNING.md` — user, use cases, ICP policy
- `ARCHITECTURE.md` — data profile, rule/LLM split, costs, verticals
- `skills/outreach-draft/SKILL.md` — reusable AI workflow
- `prompts/outreach_draft_v1.md` — cybersecurity prompt v1
- `HOW_I_BUILD.md` — development reflection
