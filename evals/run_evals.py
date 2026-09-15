#!/usr/bin/env python3
"""Run the deterministic baseline against the 25-account golden set."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.metrics import classification_metrics, set_metrics
from src.ingester import load_records, normalize_banner
from src.scoring import load_rules, score_accounts

DEFAULT_BANNERS = Path("evals/datasets/eval_banners.jsonl")
DEFAULT_LABELS = Path("evals/datasets/accounts_labelled.jsonl")
DEFAULT_RESULT = Path("evals/results/latest.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate account scoring.")
    parser.add_argument("--banners", type=Path, default=DEFAULT_BANNERS)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--vertical", default=None)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    rules = load_rules(vertical=args.vertical)
    records = [
        normalized
        for record in load_records(args.banners)
        if (normalized := normalize_banner(record)) is not None
    ]
    predictions = {
        account.account_id: account
        for account in score_accounts(records, rules, vertical=args.vertical)
    }
    labels = read_jsonl(args.labels)
    missing = [
        label["account_id"]
        for label in labels
        if label["account_id"] not in predictions
    ]
    if missing:
        raise ValueError(f"labelled accounts missing from eval banners: {missing}")

    gate = int(rules["llm_gate_score"])
    expected_contact: list[bool] = []
    predicted_contact: list[bool] = []
    expected_signals: list[set[str]] = []
    predicted_signals: list[set[str]] = []
    failures: list[dict[str, Any]] = []

    for label in labels:
        prediction = predictions[label["account_id"]]
        expected_should_contact = bool(label["should_contact"])
        predicted_should_contact = (
            prediction.is_addressable and prediction.icp_score >= gate
        )
        wanted_signals = set(label["expected_signals"])
        got_signals = {signal.code for signal in prediction.signals}

        expected_contact.append(expected_should_contact)
        predicted_contact.append(predicted_should_contact)
        expected_signals.append(wanted_signals)
        predicted_signals.append(got_signals)

        if expected_should_contact != predicted_should_contact or (
            wanted_signals != got_signals
        ):
            failures.append(
                {
                    "account_id": label["account_id"],
                    "expected_should_contact": expected_should_contact,
                    "predicted_should_contact": predicted_should_contact,
                    "expected_signals": sorted(wanted_signals),
                    "predicted_signals": sorted(got_signals),
                }
            )

    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "rules_version": rules["version"],
        "vertical": rules.get("id"),
        "eval_banners": len(records),
        "labelled_accounts": len(labels),
        "contact_metrics": classification_metrics(expected_contact, predicted_contact),
        "signal_metrics": set_metrics(expected_signals, predicted_signals),
        "failures": failures,
    }


def main() -> int:
    args = parse_args()
    result = evaluate(args)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

    # A regression fails CI only if rule extraction diverges from labels.
    # Contact-policy misses remain visible while the gate is tuned.
    return 1 if result["signal_metrics"]["f1"] < 1.0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
