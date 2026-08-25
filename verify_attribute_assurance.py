"""Verify deterministic attribute assurance against retrieved evidence."""

from __future__ import annotations

import sys
from pathlib import Path

from src.assurance.attribute import AttributeAssuranceEngine
from src.knowledge.evidence_index import EvidenceIndex


def main() -> int:
    """Retrieve sample evidence, run assurance, and print findings."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    evidence_index = EvidenceIndex()
    evidence_index.index_chunks(
        Path("data/processed/chunks"),
        Path("data/processed/evidence"),
    )
    retrieved_chunks = evidence_index.search_by_keyword("621°C")[:3]
    sample_evidence = [
        {
            "chunk_id": "verification:temperature-limit",
            "document_id": "DOC2",
            "section": "UNIT 400 - CONVERTER",
            "subsection": "Pass 1 Temperature",
            "text": "Configured limit is 620°C; operating value is 621°C.",
            "source_type": "table",
        },
        *retrieved_chunks,
    ]

    findings = AttributeAssuranceEngine().validate(sample_evidence)

    print("======== ATTRIBUTE ASSURANCE VERIFICATION ========")
    print(f"Retrieved evidence chunks: {len(retrieved_chunks)}")
    print(f"Evidence records checked: {len(sample_evidence)}")
    print("\n======== FINDINGS ========")
    if not findings:
        print("No numerical consistency findings generated.")
    for finding in findings:
        print(finding)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
