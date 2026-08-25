import json
from pathlib import Path
from collections import Counter

ENTITIES_DIR = Path("data/processed/entities")
RELATIONSHIPS_DIR = Path("data/processed/relationships")


def load_json_files(folder):
    data = []
    for file in folder.glob("*.json"):
        with open(file, "r", encoding="utf-8") as f:
            data.extend(json.load(f))
    return data


def verify_entities():
    entities = load_json_files(ENTITIES_DIR)

    print("\n======= ENTITY SUMMARY =======")
    print(f"Total Entities: {len(entities)}")

    entity_types = Counter(e["entity_type"] for e in entities)

    for etype, count in entity_types.items():
        print(f"{etype}: {count}")

    print("\nSample Entities:")
    for entity in entities[:20]:
        print(entity)


def verify_relationships():
    relationships = load_json_files(RELATIONSHIPS_DIR)

    print("\n======= RELATIONSHIP SUMMARY =======")
    print(f"Total Relationships: {len(relationships)}")

    rel_types = Counter(r["relationship"] for r in relationships)

    for rel, count in rel_types.items():
        print(f"{rel}: {count}")

    print("\nSample Relationships:")
    for rel in relationships[:20]:
        print(rel)


if __name__ == "__main__":
    verify_entities()
    verify_relationships()