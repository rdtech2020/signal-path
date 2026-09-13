# Architecture

**SignalPath** turns observational records into a ranked, explainable sales
queue. The engine (identity, account rollup, gating, tracing, outreach) is
vertical-agnostic. **Cybersecurity** is the first plugin: it scores
Shodan-style scan banners. Other motions add a YAML catalog plus a signal
extractor; they do not fork the app.

**Current scope: the 100-record cybersecurity sample only.** Every number in
§1 and §3 is measured on `data/readable/shodan_100_pretty.json` (n = 100).
Full-dump figures are labelled as projections.

---

## 1. The data

| Item | Value |
|---|---|
| Source dump | `data/b2_download_file_by_id` — single Zstd frame (XXH64), concatenated JSON objects |
| Dump size | 10.5 GiB compressed / **72.9 GiB** uncompressed |
| Dump population | **~10.3 million banners** (projected from 1.3M objects scanned at ~7–8 KB each; exact count needs a full 73 GiB decompress) |
| Working sample | `data/readable/shodan_100.jsonl`, `data/readable/shodan_100_pretty.json` — **n = 100** |
| Regenerate sample | `python3 scripts/convert_shodan_to_json.py --subset_size 100` |

The dump is never loaded whole: `scripts/convert_shodan_to_json.py` streams `zstd -d -c` and decodes objects incrementally.

**Grain: one JSON object = one banner** (one `ip_str` + `port` + service payload). It is not a firmographic company row. Sample scan window is a single ~40-second slice (`2026-09-07T06:59:27Z – 07:00:07Z`); `transport` is `tcp` on all 100.

### 1.1 Field coverage (n = 100)

| Field | Present | Sales use |
|---|---|---|
| `ip_str`, `port`, `org`, `isp`, `location` | 100 | Always available |
| `asn` | 93 | Territory / routing |
| `domains`, `hostnames` (non-empty) | **41** | Named account |
| `http` | 37 | Web stack, errors, WAF |
| `tags` | 36 | `cloud`, `cdn`, `vpn`, `eol-product`, `self-signed` |
| `product` | 34 | nginx, WinRM, PPTP, … |
| `cloud` | 23 | Hosting provider — **not** the buyer |
| `cpe` / `cpe23` | 20 | Software inventory |
| `ssl` | 9 | Cert / protocol posture |
| `ntlm` | 9 | Windows auth exposure |
| `pptp` | 4 | Legacy VPN |
| `os` (non-null) | 9 | Too sparse to rely on |

**59 of 100 banners have no domain or hostname.** One additional `domains` value is an IP with a trailing dot, and seven domains are provider-owned hostnames. Hyperscaler `org` is hosting, not an ICP: `Google LLC` alone accounts for 15 banners. Those are cloud IPs, not 15 prospects.

### 1.2 Signal base rates (n = 100)

Observed frequencies, which is what makes a weight defensible rather than invented.

| Observation | Count | Engineering note |
|---|---|---|
| Port outside `{80,443,8080,8443}` | 91 | Meaningless alone — most of the internet is not web |
| Port > 10000 | 27 | Tempting but arbitrary; **misses WinRM 5985 and PPTP 1723** |
| Port 5985 / `Microsoft HTTPAPI` | 9 | Public Windows remote admin |
| Port 1723 / `pptp` object | 4 | Legacy VPN, clean replacement pitch |
| `tags` has `cloud` (or `cloud` object) | 23 | Weak signal on its own |
| `tags` has `cdn` | 6 | **Downrank** — edge, not origin |
| `tags` has `vpn` | 4 | Category, not a score |
| `tags` has `eol-product` | **2** | Strong but rare; cannot carry the ICP |
| `tags` has `self-signed` | 2 | TLS hygiene |
| HTTP 404 | 12 of 37 | Parking / misconfig, not a leak |
| HTTP 400 | 6 of 37 | Weak at best |
| HTTP 5xx | 2 of 37 | Real ops pain |
| HTTP with no `http.waf` | 32 of 37 | Unshielded origin |
| `http.securitytxt` | **0** | Useless as a positive rule here |
| `ssl.cert.expired` | 1 of 9 SSL | Strong when `ssl` exists |
| `opts.heartbleed` present | 8 | Probe metadata only — `opts.vulns` was **empty on all 8** |
| Countries | US 39, CN 18, then DE/IL/BR/TW/GB | Territory filter belongs in the UI |

---

## 2. Pipeline

```
Zstd dump (~10.3M banners)          [prototype: 100-record sample]
        │  stream via zstd -d -c — never json.load the dump
        ▼
Ingest & normalize
  • decode concatenated JSON incrementally
  • drop rows without ip_str / port
        ▼
Account rollup  (banner → account)
  1. registrable domain from domains[] / hostnames[]
  2. else ip_str  (unnamed asset, low sales priority)
  • never use hyperscaler org as the account key
        ▼
Deterministic rule engine   (100% of accounts, $0 LLM)
  • versioned signal catalog + weights → icp_score 0–100
  • emits an explainable signal list per account
        ▼
        named domain AND icp_score >= gate AND daily cap left?
              no ──► store + dashboard only
              yes ─► outreach-draft skill (cheap model)
                        ▼
                  logs/traces.jsonl  (model, prompt_version, tokens, cost)
                        ▼
                  ranked account queue (UI / CSV export)
```

**Why roll up before scoring:** a salesperson works accounts, not banners. Scoring raw banners inflates noisy hosts and would present 15 Google-hosted IPs as 15 leads.

On n = 100 the rollup yields **85 accounts**: **25 syntactically named domains**, 60 IP-only, and **18 sales-addressable domains** after provider-owned hostnames are excluded. Only **3** accounts have more than one banner (max **14**). So on this sample the rollup mostly removes hyperscaler duplication rather than building rich multi-asset accounts — a bigger slice is needed before claiming account depth.

**Storage decision:** at 100 records, plain Python plus JSON is the correct tool; DuckDB/Parquet would be theatre. A columnar store (`banner_fact.parquet` + `account_score.parquet` queried by DuckDB) is only justified when we stream the full ~10.3M-banner dump. Keep scoring a pure function of a record so the same contract runs in Python tests today and in SQL later.

---

## 3. Rules vs LLM

| | Deterministic rules | LLM (`outreach-draft`) |
|---|---|---|
| Runs on | **Every** banner and account | Named-domain accounts past the gate, under a daily cap |
| Job | Ports, tags, CPE, HTTP status, TLS, NTLM/PPTP/WinRM, WAF absence, scoring | One CISO-facing brief + email, written **from the already-computed signals** |
| Cost | CPU only | Tokens — see §6 |
| Determinism | Required, for evals and sales audit | Temperature ≤ 0.2, JSON-schema output |
| Failure mode | Missed signal → fix rule, re-run free | Invented CVE → prevented by passing only `signals[]`, never raw banners |

**The LLM must not:** compute or override scores, invent CVEs, assert "end-of-life" unless `eol_software` is in the signal list, or treat the hosting `org` as the customer.

### 3.1 Signal catalog v1

Weights are a documented policy, not a fitted model. Score is clamped to 0–100.

| Code | Trigger | Weight |
|---|---|---|
| `exposed_winrm` | `port in (5985,5986)`, `product` contains WinRM, or HTTPAPI server | +30 |
| `eol_software` | `tags` has `eol-product` | +30 |
| `legacy_vpn` | `pptp` object, port 1723, or `tags` has `vpn` | +25 |
| `windows_auth_leak` | `ntlm` object present | +20 |
| `weak_tls` | `ssl.cert.expired`, `self-signed` tag, or TLSv1/1.1 offered | +20 |
| `origin_no_waf` | `http` present, `http.waf` null, not `cdn` | +10 |
| `http_server_error` | `http.status` in 5xx | +10 |
| `identified_cpe` | `cpe` non-empty | +5 |
| `cdn_edge` | `tags` has `cdn` | **−15** |
| `hyperscaler_unnamed` | no domain **and** hyperscaler `org` | **−20** |
| `hosted_platform_domain` | provider-owned hostname such as `amazonaws.com` | **−20** |

**Deliberately rejected:** "port > 10000" (+25) and "any cloud footprint" (+20). Both fire on a quarter of the sample, dominate the score, and do not mean the company needs security software. Uncommon ports may return later as a low-weight secondary flag once a port denylist exists.

### 3.2 Measured distribution of v1 (n = 100 → 85 accounts)

| | Value |
|---|---|
| Mean score | **12.1** |
| Max score | **60** |
| Zero-score accounts | 43 of 85 |

| Gate | Accounts ≥ gate | Of those, named |
|---|---|---|
| ≥ 20 | 17 (20%) | 5 addressable |
| ≥ 30 | 11 (13%) | 4 addressable |
| ≥ 40 | **11 (13%)** | **4 addressable** |
| ≥ 50 | 8 (9%) | 3 addressable |
| ≥ 60 | 7 (8%) | 2 addressable |

Account-level signal frequency: `origin_no_waf` 32, `identified_cpe` 20, `exposed_winrm` 10, `windows_auth_leak` 9, `hyperscaler_unnamed` 9, `hosted_platform_domain` 7, `cdn_edge` 5, `legacy_vpn` 4, `weak_tls` 3, `eol_software` 2, `http_server_error` 2.

**Gate v1 = sales-addressable domain AND `icp_score >= 40`.** On this sample that is **4 accounts**, which is the right order of magnitude for a demo queue and keeps LLM spend near zero. A `>= 60` gate is not used, because it would leave only 2 addressable accounts.

**Weakness this exposes immediately:** all 7 accounts scoring 60 carry the *identical* triplet `exposed_winrm + windows_auth_leak + origin_no_waf`. A queue would show near-duplicate leads. Signal-pattern deduplication (or capping one lead per `org`/ASN per pattern) is required before this is usable by a human.

---

## 4. Observability

One JSONL line per LLM call in `logs/traces.jsonl`. Rules are **not** traced per banner (that would be ~10M rows); the persisted `account_score` output is the audit record.

```json
{
  "trace_id": "tr_01j9c3k4n5",
  "timestamp": "2026-09-12T22:43:09Z",
  "prompt_version": "outreach_draft_v1",
  "skill_name": "outreach-draft",
  "model": "gpt-4o-mini",
  "account_id": "domain:example.com",
  "icp_score": 60,
  "signals": ["exposed_winrm", "windows_auth_leak", "origin_no_waf"],
  "latency_ms": 482,
  "prompt_tokens": 420,
  "completion_tokens": 180,
  "total_cost_usd": 0.000171,
  "output_status": "success",
  "validation_passed": true
}
```

`request` and `response` are mandatory but redacted: the request contains only account name, country, score, ports, and deterministic signals; the response is the validated outreach object. `prompt_version`, `model`, `signals`, `icp_score`, token counts and cost are also mandatory, since v1-vs-v2 comparison is computed from them. **Never** log `http.html`, `ssl.chain`, `http.favicon.data`, or the raw `data` banner — that is third-party content and it bloats the log.

---

## 5. Repository layout

| Path | Role | Status |
|---|---|---|
| `scripts/convert_shodan_to_json.py` | Streams the Zstd dump into readable JSON/JSONL samples | **built** |
| `data/readable/shodan_100*.json*` | n = 100 working sample | **built** |
| `ARCHITECTURE.md` | This document | **built** |
| `config/verticals/cybersecurity.yaml` | Cybersecurity weights, gate, identity denylists | **built** |
| `src/scoring.py` | Vertical-agnostic rollup and scoring | **built** |
| `src/verticals/cybersecurity.py` | Scan-banner signal extractor | **built** |
| `skills/outreach-draft/SKILL.md` | Trigger, inputs (`account` + `signals` only), output schema, worked example | **built** |
| `prompts/outreach_draft_v1.md` | Versioned prompt; v2 is a new file, never a silent edit | **built** |
| `evals/` | 25 labelled accounts + one-command deterministic harness | **baseline built; human label review and live LLM eval pending** |
| `PLANNING.md` | Chosen use cases and why | **built** |
| `HOW_I_BUILD.md` | Dev-loop reflection | **built** |
| `app.py` | Ranked **account** queue with score, signals, country, ports, draft button | **built** |

The eval set is drawn from this sample. Its 25 accounts include 5 manually reviewed `should_contact` positives and 20 negatives. The deterministic baseline measures contact precision **1.00**, recall **0.80**, F1 **0.889**, and signal-code F1 **1.00**. The missed positive is `estpak.ee`: a legacy VPN signal scores 25, below the gate of 40. These are baseline policy labels; the repository owner must review them before presenting them as a final golden set. A live LLM-output eval is still required once an API key is configured.

---

## 6. Cost model

**Rules cost $0 in tokens.** They run over 100% of banners; the only cost is CPU and the one-time 73 GiB stream.

LLM spend is controlled by a **budget cap, not a percentile**. Percentile gating on a 10.3M-banner dump is how a prototype turns into a four-figure invoice.

Per-draft token estimate (signals + a short banner summary, never raw HTML): **~420 input / ~180 output**. This is an estimate — no LLM calls have been made yet, so `logs/traces.jsonl` does not exist and no measured cost is claimed.

Model split: cheap model (`gpt-4o-mini`-class, $0.150/1M in, $0.600/1M out — verify at ship time) for drafting and classification; a stronger model is only worth it for judgement tasks, and nothing in this pipeline currently needs one.

```
cost_per_draft = (420/1e6 * 0.150) + (180/1e6 * 0.600)
               = 0.000063 + 0.000108
               = $0.000171
```

| Scenario | Drafts | LLM cost |
|---|---|---|
| Current sample (gate ≥ 40, addressable) | 4 | **$0.0007** |
| Demo cap: 500 drafts/day, 30 days | 15,000 | **~$2.57 / month** |
| Rejected: naive 10% of 10.3M banners | 1,030,000 | ~$176 per dump pass |

**Production ceiling: $25 / month**, alerting at 50% and 80%. When volume grows, hold the dollar ceiling and drop the lowest-scoring accounts from the queue — never widen the gate to unnamed IPs.

---

## 7. Known weaknesses

1. **n = 100 from a 40-second scan window.** Port mix (WinRM 5985, 9998, PPTP) is not proven representative of 10.3M banners. Weights are provisional until validated on a larger slice.
2. **No exact record count** for the dump; ~10.3M is a projection.
3. **59% of banners have no hostname/domain**, and after an IP-like domain is corrected, 60 of 85 accounts are IP-only. Of the 25 syntactic domains, only 18 are sales-addressable after provider hostnames are removed.
4. **Near-duplicate high scorers** (§3.2) — deduplication is required before a human uses the queue.
5. **`opts.vulns` was empty on all 8 records that had it.** Do not build a CVE feature on this field yet.
6. **EOL appears on only 2%.** The genuine signal in this dump is *protocol and admin-surface exposure* (WinRM, NTLM, PPTP, unshielded origin), not an EOL epidemic.
7. **Sensitive content.** Banners carry third-party HTML, certificates, NTLM data and favicons. They stay out of git, out of traces, and out of prompts apart from a truncated title/server header.
8. **Not yet a git repository.** `.gitignore` now excludes the 10 GB dump and runtime traces, but that protection starts only after git is initialized.

---

## 8. Build order

1. Have a human review the 25 provisional account labels and resolve the `legacy_vpn` gate miss.
2. Add signal-pattern dedup so identical-fingerprint accounts collapse.
3. Add a live, schema- and claim-grounding eval for `outreach_draft_v1`.
4. Deploy the ranked account queue and collect measured latency/token traces.
5. Only then consider streaming the full dump into Parquet; the demo must not depend on a 73 GiB expansion.

---

## 9. Adding a vertical

Keep industry logic out of the engine.

| Layer | Stays generic | Lives in the vertical |
|---|---|---|
| Identity | domain / hostname / IP | denylist of provider hostnames |
| Rollup | one score per account | — |
| Signals | identity-quality flags | ICP catalog (`extract_record_signals`) |
| Gate + cost | daily cap, trace schema | `llm_gate_score`, `prompt_path` |
| Evals | harness | labelled set for that motion |

Activate with `VERTICAL=<id>`. Do not add a second live vertical until the
cybersecurity labels have been reviewed.
