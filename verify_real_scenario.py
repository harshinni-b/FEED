"""Verify the real Unit 400 Pass 1 temperature scenario end to end."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from src.orchestration.analyze import EDOCAAnalyzer
from src.reasoning.gpt_reasoner import GPTReasoner

QUESTION = "Is there a consistency issue with Unit 400 Pass 1 temperature?"


class DeterministicReasoningProvider:
    """Return grounded JSON for offline pipeline verification."""

    def generate(self, prompt: str) -> dict[str, Any]:
        """Create a response from assurance and graph facts in the prompt."""
        payload = json.loads(prompt.split("\n\n", 1)[1])
        assurance = payload.get("assurance_results", [])
        graph_context = payload.get("graph_context", {})
        assets = [
            str(node.get("name", ""))
            for node in graph_context.get("nodes", [])
            if isinstance(node, dict)
            and node.get("entity_type") in {
                "UNIT", "EQUIPMENT", "INSTRUMENT", "CONTROL_LOOP",
                "SIF", "VALVE", "LINE",
            }
        ]
        failed = next((result for result in assurance if result.get("status") == "FAIL"), {})
        return {
            "finding_title": str(failed.get("check", "Engineering consistency issue")),
            "severity": str(failed.get("severity", "HIGH")),
            "confidence": 1.0 if failed else 0.5,
            "root_cause": str(failed.get("finding", "Insufficient assurance evidence.")),
            "reasoning": "Deterministic verification used only supplied EPC evidence and assurance results.",
            "recommendation": "Review the failed assurance result with the engineering team.",
            "affected_assets": assets[:10],
        }


def print_json(label: str, value: Any) -> None:
    """Print structured verification data as readable JSON."""
    print(f"{label}: {json.dumps(value, indent=2, ensure_ascii=False)}")


def main() -> int:
    """Run and report the real EPC scenario through every pipeline stage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("======== REAL EDOCA SCENARIO ========")
    print(f"Question: {QUESTION}")
    print("Reasoning mode: live GPT-4o" if os.getenv("EDOCA_LIVE_GPT") else "Reasoning mode: deterministic offline provider")

    try:
        provider = None if os.getenv("EDOCA_LIVE_GPT") else DeterministicReasoningProvider()
        analyzer = EDOCAAnalyzer(reasoner=GPTReasoner(provider))
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
            analyzer._builder_results(assurance_results),
            reasoning,
        )
    except Exception as exc:
        print(f"\nPipeline error: {exc}")
        print("\nEDOCA REAL SCENARIO = FAIL")
        return 1

    attribute_titles = {
        str(result["check"])
        for result in assurance_results
        if analyzer._is_attribute_result(result) and result.get("status") == "FAIL"
    }
    final_finding = next(
        (finding for finding in findings if finding.get("title") in attribute_titles),
        findings[0] if findings else None,
    )
    print(f"\nEvidence Count: {len(evidence)}")
    print(
        "Matched Documents: "
        + json.dumps(sorted({record.get("document_id", "") for record in evidence}))
    )
    print_json("Graph Context", graph_context or {})
    print_json("Assurance Results", assurance_results)
    print_json("GPT Reasoning", reasoning)
    print_json("Final Finding", final_finding or {})

    complete = isinstance(final_finding, dict) and all(
        field in final_finding
        for field in (
            "finding_id",
            "title",
            "severity",
            "status",
            "root_cause",
            "reasoning",
            "recommendation",
            "evidence",
            "affected_assets",
            "confidence",
        )
    )
    print("\nEDOCA REAL SCENARIO = PASS" if complete else "\nEDOCA REAL SCENARIO = FAIL")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
