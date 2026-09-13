---
name: outreach-draft
description: Drafts evidence-grounded sales outreach from deterministic account signals. Default vertical is cybersecurity. Use when an addressable account has passed the score gate and needs a concise email.
disable-model-invocation: true
---

# Outreach Draft

## Trigger

Run only when all conditions hold:

- `is_addressable` is `true`
- `icp_score` meets the configured gate
- at least one positive deterministic signal exists
- the daily and monthly LLM budgets have capacity

Never run for an IP-only account or provider-owned hostname.

## Inputs

Pass only this redacted account shape:

```json
{
  "account_name": "example.com",
  "country_code": "US",
  "icp_score": 60,
  "ports": [5985],
  "signals": [
    {
      "code": "exposed_winrm",
      "detail": "Public Windows remote-management service on port 5985"
    }
  ]
}
```

Do not pass raw banners, HTML, certificates, NTLM values, IP addresses, or
favicon data.

## Workflow

1. Load `prompts/outreach_draft_v1.md`.
2. Confirm every factual claim maps to one supplied signal.
3. Produce the required JSON object.
4. Reject output containing an invented CVE, breach claim, or unsupported
   software version.
5. Write the redacted execution trace.

## Output contract

```json
{
  "subject": "string, at most 80 characters",
  "opening": "string, at most 280 characters",
  "evidence": ["one to three signal-grounded statements"],
  "call_to_action": "string, at most 180 characters",
  "confidence": "low | medium | high"
}
```

## Worked invocation

Input:

```json
{
  "account_name": "example.com",
  "country_code": "US",
  "icp_score": 60,
  "ports": [5985],
  "signals": [
    {
      "code": "exposed_winrm",
      "detail": "Public Windows remote-management service on port 5985"
    },
    {
      "code": "windows_auth_leak",
      "detail": "NTLM metadata is exposed by the service"
    }
  ]
}
```

Acceptable output:

```json
{
  "subject": "A public Windows management surface at example.com",
  "opening": "We observed an externally reachable Windows management service associated with example.com.",
  "evidence": [
    "WinRM is reachable on port 5985.",
    "The service exposes NTLM metadata."
  ],
  "call_to_action": "Would a 15-minute review of the observed exposure be useful?",
  "confidence": "high"
}
```
