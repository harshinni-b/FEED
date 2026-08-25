"""Verify semantic quality of EDOCA entities and relationships."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ENTITY_TYPES = (
    "DOCUMENT",
    "UNIT",
    "EQUIPMENT",
    "INSTRUMENT",
    "CONTROL_LOOP",
    "SIF",
    "VALVE",
    "LINE",
    "PARAMETER",
)
RELATIONSHIP_TYPES = (
    "DESCRIBES",
    "HAS_PARAMETER",
    "HAS_LIMIT",
    "HAS_VALUE",
    "APPEARS_IN",
    "RELATED_TO",
)
SEARCH_TERMS = ("Unit-400", "Pass-1", "TSHH-401", "TIC-401", "SIF-05", "XV-101")
ENGINEERING_TYPES = set(ENTITY_TYPES) - {"DOCUMENT", "PARAMETER"}


def load_records(directory: Path) -> list[dict[str, Any]]:
    """Load dictionary records from every JSON file in a directory."""
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError(f"Expected a JSON list in {path}")
        records.extend(record for record in loaded if isinstance(record, dict))
    return records


def normalized(value: str) -> str:
    """Normalize case and separators for semantic term matching."""
    return "".join(value.casefold().split()).replace("-", "")


def print_entity_summary(entities: list[dict[str, Any]]) -> None:
    """Print entity totals, type counts, and representative samples."""
    counts = Counter(str(entity.get("entity_type", "UNKNOWN")) for entity in entities)
    print("======== ENTITY SUMMARY ========")
    print(f"Total Entities: {len(entities)}")
    print("\nBreakdown by type:")
    for entity_type in ENTITY_TYPES:
        print(f"{entity_type}: {counts.get(entity_type, 0)}")
    print("\n20 sample entities:")
    for entity in entities[:20]:
        print(
            f"- {entity.get('name', '')} "
            f"[{entity.get('entity_type', 'UNKNOWN')}] "
            f"({entity.get('entity_id', '')})"
        )


def print_relationship_summary(relationships: list[dict[str, Any]]) -> None:
    """Print relationship totals, type counts, and representative samples."""
    counts = Counter(
        str(relationship.get("relationship", "UNKNOWN"))
        for relationship in relationships
    )
    print("\n======== RELATIONSHIP SUMMARY ========")
    print(f"Total Relationships: {len(relationships)}")
    print("\nBreakdown by type:")
    for relationship_type in RELATIONSHIP_TYPES:
        print(f"{relationship_type}: {counts.get(relationship_type, 0)}")
    print("\n20 sample relationships:")
    for relationship in relationships[:20]:
        print(
            f"- {relationship.get('source', '')} "
            f"--[{relationship.get('relationship', 'UNKNOWN')}]--> "
            f"{relationship.get('target', '')} "
            f"({relationship.get('document', '')})"
        )


def print_search_results(entities: list[dict[str, Any]]) -> None:
    """Print whether each requested engineering term exists."""
    available = {
        normalized(str(entity.get("name", ""))) for entity in entities
    }
    print("\n======== ENGINEERING ENTITY SEARCH ========")
    for term in SEARCH_TERMS:
        status = "FOUND" if normalized(term) in available else "NOT FOUND"
        print(f"{term}: {status}")


def print_readiness(entities: list[dict[str, Any]]) -> bool:
    """Print and return whether engineering entities are available for retrieval."""
    counts = Counter(str(entity.get("entity_type", "")) for entity in entities)
    engineering_count = sum(counts[entity_type] for entity_type in ENGINEERING_TYPES)
    ready = engineering_count > 0
    print("\n======== GRAPH READINESS ========")
    if ready:
        print(f"PASS: Engineering entities exist ({engineering_count} entities).")
    else:
        print("FAIL: Only generic parameters exist; engineering entities are missing.")
    return ready


def main() -> int:
    """Run semantic verification against processed EDOCA outputs."""
    entities = load_records(Path("data/processed/entities"))
    relationships = load_records(Path("data/processed/relationships"))
    print_entity_summary(entities)
    print_relationship_summary(relationships)
    print_search_results(entities)
    return 0 if print_readiness(entities) else 1


if __name__ == "__main__":
    raise SystemExit(main())
