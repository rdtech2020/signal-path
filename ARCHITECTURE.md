# Architecture

SignalPath converts internet-exposure telemetry into a ranked, explainable
account queue. The engine — identity, rollup, scoring, gating, tracing, outreach
— is vertical-agnostic. **Cybersecurity** is the first plugin: a YAML signal
catalog plus a record-level extractor. A new sales motion adds those two files;
it does not fork the app.

Serving reads one artifact: `data/signal_path.duckdb`.

---

## 1. Component map

```
compressed scan archive (10.5 GiB zstd, 72.9 GiB of JSON)
        │  streamed via `zstd -d -c`; raw JSON never lands on disk
        ▼
ingest + normalize            src/ingester.py
  • strip data, http.html, http.favicon, ssl.chain, ssl.cert
  • drop records without ip_str / port
        ▼
identity sanitization         src/identity.py
  • public routable IP only (no loopback, RFC1918, link-local, IMDS)
  • public apex domain only (dot required, placeholders/honeypots rejected)
        ▼
signal extraction             src/verticals/cybersecurity.py
  • one boolean column per catalog code
        ▼
banner_fact (DuckDB)          src/duckdb_store.py
        │  GROUP BY account_id — SQL, not Python loops
        ▼
account_score (DuckDB)
  • icp_score = clamp(Σ weight × flag, 0, 100)
  • signal_codes[], ports[], ip_addresses[], country, org, banner_count
        ▼
        addressable AND icp_score ≥ gate AND budget left?
              no ──► queue and dashboard only          ($0)
              yes ─► outreach-draft skill (cheap model)
                        ▼
                  logs/traces.jsonl — model, prompt version, tokens, cost
                        ▼
        ranked queue in app.py (bounded to 100 rows per view)
```

---

## 2. The data

| Item | Value |
|---|---|
| Source | Single Zstd frame (XXH64) of concatenated JSON objects |
| Size | 10.5 GiB compressed / 72.9 GiB uncompressed |
| Banners ingested | 10,046,794 |
| Serving store | `data/signal_path.duckdb` (432 MB) — `banner_fact` + `account_score` |
| Full build time | ~10 minutes under the default resource caps |

**Grain: one JSON object is one banner** — one `ip_str`, one `port`, one service
payload. It is not a company row. That single fact is why account rollup happens
before scoring.

### 2.1 What set the v1 weights

Weights were derived from a hand-reviewed 100-banner profiling slice before the
full load, because base rates are what make a weight defensible rather than
invented. That slice was a single ~40-second scan window, so it justifies the
*shape* of the catalog, not final calibration.

| Observation in the profiling slice | Count | Engineering read |
|---|---|---|
| No domain or hostname | 59 of 100 | Attribution, not detection, is the bottleneck |
| Port outside `{80,443,8080,8443}` | 91 | Meaningless alone — most of the internet is not web |
| Port > 10000 | 27 | Arbitrary, and it misses WinRM 5985 and PPTP 1723 |
| Port 5985 / `Microsoft HTTPAPI` | 9 | Public Windows remote administration |
| Port 1723 / `pptp` object | 4 | Legacy VPN, clean replacement pitch |
| `tags` has `cloud` | 23 | Describes hosting, not a buyer |
| `tags` has `cdn` | 6 | Downrank — edge, not origin |
| `tags` has `eol-product` | 2 | Strong but rare; cannot carry the ICP |
| HTTP present with no `http.waf` | 32 of 37 | Unshielded origin |
| HTTP 5xx | 2 of 37 | Real operational pain |
| `ssl.cert.expired` | 1 of 9 with SSL | Strong when TLS data exists |
| `opts.vulns` populated | 0 of 8 with `opts.heartbleed` | No CVE feature can be built on this |
| `http.securitytxt` | 0 | Useless as a positive rule here |

`Google LLC` alone accounted for 15 banners in that slice. Those are cloud IPs,
not 15 prospects — the origin of the `hyperscaler_unnamed` penalty.

### 2.2 Measured at full scale

| Metric | Value |
|---|---|
| Accounts after rollup | 1,585,994 |
| Named accounts | 203,021 |
| Sales-addressable accounts | 201,397 |
| Mean score | 7.19 |
| Max score | 100 |
| Addressable and ≥ 40 | 27,707 |
| Addressable and ≥ 60 | 11,700 |
| Addressable and ≥ 80 | 2,102 |
| Countries | 229 |

Signal frequency across accounts: `origin_no_waf` 521,915 · `identified_cpe`
482,698 · `hyperscaler_unnamed` 349,209 · `cdn_edge` 204,608 · `exposed_winrm`
64,612 · `weak_tls` 57,054 · `windows_auth_leak` 51,860 · `http_server_error`
42,949 · `eol_software` 28,755 · `legacy_vpn` 24,056 · `hosted_platform_domain`
8.

The scale run confirms the profiling read: the genuine signal in this data is
**protocol and administration-surface exposure**, not an end-of-life epidemic.

---

## 3. Key design decisions

### 3.1 Roll up to accounts before scoring

A seller works accounts, not banners. Scoring raw banners inflates noisy hosts
and would present one hyperscaler's IPs as many separate leads. Rollup key
priority: registrable domain from `domains[]`, then `hostnames[]`, then the IP
as an explicitly unnamed asset. A hosting `org` is never the account key.

### 3.2 DuckDB is the execution engine; YAML is the policy

At a hundred records, plain Python was the right tool. At ten million, a
columnar store is the only way to answer "addressable, score ≥ 80, country = US"
without touching every nested JSON field.

The split that keeps this honest: **weights and gates live in YAML, and both
engines read them.** Python scores a record for tests and evals; generated SQL
scores the archive. A parity test asserts the two produce identical
`icp_score`, `is_addressable`, and signal sets, so SQL can never silently drift
from the audited contract.

The archive is streamed, never expanded. Ingest is the only full pass; serving
queries hit typed columns in a 432 MB store.

### 3.3 Sanitization belongs at identity time

A commercial queue that contains `localhost`, `10.0.0.7`, `169.254.169.254`, or
`WORKSTATION1` is worse than an empty queue: it burns seller time and sender
reputation. `src/identity.py` enforces, in both engines:

- globally routable IPs only — loopback, RFC 1918, link-local and cloud metadata
  endpoints are dropped at ingest
- public apex domains only — a dot is required, so NetBIOS names are rejected
- placeholder names (`unknown`, `null`, `none`, `test`, `-`) rejected
- non-public suffixes (`.local`, `.arpa`, `.internal`, RFC 2606) rejected
- known honeypot and sinkhole suffixes rejected
- provider tenant hostnames kept but marked unaddressable

Rules live in the vertical config, so a new motion tunes them without code.

### 3.4 Resource caps are part of the design

A full load that swaps a laptop is not a working pipeline. Ingest holds at most
one 5,000-row batch in Python, caps DuckDB at 4 GB and 2 threads, bounds spill
at 20 GB, and refuses to start below 15 GiB free disk. The parser fails loudly
on a record larger than 128 MiB rather than silently skipping source data.

---

## 4. Rules versus LLM

| | Deterministic rules | LLM (`outreach-draft`) |
|---|---|---|
| Runs on | Every banner and every account | Addressable accounts past the gate, under a daily cap |
| Job | Ports, tags, CPE, HTTP status, TLS, NTLM/PPTP/WinRM, WAF absence, identity, scoring | One short, evidence-grounded email from already-computed signals |
| Cost | CPU only | Tokens — see §7 |
| Determinism | Required, for audit and evals | Structured output validated against a Pydantic schema |
| Failure mode | Missed signal → fix the rule, re-run for free | Invented claim → prevented by passing only `signals[]`, never raw banners |

**The model must not** compute or override a score, invent a CVE or breach,
assert end-of-life unless `eol_software` fired, or treat a hosting `org` as the
customer.

### 4.1 Signal catalog v1

Weights are documented policy, not a fitted model. Score is clamped to 0–100.

| Code | Trigger | Weight |
|---|---|---|
| `exposed_winrm` | port 5985/5986, `product` contains WinRM, or HTTPAPI server | +30 |
| `eol_software` | `tags` has `eol-product` | +30 |
| `legacy_vpn` | `pptp` object, port 1723, or `tags` has `vpn` | +25 |
| `windows_auth_leak` | `ntlm` object present | +20 |
| `weak_tls` | expired cert, `self-signed` tag, or TLSv1/1.1 offered | +20 |
| `origin_no_waf` | `http` present, no `http.waf`, not `cdn` | +10 |
| `http_server_error` | `http.status` is 5xx | +10 |
| `identified_cpe` | `cpe` non-empty | +5 |
| `cdn_edge` | `tags` has `cdn` | −15 |
| `hyperscaler_unnamed` | no domain and hyperscaler `org` | −20 |
| `hosted_platform_domain` | provider-owned hostname such as `amazonaws.com` | −20 |

**Deliberately rejected:** `port > 10000` (+25) and "any cloud footprint" (+20).
Both fire on roughly a quarter of records, dominate the score, and do not mean a
company needs security software. Uncommon ports may return later as a low-weight
secondary flag once a port denylist exists.

### 4.2 Gate

Gate v1 is **addressable AND `icp_score ≥ 80`**, with a cap of 100 drafts per
day. At full scale that is 2,102 candidate accounts — a deep enough bench for a
sales team while keeping spend near zero. The gate is a config value, not a
percentile: percentile gating over ten million records is how a prototype turns
into a four-figure invoice.

---

## 5. Observability

One JSONL line per LLM call in `logs/traces.jsonl`. Rule evaluation is not
traced per banner — that would be ten million rows — the persisted
`account_score` row is the audit record instead.

```json
{
  "trace_id": "tr_c0643904d6de4b31b5087880cfc23e71",
  "timestamp": "2026-09-15T17:57:01.524627+00:00",
  "skill_name": "outreach-draft",
  "prompt_version": "outreach_draft_v1",
  "model": "gpt-4o-mini",
  "vertical": "cybersecurity",
  "decision": "draft_outreach",
  "account_id": "domain:182-airtel.com",
  "icp_score": 100,
  "signals": ["eol_software", "exposed_winrm", "http_server_error", "identified_cpe", "origin_no_waf", "weak_tls", "windows_auth_leak"],
  "request": { "account_name": "…", "country_code": "IN", "icp_score": 100, "ports": [], "signals": [] },
  "response": { "subject": "…", "opening": "…", "evidence": [], "call_to_action": "…", "confidence": "medium" },
  "latency_ms": 6190,
  "prompt_tokens": 606,
  "completion_tokens": 74,
  "total_cost_usd": 0.0001353,
  "output_status": "success",
  "validation_passed": true
}
```

`src/tracer.py` writes through an allowlist, so an unknown field is discarded
rather than leaked. `request` carries only account name, country, score, ports,
and deterministic signals; `response` is the validated draft object. Raw
`data`, `http.html`, `ssl.chain`, and favicon bytes never reach the log — that
is third-party content and it would bloat the file.

Because `prompt_version`, `model`, tokens, and cost are mandatory, a v1-to-v2
prompt comparison is a query over this file rather than a new instrumentation
project.

---

## 6. Evaluation

`python evals/run_evals.py` scores 25 hand-labelled accounts from 40 fixture
banners and writes `evals/results/latest.json`. Two metrics are reported:

- **Signal extraction** — did the rules find exactly the expected signal codes?
  Currently precision 1.00, recall 1.00, F1 1.00 across 45 signal decisions.
  CI fails if this regresses.
- **Contact policy** — would the account be queued for outreach? This compares
  labels against the live gate, so it moves whenever gate policy moves.

The harness exits non-zero only on signal-extraction regression. Contact-policy
disagreement is surfaced rather than enforced, because the gate is a business
lever that is expected to be re-tuned.

`pytest` (14 tests) covers identity sanitization, rollup and scoring,
Python/SQL parity, private-IP rejection at ingest, tracing redaction, and the
dashboard.

---

## 7. Cost model

Rules cost zero tokens. They run over 100% of banners; the only cost is CPU and
the one-time archive stream.

Measured from real traces (`gpt-4o-mini`, $0.150/1M input, $0.600/1M output):

```
mean input  652 tokens
mean output  78 tokens

cost_per_draft = (652/1e6 × 0.150) + (78/1e6 × 0.600)
               = 0.0000978 + 0.0000468
               = $0.000145
```

Observed latency is 5.0–6.3 s per draft, and three completed drafts cost
$0.00043 in total.

| Scenario | Drafts | LLM cost |
|---|---|---|
| Daily cap (100/day) | 3,000 / month | **~$0.43 / month** |
| Draft every account at gate ≥ 80 once | 2,102 | **~$0.30** |
| Rejected: naive 10% of all banners | 1,004,679 | ~$145 per pass |

Model choice per task: a cheap model drafts and classifies; nothing in this
pipeline currently needs a stronger reasoning model, because judgement lives in
the deterministic catalog. **Production ceiling: $25/month**, alerting at 50%
and 80%. When volume grows, hold the dollar ceiling and drop the lowest-scoring
accounts — never widen the gate to unattributable IPs.

Budget enforcement is code, not documentation: `src/llm_client.py` checks the
monthly spend and the daily draft count from the trace log *before* calling the
API.

---

## 8. Known weaknesses

1. **Contact-policy evals are stale against the current gate.** The 25 labels
   were written when the gate was 40; the gate is now 80, so every labelled
   positive now reads as a miss. The labels need re-review against the live
   policy before contact precision/recall is quoted.
2. **Signal detail text is lost on the SQL path.** `account_score` stores signal
   *codes*, so the app reconstructs details as "Detected by deterministic rule:
   <code>". The model therefore receives weaker evidence than the Python
   extractor produces, and drafts read generically. Persisting detail strings is
   the highest-value fix for draft quality.
3. **Briefs carry too many ports.** Some accounts pass 30+ ports into the
   prompt. That is telemetry, not a sales brief; ports should be summarized.
4. **Near-duplicate high scorers.** Many top accounts share an identical signal
   fingerprint. Signal-pattern deduplication, or one lead per org/ASN per
   pattern, is required before a human works the list end to end.
5. **Attribution remains the ceiling.** 1.38M of 1.59M accounts are IP-only.
   Reliable company enrichment is needed before this is a primary lead source.
6. **No output-quality eval for generated drafts.** Structure is validated and
   claims are constrained by construction, but claim-grounding is not yet
   measured against labelled examples.
7. **Weights are provisional.** The base rates that shaped them came from a
   single short scan window; the full load supports their direction but has not
   been used to recalibrate them.
8. **One archive, one moment.** This is a point-in-time scan. Exposure change
   over time — a much stronger buying signal — needs a second snapshot.

---

## 9. Roadmap

1. Re-review the 25 labels against the current gate and restore a defensible
   contact precision/recall figure.
2. Persist signal detail strings through to `account_score` and summarize ports,
   then re-measure draft quality.
3. Add a claim-grounding eval for `outreach_draft_v1`, and use it to justify a
   v2 prompt file.
4. Collapse duplicate signal fingerprints in the queue.
5. Ingest a second snapshot and add change-over-time signals.

---

## 10. Adding a vertical

Industry logic stays out of the engine.

| Layer | Stays generic | Lives in the vertical |
|---|---|---|
| Identity | domain / hostname / IP, public-routability rules | provider and honeypot denylists |
| Rollup | one score per account | — |
| Signals | identity-quality flags | ICP catalog via `extract_record_signals` |
| Gate and cost | daily cap, budget check, trace schema | `llm_gate_score`, `prompt_path` |
| Evals | harness and metrics | labelled set for that motion |

Activate with `VERTICAL=<id>`. A second live vertical should wait until the
cybersecurity labels are reconciled with the current gate.
