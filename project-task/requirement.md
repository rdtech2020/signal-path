# Take-Home Task: AI Sales Intelligence Platform

## Context

Imagine you're building for the sales team at a **cybersecurity software company**. Their challenge: out of thousands of businesses in the market, which ones actually need our services right now — and how do we reach them first?

Your job is to turn raw company data into a tool that answers that question.

## The Task

Build a small **sales intelligence platform** that helps a sales team **identify, prioritise, and target** businesses most likely to need cybersecurity software.

Before you build, spend some time researching how B2B sales teams actually prospect — ideal customer profiles (ICP), account scoring, buying signals, territory and segment filtering, outreach prioritisation. Let real use cases drive what you build, not the other way around.

## Dataset

Use the dataset below as the **core** of your prototype.

Dataset link : https://f001.backblazeb2.com/b2api/v1/b2_download_file_by_id?fileId=4_z53658c377a6f469082f90a15_f20920f9b7a3450c4_d20260907_m081559_c001_v0001183_t0057_u01788768959953

- You're welcome to supplement it with additional or derived data (enrichment, signals, scoring), but the provided dataset must remain central.
- Think creatively: what hidden signals in this data could tell a salesperson *"this company needs cybersecurity help"*?

## We Are AI-Native — Build Like It

At Firmable, AI is not a productivity tool bolted onto engineering work — it *is* the workflow. We'll assess **how you build** as much as what you ship.

Wherever your app uses an LLM (account scoring, company summaries, outreach drafting, signal classification — your choice), we want to see the production scaffolding around it:

- **Skills** — package at least one recurring AI workflow as a reusable, versioned `SKILL.md` (e.g. `account-scoring` or `outreach-draft`) that any agent (Claude Code, Cursor, API) can load and run: trigger conditions, inputs, outputs, dependent prompts, and a worked example invocation.
- **Evals** — a small hand-labelled eval set (20–30 examples) for your core LLM feature, with measured precision/recall or an equivalent quality metric. We care less about the number and more about whether you've *measured* your system and can defend its weaknesses.
- **Eval harness** — a one-command script that re-runs your checks against the labelled set and reports results vs. the previous prompt version.
- **Tracing & observability** — a log schema for every LLM call: request, response, model, prompt version, latency, cost, decision. JSONL or SQLite is fine — the schema is what matters.
- **Prompt versioning** — prompts tracked as files (or a registry) so v1 vs. v2 of a feature can be compared.
- **Cost monitoring** — show your math: tokens × volume × frequency, model choice per task (cheap model for classification, stronger model for judgement), and the cost ceiling you'd set in production.

If your app uses **no** LLM features, tell us why — that's a legitimate engineering decision, but we expect the reasoning.

## Deliverables

1. **A working, hosted app** — a small but functional product demonstrating how prospecting and targeting works with this data. Host it anywhere and share the link.
2. **A Git repository** containing:
    - Full source code
    - `skills/` directory with your `SKILL.md` file(s)
    - `prompts/` directory with versioned prompts
    - `evals/` directory with labelled sets, eval harness, and results
    - A short **planning document** (the use cases you chose and why)
    - An **architecture document** (how the pieces fit together, key design decisions, trade-offs — including your rule-vs-LLM split and cost model)
3. **A short "How You Build" reflection** (½–1 page): your dev loop and agentic tools used (Claude Code, Cursor, API scripts), where AI saved you the most time vs. where it cost more than doing it by hand, and one known weakness you'd flag when handing this to a teammate.
4. **Optional but valued:** a ≤5-minute Loom walking through your agentic dev loop and the app running end-to-end.

## What We're Looking For

- **Product thinking** — did you build something a salesperson would actually use?
- **Creative use of the data** — signals, scoring, or segmentation beyond simple filters
- **AI-native craft** — skills, evals, traces, prompt versioning, and cost awareness — not prompts glued together
- **Engineering quality** — clean, working code with sensible architecture, and rules used where rules are the right tool
- **Clarity** — we should understand your decisions from the docs, not have to reverse-engineer them

## Timeline & Questions

- Please share your submission within **one week ( 7 to 8 days )** of receiving this task.
- Questions are welcome.

Looking forward to seeing what you build. 🚀