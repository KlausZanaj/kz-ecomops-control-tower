"""Keep the documented reconciliation matrix aligned with the public catalog."""

from __future__ import annotations

from pathlib import Path

from kz_ecomops.reconciliation import AnomalyCode, RuleCode


PROJECT_ROOT = Path(__file__).parents[2]


def test_readme_matrix_contains_every_rule_and_anomaly_code_exactly_once() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Implemented reconciliation rules", 1)[1].split(
        "## Technology stack", 1
    )[0]
    rows = [line for line in section.splitlines() if line.startswith("| REC-")]
    documented_rules = [row.split("|")[1].strip() for row in rows]
    documented_anomalies = [row.split("`")[1] for row in rows]

    assert documented_rules == [rule.value for rule in RuleCode]
    assert documented_anomalies == [code.value for code in AnomalyCode]
    assert len(rows) == 10
