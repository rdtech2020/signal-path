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

## Build the full-data DuckDB

The full dump is streamed directly from zstd into a stripped `banner_fact`
table. Raw HTML, certificate chains, favicons, and banner payloads are never
stored. Account scores are materialized from the active vertical's YAML
weights, so application queries do not rescan the archive.

```bash
python scripts/build_duckdb.py
```

Resource-safe defaults are deliberately conservative:

- 2 DuckDB worker threads
- 4 GB DuckDB memory limit
- 5,000 banners per Python ingestion batch
- 20 GB maximum temporary spill
- refuse to start with less than 15 GiB free disk

Override them only after measuring the machine:

```bash
python scripts/build_duckdb.py \
  --threads 4 \
  --memory_limit 8GB \
  --max_temp_size 20GB \
  --min_free_gib 15
```

For a safe parity run before processing the full archive:

```bash
python scripts/build_duckdb.py \
  --source data/readable/shodan_100.jsonl \
  --database data/signal_path_sample.duckdb \
  --jsonl
```

Query only the materialized account table:

```sql
SELECT account_name, icp_score, signal_codes
FROM account_score
WHERE is_addressable AND icp_score >= 40
ORDER BY icp_score DESC
LIMIT 500;
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
