"""Small dependency-free classification metrics."""

from __future__ import annotations

from collections.abc import Iterable


def classification_metrics(
    expected: Iterable[bool], predicted: Iterable[bool]
) -> dict[str, float | int]:
    pairs = list(zip(expected, predicted, strict=True))
    true_positive = sum(want and got for want, got in pairs)
    false_positive = sum(not want and got for want, got in pairs)
    false_negative = sum(want and not got for want, got in pairs)
    true_negative = sum(not want and not got for want, got in pairs)

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def set_metrics(
    expected_sets: Iterable[set[str]], predicted_sets: Iterable[set[str]]
) -> dict[str, float | int]:
    expected_flat: list[bool] = []
    predicted_flat: list[bool] = []
    for expected, predicted in zip(expected_sets, predicted_sets, strict=True):
        universe = expected | predicted
        for label in universe:
            expected_flat.append(label in expected)
            predicted_flat.append(label in predicted)
    return classification_metrics(expected_flat, predicted_flat)
