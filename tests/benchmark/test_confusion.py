from __future__ import annotations

from benchmarks.confusion import build_confusion_report


def test_perfect_predictions() -> None:
    y_true = ["HIGH", "MEDIUM", "LOW", "HIGH", "LOW"]
    y_pred = ["HIGH", "MEDIUM", "LOW", "HIGH", "LOW"]
    report = build_confusion_report(y_true, y_pred)

    assert report.accuracy == 1.0
    assert report.correct == 5
    assert report.total_samples == 5
    assert report.f1_weighted == 1.0


def test_all_wrong() -> None:
    y_true = ["HIGH", "HIGH", "HIGH"]
    y_pred = ["LOW", "LOW", "LOW"]
    report = build_confusion_report(y_true, y_pred)

    assert report.accuracy == 0.0
    assert report.correct == 0
    assert report.per_class["HIGH"]["recall"] == 0.0
    assert report.per_class["LOW"]["precision"] == 0.0


def test_partial_match() -> None:
    y_true = ["HIGH", "MEDIUM", "LOW", "HIGH"]
    y_pred = ["HIGH", "LOW", "LOW", "MEDIUM"]
    report = build_confusion_report(y_true, y_pred)

    assert report.correct == 2  # HIGH and LOW correct
    assert report.accuracy == 0.5
    assert report.total_samples == 4


def test_single_class() -> None:
    y_true = ["HIGH", "HIGH", "HIGH"]
    y_pred = ["HIGH", "HIGH", "HIGH"]
    report = build_confusion_report(y_true, y_pred)

    assert report.accuracy == 1.0
    assert report.per_class["HIGH"]["precision"] == 1.0
    assert report.per_class["HIGH"]["recall"] == 1.0


def test_empty_inputs() -> None:
    report = build_confusion_report([], [])
    assert report.total_samples == 0
    assert report.accuracy == 0.0


def test_matrix_shape() -> None:
    y_true = ["HIGH", "MEDIUM"]
    y_pred = ["MEDIUM", "HIGH"]
    report = build_confusion_report(y_true, y_pred)

    assert len(report.matrix) == 3  # 3 labels
    assert all(len(row) == 3 for row in report.matrix)
    assert report.labels == ["HIGH", "MEDIUM", "LOW"]
