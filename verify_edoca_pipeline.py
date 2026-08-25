"""Verify the complete EDOCA analysis pipeline with a real EPC query."""

from __future__ import annotations

import json
import sys
from typing import Any

from src.orchestration.analyze import analyze

QUERY = "Is there a consistency issue with Unit 400 Pass 1 temperature?"
REQUIRED_FINDING_FIELDS = {
    "finding_id",
    "title",
    "severity",
    "status",
    "affected_assets",
    "root_cause",
    "evidence",
    "recommendation",
    "confidence",
    "reasoning",
}


def print_value(label: str, value: Any) -> None:
    """Print a pipeline value as readable JSON when structured."""
    if isinstance(value, (dict, list)):
        print(f"{label}: {json.dumps(value, indent=2, ensure_ascii=False)}")
    else:
        print(f"{label}: {value}")


def main() -> int:
    """Execute and report the complete EDOCA pipeline."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("======== EDOCA PIPELINE VERIFICATION ========")
    print(f"Query: {QUERY}")

    try:
        final_finding = analyze(QUERY)
    except Exception as exc:
        print(f"\nPipeline error: {exc}")
        print("\nEDOCA PIPELINE = FAIL")
        return 1

    if not isinstance(final_finding, dict):
        print("\nNo complete finding object returned.")
        print("\nEDOCA PIPELINE = FAIL")
        return 1

    print("\n======== Retrieved Evidence ========")
    print_value("Evidence Count", len(final_finding.get("evidence", [])))
    print_value("Evidence", final_finding.get("evidence", []))

    print("\n======== Graph Context ========")
    print_value("Affected Assets", final_finding.get("affected_assets", []))

    print("\n======== Assurance Results ========")
    print_value("Status", final_finding.get("status", ""))
    print_value("Severity", final_finding.get("severity", ""))
    print_value("Check", final_finding.get("title", ""))

    print("\n======== GPT Reasoning Output ========")
    print_value("Reasoning", final_finding.get("reasoning", ""))
    print_value("Confidence", final_finding.get("confidence", 0.0))

    print("\n======== Final Finding ========")
    print_value("Finding Title", final_finding.get("title", ""))
    print_value("Severity", final_finding.get("severity", ""))
    print_value("Root Cause", final_finding.get("root_cause", ""))
    print_value("Recommendation", final_finding.get("recommendation", ""))
    print_value("Evidence Count", len(final_finding.get("evidence", [])))
    print_value("Affected Assets", final_finding.get("affected_assets", []))

    complete = REQUIRED_FINDING_FIELDS.issubset(final_finding)
    print("\nEDOCA PIPELINE = PASS" if complete else "\nEDOCA PIPELINE = FAIL")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
