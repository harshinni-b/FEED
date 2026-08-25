"""Verify the complete EDOCA pipeline for the Unit 400 temperature query."""

from __future__ import annotations

import json
import sys
from typing import Any

from src.orchestration.analyze import EDOCAAnalyzer

QUESTION = "Is there a consistency issue with Unit 400 Pass 1 temperature?"
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


def print_json(label: str, value: Any) -> None:
    """Print structured pipeline data as readable JSON."""
    print(f"{label}: {json.dumps(value, indent=2, ensure_ascii=False)}")


def main() -> int:
    """Execute each EDOCA stage and report whether a finding was produced."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("======== EDOCA END-TO-END VERIFICATION ========")
    print(f"Question: {QUESTION}")

    try:
        analyzer = EDOCAAnalyzer()
        analyzer._ensure_ready()

        evidence = analyzer._retrieve(QUESTION)
        graph_context = analyzer._graph_context(QUESTION, evidence)
        assurance_results = analyzer._run_assurance(QUESTION, evidence, graph_context)
        reasoning = analyzer._get_reasoning(
            QUESTION,
            graph_context,
            evidence,
            assurance_results,
        )
        findings = analyzer.finding_builder.build(
            evidence,
            graph_context,
            analyzer._attribute_results(assurance_results),
        )
        final_finding = dict(findings[0]) if findings else None
        if final_finding is not None:
            final_finding.update(
                {
                    "title": reasoning["finding_title"],
                    "severity": reasoning["severity"],
                    "root_cause": reasoning["root_cause"],
                    "recommendation": reasoning["recommendation"],
                    "confidence": reasoning["confidence"],
                    "affected_assets": reasoning["affected_assets"]
                    or final_finding["affected_assets"],
                    "reasoning": reasoning["reasoning"],
                }
            )
    except Exception as exc:
        print(f"\nPipeline error: {exc}")
        print("\nEDOCA = FAIL")
        return 1

    print(f"\nEvidence Count: {len(evidence)}")
    print_json("Graph Context", graph_context or {})
    print_json("Assurance Results", assurance_results)
    print_json("GPT Reasoning", reasoning)
    print_json("Final Finding", final_finding or {})

    complete = isinstance(final_finding, dict) and REQUIRED_FINDING_FIELDS.issubset(final_finding)
    print("\nEDOCA = PASS" if complete else "\nEDOCA = FAIL")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
