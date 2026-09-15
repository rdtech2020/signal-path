# Product Plan

**SignalPath** takes observational internet-exposure data and returns a ranked,
explainable account queue.

V1 ships the **cybersecurity** motion. The engine is built to host later motions
(IT operations, payroll, payments) by swapping signal catalogs, not by forking
the app.

## The user and the decision

The user is a seller or SDR building a daily prospecting list at a cybersecurity
software company. Their decision is not "which record looks unusual?" but:

> Which attributable company has a concrete, defensible reason to talk today,
> and what do I say in the first line?

That framing drives everything below. In B2B prospecting the work splits into
four steps, and the product mirrors them:

| Prospecting step | In SignalPath |
|---|---|
| Define an ICP | Signal catalog and weights in `config/verticals/cybersecurity.yaml` |
| Score and prioritise accounts | `icp_score` 0–100 per account, ranked queue |
| Filter territory and segment | Country filter, score floor, addressable-only toggle |
| Open the conversation | `outreach-draft` skill, gated and budgeted |

## Why this data supports that decision

The source is service-banner telemetry: one record is an IP plus a port plus a
service payload. It is not a firmographic company row. There is no revenue,
headcount, industry, or intent field to score.

So the usable wedge is **externally observed attack surface** — public
administration interfaces, exposed authentication metadata, legacy VPN, expired
or self-signed TLS, end-of-life software, unshielded origins. These are exactly
the reasons a security buyer takes a meeting, and they are visible in this data
without enrichment.

The hard part is not detection. It is **attribution**. Of 1,585,994 rolled-up
accounts, only 203,021 carry a name, and only 201,397 survive sanitization as
sales-addressable. A technically correct finding on an unattributable IP is not
a lead — and a finding on a hosting provider's tenant is worse, because it looks
like a lead. That is why the labelled eval asks whether the evidence plausibly
belongs to the account, not just whether a signal fired.

## V1 use cases

1. **Prioritise attributable accounts** by externally observed risk evidence.
2. **Work a territory** by filtering country and inspecting exposed ports.
3. **Explain every rank** from deterministic signals, with no model in the loop.
4. **Draft the first touch** only for high-scoring, addressable accounts, under
   an explicit budget.

## ICP policy

Rank first: accounts with direct administration exposure (WinRM), exposed
Windows authentication metadata (NTLM), legacy VPN (PPTP), end-of-life software,
or weak TLS.

Rank down: CDN edges, hyperscaler-owned unnamed IPs, and provider tenant
hostnames. These describe a hosting provider, not a buyer.

Exclude entirely from the sellable queue: loopback and private address space,
cloud metadata endpoints, placeholder names, non-public DNS suffixes, and
honeypot domains. Geography stays a seller-controlled filter, never a model
decision.

## Rules, not a model, decide priority

Scores are deterministic and cost nothing per account. That is a product
decision as much as an engineering one: a seller will not trust a rank they
cannot interrogate, and a sales manager cannot defend a quota built on an
unexplainable number. The LLM writes prose from already-approved signals; it
never computes or overrides a score.

## Success criteria

- The account queue is stable, queryable, and served without loading raw JSON.
- Every score is reconstructable from the vertical's YAML config.
- A seller can see why an account ranks without opening raw scan data, in the
  same words the outreach model is given.
- Nothing in the queue is a private, placeholder, or unroutable identity.
- A brief names the ports that carry evidence and summarizes the rest, rather
  than pasting a port scan into an email.
- Generated drafts contain no vulnerability, breach, or version claim that is
  not backed by a deterministic signal.
- One command reruns the eval harness and reports comparable metrics, including
  how the outreach gate trades precision against recall.
- A second motion can be added without editing `src/scoring.py`.

## Out of scope for V1

- Claiming this archive represents the whole internet.
- Contact enrichment or inferring people from domains.
- CVE matching — `opts.vulns` is empty everywhere it appears in this data.
- Expanding the archive to raw JSON on disk.
- Using an LLM to calculate risk scores.
- Launching a second live vertical before the cybersecurity labels are reviewed.
