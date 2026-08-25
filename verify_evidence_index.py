"""Verify deterministic EDOCA evidence-index searches."""

from __future__ import annotations

import sys
from pathlib import Path

from src.knowledge.evidence_index import EvidenceChunk, EvidenceIndex

SEARCHES = ("Unit-400", "Pass-1", "WHB-201", "TK-101A", "TSHH-401")


def main() -> int:
    """Build the evidence index and print the first five results per search."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    evidence_index = EvidenceIndex()
    evidence_index.index_chunks(
        Path("data/processed/chunks"),
        Path("data/processed/evidence"),
    )

    print("======== EVIDENCE INDEX VERIFICATION ========")
    for query in SEARCHES:
        results = search_entity(evidence_index, query)
        print(f"\nSearch: {query}")
        print(f"Number of chunks returned: {len(results)}")
        for index, result in enumerate(results[:5], start=1):
            print(f"\nResult {index}")
            print(f"Document: {result['document_id']}")
            print(f"Section: {result['section']}")
            print(f"Source text: {result['text']}")

    return 0


def search_entity(evidence_index: EvidenceIndex, query: str) -> list[EvidenceChunk]:
    """Search exact entity text, then tolerate EPC hyphen/space variants."""
    results = evidence_index.search_by_entity(query)
    if results:
        return results
    return evidence_index.search_by_keyword(query.replace("-", " "))


if __name__ == "__main__":
    raise SystemExit(main())
