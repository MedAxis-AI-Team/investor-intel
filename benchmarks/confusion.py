from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_LABELS = ["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class ConfusionReport:
    """Confusion matrix and derived classification metrics."""

    labels: list[str]
    matrix: list[list[int]]
    per_class: dict[str, dict[str, float]]
    precision_weighted: float
    recall_weighted: float
    f1_weighted: float
    total_samples: int
    correct: int
    accuracy: float


def build_confusion_report(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str] | None = None,
) -> ConfusionReport:
    """Build a confusion matrix and classification report.

    Uses sklearn if available, otherwise falls back to a pure-Python
    implementation so that benchmarks can run without sklearn installed.
    """
    labels = labels or _LABELS

    if not y_true:
        return _pure_python_report(y_true, y_pred, labels)

    try:
        return _sklearn_report(y_true, y_pred, labels)
    except ImportError:
        logger.info("sklearn not available — using pure-Python confusion matrix")
        return _pure_python_report(y_true, y_pred, labels)


def _sklearn_report(
    y_true: list[str], y_pred: list[str], labels: list[str]
) -> ConfusionReport:
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0.0,
    )

    per_class: dict[str, dict[str, float]] = {}
    for i, label in enumerate(labels):
        per_class[label] = {
            "precision": round(float(precision[i]), 4),
            "recall": round(float(recall[i]), 4),
            "f1": round(float(f1[i]), 4),
            "support": int(support[i]),
        }

    # Weighted averages
    total = sum(int(s) for s in support)
    if total > 0:
        p_w = sum(float(precision[i]) * int(support[i]) for i in range(len(labels))) / total
        r_w = sum(float(recall[i]) * int(support[i]) for i in range(len(labels))) / total
        f1_w = sum(float(f1[i]) * int(support[i]) for i in range(len(labels))) / total
    else:
        p_w = r_w = f1_w = 0.0

    correct = sum(int(cm[i][i]) for i in range(len(labels)))

    return ConfusionReport(
        labels=labels,
        matrix=cm.tolist(),
        per_class=per_class,
        precision_weighted=round(p_w, 4),
        recall_weighted=round(r_w, 4),
        f1_weighted=round(f1_w, 4),
        total_samples=total,
        correct=correct,
        accuracy=round(correct / total, 4) if total else 0.0,
    )


def _pure_python_report(
    y_true: list[str], y_pred: list[str], labels: list[str]
) -> ConfusionReport:
    label_idx = {label: i for i, label in enumerate(labels)}
    n = len(labels)

    # Build matrix
    matrix = [[0] * n for _ in range(n)]
    for true, pred in zip(y_true, y_pred):
        ti = label_idx.get(true)
        pi = label_idx.get(pred)
        if ti is not None and pi is not None:
            matrix[ti][pi] += 1

    # Compute per-class metrics
    per_class: dict[str, dict[str, float]] = {}
    total = len(y_true)

    for i, label in enumerate(labels):
        tp = matrix[i][i]
        fp = sum(matrix[j][i] for j in range(n)) - tp
        fn = sum(matrix[i][j] for j in range(n)) - tp
        support = sum(matrix[i][j] for j in range(n))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
        }

    # Weighted averages
    correct = sum(matrix[i][i] for i in range(n))
    if total > 0:
        p_w = sum(per_class[l]["precision"] * per_class[l]["support"] for l in labels) / total
        r_w = sum(per_class[l]["recall"] * per_class[l]["support"] for l in labels) / total
        f1_w = sum(per_class[l]["f1"] * per_class[l]["support"] for l in labels) / total
    else:
        p_w = r_w = f1_w = 0.0

    return ConfusionReport(
        labels=labels,
        matrix=matrix,
        per_class=per_class,
        precision_weighted=round(p_w, 4),
        recall_weighted=round(r_w, 4),
        f1_weighted=round(f1_w, 4),
        total_samples=total,
        correct=correct,
        accuracy=round(correct / total, 4) if total else 0.0,
    )
