# How I Build

## The loop

Evidence first, then policy, then code. I started by identifying the source
format rather than assuming it was company data: magic bytes, then a streamed
decompressed prefix, then a small reviewed slice I could read by hand. That
changed the product direction before any scoring existed — the records are
service-banner telemetry, so account identity and attribution had to be solved
before sales scoring meant anything.

From there each rule followed the same cycle: profile the slice, count the base
rate, propose a weight, run it over every record, and compare the resulting
queue against the sales decision it is supposed to support. A rule that could
not survive that comparison was deleted, not tuned.

My tooling was Cursor with an agent in the loop for exploration, scaffolding,
and refactors, driven from the terminal and the test suite. I kept `ruff`,
`pytest`, and the eval harness as the contract the agent had to satisfy; that
is what made fast generation safe. Where a workflow recurred — outreach drafting
— I packaged it as a versioned `SKILL.md` with explicit inputs and an output
schema, so it is reproducible from any agent rather than living in chat history.

## Where AI paid off

Schema archaeology on deeply nested, sparsely populated records was the biggest
win: enumerating field coverage, spotting `opts.vulns` was empty everywhere it
appeared, and finding the edge cases in identity handling (an IP with a trailing
dot in a `domains` array, provider tenant hostnames masquerading as customers).
It was also fast at the mechanical half of the DuckDB migration — generating the
SQL rollup from the same YAML the Python scorer reads, and writing the parity
test that keeps them honest.

## Where it cost more than doing it by hand

Turning observations into policy. Early proposals overweighted "cloud presence"
and arbitrary high ports — both fire on a quarter of the data, dominate the
score, and say nothing about whether a company needs security software. The
model was confident about them; the base rates were not. Running the rules over
real records settled those arguments far faster than reasoning about them.

The second cost was scale-boundary work. The first ingestion attempt failed on
CSV quoting inside organization names, on a `zstd` SIGPIPE that looked like a
crash, and on a buffer limit that would have silently dropped oversized records.
Each fix was small, but finding them required reading real failures. I also had
to make a deliberate call there: fail loudly on an oversized record rather than
skip it, because silent data loss in a sales pipeline is invisible until someone
asks why an account never appeared.

## What measurement changed

Two problems only became visible once I looked at real output rather than at
code. A trace showed the model receiving 34 raw ports and signal details that
read "Detected by deterministic rule: exposed_winrm" — the scores were grounded
but the drafts were not, because the SQL store had kept the codes and thrown
away the sentences. Persisting the evidence text and cutting ports down to the
ones a signal actually cites fixed the input the model sees.

The second came from the eval set. Reading contact precision and recall against
a sweep of candidate gates showed precision *falling* as the gate rose, which is
the opposite of the intended behaviour. The cause is that the highest-scoring
band is full of hosting and VPS providers whose exposed management surface
belongs to their tenants. That is a scoring defect the rules cannot see, and no
amount of prompt work would have surfaced it.

## The weakness I would flag to a teammate

**Attribution.** Most records resolve to an IP with no attributable company, and
in several sampled accounts the domain and the network owner disagree about who
runs the host. Until a hosting-provider downrank exists and company enrichment
is wired in, the top of the queue will contain accounts where the finding is
real but the owner is wrong — and that is the one failure mode a salesperson
cannot recover from in a first email.

The product is named **SignalPath** deliberately: the engine should not be
trapped in one industry. Cybersecurity is implemented as a vertical plugin, and
the next motion should be a YAML file and an extractor, not a fork.
