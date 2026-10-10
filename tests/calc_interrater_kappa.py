#!/usr/bin/env python3
"""Calculate unweighted Cohen's kappa only after both human review columns are complete.

The calculation cannot authenticate reviewers. It refuses blank rows and duplicate
reviewer names; the group must ensure ratings were genuinely independent.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


CATEGORIES = ("pass", "partial", "fail")


def calculate(rows: list[dict[str, str]]) -> tuple[float, float, float | None]:
    count = len(rows)
    if count != 30 or len({row["id"] for row in rows}) != count:
        raise ValueError("Expected 30 unique cases")
    required = (
        "reviewer_A_name", "reviewer_A_rating", "reviewer_A_checked_url_or_NA", "reviewer_A_rationale",
        "reviewer_B_name", "reviewer_B_rating", "reviewer_B_checked_url_or_NA", "reviewer_B_rationale",
    )
    incomplete = [row["id"] for row in rows if any(not row.get(field, "").strip() for field in required)]
    if incomplete:
        raise ValueError(f"Independent reviews are incomplete for: {', '.join(incomplete)}")
    a_names = {row["reviewer_A_name"].strip() for row in rows}
    b_names = {row["reviewer_B_name"].strip() for row in rows}
    if len(a_names) != 1 or len(b_names) != 1 or a_names == b_names:
        raise ValueError("Enter two distinct reviewer names, consistent across all cases")
    invalid = [row["id"] for row in rows if row["reviewer_A_rating"].strip().lower() not in CATEGORIES or row["reviewer_B_rating"].strip().lower() not in CATEGORIES]
    if invalid:
        raise ValueError(f"Ratings must be pass, partial or fail for: {', '.join(invalid)}")

    a = [row["reviewer_A_rating"].strip().lower() for row in rows]
    b = [row["reviewer_B_rating"].strip().lower() for row in rows]
    observed = sum(x == y for x, y in zip(a, b)) / count
    a_counts, b_counts = Counter(a), Counter(b)
    expected = sum(a_counts[category] * b_counts[category] for category in CATEGORIES) / count**2
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    return observed, expected, kappa


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", type=Path, help="Completed two-reviewer CSV")
    args = parser.parse_args()
    with args.sheet.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    try:
        observed, expected, kappa = calculate(rows)
    except (KeyError, ValueError) as error:
        print(f"No kappa reported: {error}", file=sys.stderr)
        return 2
    print(f"Cases: {len(rows)}")
    print(f"Observed agreement: {observed:.3f}")
    print(f"Expected chance agreement: {expected:.3f}")
    print("Cohen's kappa: undefined (both reviewers used a single identical category)" if kappa is None else f"Cohen's kappa: {kappa:.3f}")
    print("Interpret these values alongside the case-level disagreements and source-check rationales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
