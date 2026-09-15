# Product Plan

**Product:** SignalPath — observational data in, ranked account queue out.

V1 ships the **cybersecurity** vertical. The same engine is meant to host later
motions (for example payroll, payments, or IT operations) by swapping signal
catalogs, not by forking the app.

## User and decision

The primary user is a seller preparing a daily account queue. Their decision is
not “which raw record looks unusual?” but “which attributable company has a
concrete, defensible reason to talk today?”

For cybersecurity that reason is attack-surface evidence. Another vertical would
substitute its own buying signals and keep the same queue, gate, and outreach
contract.

## V1 use cases (cybersecurity)

1. **Prioritise named accounts** by externally observed risk signals.
2. **Filter territory** by country and inspect exposed ports.
3. **Explain every score** with deterministic evidence.
4. **Draft outreach** only for high-priority, attributable accounts.

## Why these use cases

The source is banner telemetry, not firmographics. Most banners have no
attributable company domain; the useful wedge is attack-surface evidence on
named, public, sales-addressable accounts.

## ICP policy (cybersecurity)

Named accounts with direct administration, authentication, legacy VPN, EOL, or
TLS signals rank first. CDN edges, hyperscaler-owned IPs, and provider tenant
hostnames are downranked. Geography is a salesperson-controlled filter rather
than a model decision.

## Success criteria

- The DuckDB account queue is stable and queryable without loading raw JSON.
- Every score can be reconstructed from `config/verticals/cybersecurity.yaml`.
- A seller can see why an account is ranked without opening raw scan data.
- LLM output contains no unsupported vulnerability or breach claim.
- The eval harness runs with one command and reports contact precision/recall
  and signal F1.
- A second vertical can be added without changing `src/scoring.py`.

## Out of scope for V1

- Claiming the dump represents the full internet.
- Contact enrichment or guessing people from domains.
- CVE matching from empty `opts.vulns` values.
- Loading the 73 GiB uncompressed dump into memory.
- Using an LLM to calculate risk scores.
- Shipping a second live vertical before the cybersecurity evals are reviewed.
