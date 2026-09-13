# How I Build

I started by identifying the source format instead of assuming it was company
data. I inspected magic bytes, streamed a small decompressed prefix, then made a
100-record fixture that could be read and reviewed safely. That changed the
product direction: the source is service-banner telemetry, so account identity
and attribution have to come before sales scoring.

My loop is evidence first: profile the sample, propose a rule, execute it over
all 100 records, and compare the resulting queue with the intended sales
decision. AI accelerated schema exploration, edge-case discovery, documentation,
and scaffolding. It was less reliable when turning observations directly into
policy; early proposals overweighted “cloud” and arbitrary high ports. Running
the rules exposed those mistakes faster than debating them.

The rule/LLM boundary is deliberate. Ports, tags, TLS flags, account rollup and
scores are deterministic, cheap and auditable. The model receives only the
already-approved signal list and writes a short account brief. Prompts are
versioned, outputs are schema-validated, calls are traced, and budget checks
happen before invocation.

The known weakness is attribution. Most records in this slice are IP-only, and
several apparent domains are provider-owned tenant hostnames. A larger sample
and reliable company enrichment are required before this is a production lead
source. I would flag that before handing the system to sales: a technically
accurate exposure is not useful outreach unless it is linked to the correct
buyer.

The product is named **SignalPath** so the engine is not trapped in a single
industry. Cybersecurity is implemented as a vertical plugin.
