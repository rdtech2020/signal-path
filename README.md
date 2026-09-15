# SignalPath

Turn raw internet-exposure telemetry into a ranked, explainable sales queue.

A seller opening this app should be able to answer one question in seconds:
**which attributable company has a concrete, defensible reason to talk today?**

Cybersecurity is the first vertical, not the product. A **vertical** is a sales
motion with its own signal catalog, weights, attribution rules, eval set, and
prompt. The engine — identity, rollup, gating, tracing, outreach — stays the
same.

## What is in the box

| Piece | What it is | Why it matters |
|---|---|---|
| `scripts/build_duckdb.py` | Streams the compressed scan archive into DuckDB under fixed resource caps | Turns 10.5 GiB of compressed JSON into a queryable store without ever writing 73 GiB of text |
| `src/identity.py` | Public-IP and public-apex-domain sanitization | A queue containing `localhost` or `10.0.0.7` destroys seller trust and sender reputation |
| `src/scoring.py` + `config/verticals/cybersecurity.yaml` | Deterministic account rollup and weighted ICP score | Every number is reconstructable from config, so sales can audit a rank |
| `src/duckdb_store.py` | SQL rollup and bounded queue queries | The dashboard reads 500 rows, never 10M banners |
| `skills/outreach-draft/SKILL.md` | Reusable, versioned AI workflow | Any agent can load the same trigger, inputs, and output contract |
| `prompts/outreach_draft_v1.md` | Versioned prompt file | v2 becomes a new file, so drafts stay comparable |
| `src/llm_client.py` + `src/tracer.py` | Schema-validated generation with budget gates and JSONL tracing | Cost, latency, and claims are measurable per call |
| `evals/` | 25 labelled accounts, 40 fixture banners, one-command harness | Scoring changes are measured, not asserted |
| `app.py` | Streamlit queue with score, signals, territory, and draft button | The product surface a seller actually uses |

## Current dataset in the store

Measured from `data/signal_path.duckdb`:

| Metric | Value |
|---|---|
| Banners ingested | 10,046,794 |
| Accounts after rollup | 1,585,994 |
| Named accounts | 203,021 |
| Sales-addressable accounts | 201,397 |
| Score ≥ 40 and addressable | 27,707 |
| Score ≥ 80 and addressable | 2,102 |
| Countries represented | 229 |
| Store size | 432 MB |

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/build_duckdb.py
streamlit run app.py
```

The app reads `data/signal_path.duckdb` only, and stops with a clear message if
that store is missing. The ranked queue works without an API key. Outreach
drafting needs one:

```bash
cp .env.example .env
export OPENAI_API_KEY="..."
```

## Build the store

The archive is streamed straight from zstd into a stripped `banner_fact` table.
Raw HTML, certificate chains, favicons, and banner payloads are dropped at
ingest. Account scores are then materialized from the active vertical's YAML
weights, so serving queries never rescan the archive.

```bash
python scripts/build_duckdb.py
```

Defaults are deliberately conservative so a laptop stays usable during a
ten-minute full load:

- 2 DuckDB worker threads
- 4 GB DuckDB memory limit
- 5,000 banners per ingestion batch
- 20 GB maximum temporary spill
- refuses to start with less than 15 GiB free disk

Raise them only after measuring the machine:

```bash
python scripts/build_duckdb.py \
  --threads 4 \
  --memory_limit 8GB \
  --max_temp_size 20GB \
  --min_free_gib 15
```

After changing identity or sanitization rules, recompute eligibility in about a
minute instead of rebuilding:

```bash
python scripts/refresh_eligibility.py
```

## Query the queue directly

Serving reads only the materialized account table:

```sql
SELECT account_name, icp_score, signal_codes, country_code
FROM account_score
WHERE is_addressable AND icp_score >= 80
ORDER BY icp_score DESC
LIMIT 500;
```

## Verify

```bash
ruff check .
pytest
python evals/run_evals.py
```

`pytest` covers identity sanitization, scoring, the Python/SQL parity contract,
tracing, and the dashboard. The eval harness writes `evals/results/latest.json`
so successive prompt and weight versions stay comparable.

## Deploy

```bash
docker build -t signal-path .
docker run -p 8501:8501 \
  -v "$PWD/data/signal_path.duckdb:/app/data/signal_path.duckdb" \
  -e OPENAI_API_KEY signal-path
```

The store is mounted rather than baked into the image: it is derived data, and
the raw archive must never ship inside a container.

## Add another sales motion

1. `config/verticals/<id>.yaml` — weights, gate, prompt path, identity denylists.
2. `src/verticals/<id>.py` — `extract_record_signals(record, rules)`.
3. Register it in `src/verticals/__init__.py` (`EXTRACTORS`).
4. Add labelled accounts under `evals/datasets/` and run
   `python evals/run_evals.py --vertical <id> --labels ...`.
5. Set `VERTICAL=<id>`.

Industry-specific ports, CPE logic, and ICP weights do not belong in
`src/scoring.py`.

## Data safety

The raw archive and the generated store are both git-ignored. Third-party
payloads are stripped at ingest, so they cannot reach prompts, traces, or the
dashboard.

## Documents

- `PLANNING.md` — user, decision, use cases, ICP policy
- `ARCHITECTURE.md` — data profile, rule/LLM split, cost model, weaknesses
- `HOW_I_BUILD.md` — development loop and what it cost
- `skills/outreach-draft/SKILL.md` — the reusable AI workflow
- `prompts/outreach_draft_v1.md` — cybersecurity outreach prompt v1
