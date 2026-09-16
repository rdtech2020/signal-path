# SignalPath

Turn raw internet-exposure telemetry into a ranked, explainable sales queue.

A seller opening this app should be able to answer one question in seconds:
**which attributable company has a concrete, defensible reason to talk today?**

Cybersecurity is the first vertical, not the product. A **vertical** is a sales
motion with its own signal catalog, weights, attribution rules, eval set, and
prompt. The engine — identity, rollup, gating, tracing, outreach — stays the
same.

**Live app:** [https://signal-path-icp-score.streamlit.app/](https://signal-path-icp-score.streamlit.app/)

## What is in the box


| Piece                                                    | What it is                                                                | Why it matters                                                                               |
| -------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `scripts/build_duckdb.py`                                | Streams the compressed scan archive into DuckDB under fixed resource caps | Turns 10.5 GiB of compressed JSON into a queryable store without ever writing 73 GiB of text |
| `src/identity.py`                                        | Public-IP and public-apex-domain sanitization                             | A queue containing `localhost` or `10.0.0.7` destroys seller trust and sender reputation     |
| `src/scoring.py` + `config/verticals/cybersecurity.yaml` | Deterministic account rollup and weighted ICP score                       | Every number is reconstructable from config, so sales can audit a rank                       |
| `src/duckdb_store.py`                                    | SQL rollup and paged queue queries                                        | The dashboard reads one page at a time, never 10M banners                                    |
| `src/store_fetch.py` + `scripts/export_serving_store.py` | Ships a 46 MiB store to a hosted container                                | A host cannot rebuild from a 10.5 GiB archive, so it downloads a serving copy of the result  |
| `src/brief.py`                                           | Turns an account into a sales brief                                       | 34 open ports is telemetry; two cited ports plus a count is a reason to call                 |
| `skills/outreach-draft/SKILL.md`                         | Reusable, versioned AI workflow                                           | Any agent can load the same trigger, inputs, and output contract                             |
| `prompts/outreach_draft_v*.md`                           | Versioned prompt files                                                    | A new version is a new file, so past traces stay interpretable                               |
| `src/llm_client.py` + `src/tracer.py`                    | Schema-validated generation with budget gates and JSONL tracing           | Cost, latency, and claims are measurable per call                                            |
| `evals/`                                                 | 31 labelled accounts, 46 fixture banners, one-command harness             | Scoring changes are measured, not asserted                                                   |
| `app.py`                                                 | Streamlit queue with score, signals, territory, and draft button          | The product surface a seller actually uses                                                   |




## Current dataset in the store

Measured from `data/signal_path.duckdb`:


| Metric                     | Value      |
| -------------------------- | ---------- |
| Banners ingested           | 10,046,794 |
| Accounts after rollup      | 1,585,994  |
| Named accounts             | 203,021    |
| Sales-addressable accounts | 201,397    |
| Score ≥ 40 and addressable | 27,707     |
| Score ≥ 80 and addressable | 2,102      |
| Countries represented      | 229        |
| Store size                 | 497 MB     |




## Quick start

```bash
python3 -m venv .venv
 
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

Defaults are deliberately conservative so a laptop stays usable during the
roughly twenty-minute full load:

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
SELECT account_name, icp_score, signal_codes, signal_details, country_code
FROM account_score
WHERE is_addressable AND icp_score >= 80
ORDER BY icp_score DESC
LIMIT 100;
```



## Verify

```bash
ruff check .
pytest
python evals/run_evals.py
```

`pytest` covers identity sanitization, scoring, the Python/SQL parity contract
(including signal detail text), port summarization, tracing, and the dashboard.

The eval harness writes `evals/results/latest.json`, which reports signal
extraction metrics plus a contact-policy sweep across candidate gates. Signal
extraction is the regression gate; the sweep exists because the outreach gate is
a business trade-off, and `ARCHITECTURE.md` §6 explains what the current curve
says about it.

The labelled set spans both sides of that gate on purpose. Candidates for
labelling are pulled from the archive with:

```bash
python scripts/sample_eval_banners.py --output /tmp/candidates.jsonl \
  --minimum_score 80 --wanted 6
```

Labels themselves are written by hand — the question is whether a seller would
spend a touch on the account, never whether the score cleared the gate.

## Deploy

The live queue is at
[https://signal-path-icp-score.streamlit.app/](https://signal-path-icp-score.streamlit.app/).

A hosted container cannot build the store — that needs the 10.5 GiB archive and
about twenty minutes — so the store is built once locally and supplied to the
deployment. It is never baked into the image or committed, because it is derived
data.

**Container, with the store mounted:**

```bash
docker build -t signal-path .
docker run -p 8501:8501 \
  -v "$PWD/data/signal_path.duckdb:/app/data/signal_path.duckdb" \
  -e OPENAI_API_KEY signal-path
```

**Streamlit Community Cloud**, or anywhere without persistent storage. Export a
serving-only store, upload it, and let the app fetch it on first run:

```bash
python scripts/export_serving_store.py            # 474 MiB -> 70 MiB
gzip -kf data/signal_path_serving.duckdb          # 70 MiB  -> 46 MiB
# upload data/signal_path_serving.duckdb.gz somewhere readable over HTTPS
```

The export keeps every one of the 1,585,994 accounts. It drops `banner_fact`,
which is 85% of the built store and is read by the app only for the corpus
banner count — that count is materialized into a small `store_summary` table
instead, so the dashboard still reports the full 10,046,794 banners.

Then set these as secrets (Streamlit exposes secrets as environment variables):

```
DATABASE_URL = "https://.../signal_path_serving.duckdb.gz"
OPENAI_API_KEY = "..."
```

On first run the app streams that file into its ephemeral disk, shows download
progress, checks the expected tables are present, and only then renames it into
place — a partial download can never be mistaken for a store. The result is
cached for the life of the container, so later reruns are instant. A `.gz` URL
is decompressed while downloading; a plain `.duckdb` URL also works.

`requirements.txt` exists so hosts install with pip. Without it, a host that
finds only `pyproject.toml` tries Poetry, which attempts to install this
repository as a package named `signal-path` and fails — the code lives in `src/`
and `config/`, not in a `signal_path/` package.

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
- `prompts/outreach_draft_v2.md` — active outreach prompt (`v1` kept for comparison)

