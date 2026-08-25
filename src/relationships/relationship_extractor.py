"""Rule-based relationship extraction for engineering entities and chunks."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Pattern, TypedDict

logger = logging.getLogger(__name__)


class ExtractedRelationship(TypedDict):
	"""Schema for a relationship in the plant knowledge graph."""

	source: str
	relationship: str
	target: str
	document: str


DEFAULT_VALUE_PATTERN = (
	r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?\s*"
	r"(?:%|t/d|kg/h|Nm[³3]/h|m[³3]/h|kW|bar(?:g)?|°C|C|mm|m|yr)\b"
)
DEFAULT_LIMIT_PATTERN = (
	r"(?:maximum|minimum|min\.?|max\.?|limit|rated|design|normal|allowable)"
	r"[^.\n]{0,50}?"
	+ DEFAULT_VALUE_PATTERN
)


class RelationshipExtractor:
	"""Extract deterministic relationships from chunks and extracted entities."""

	def __init__(
		self,
		value_pattern: str | Pattern[str] = DEFAULT_VALUE_PATTERN,
		limit_pattern: str | Pattern[str] = DEFAULT_LIMIT_PATTERN,
	) -> None:
		self.value_pattern = self._compile(value_pattern)
		self.limit_pattern = self._compile(limit_pattern)

	def extract_relationships(
		self,
		chunks: list[dict[str, Any]],
		entities: list[dict[str, Any]],
	) -> list[ExtractedRelationship]:
		"""Extract and deduplicate relationships using chunk-local evidence."""
		entities_by_chunk: dict[str, list[dict[str, Any]]] = {}
		for entity in entities:
			source_chunk = str(entity.get("source_chunk", ""))
			entities_by_chunk.setdefault(source_chunk, []).append(entity)

		relationships: list[ExtractedRelationship] = []
		seen: set[tuple[str, str, str, str]] = set()
		for chunk in chunks:
			chunk_id = str(chunk.get("chunk_id", ""))
			document = str(chunk.get("document_id", ""))
			text = " ".join(
				str(chunk.get(field, ""))
				for field in ("section", "subsection", "text")
				if chunk.get(field)
			)
			chunk_entities = self._entities_in_chunk(
				text,
				entities,
				entities_by_chunk.get(chunk_id, []),
			)
			document_entities = [
				entity for entity in chunk_entities if entity.get("entity_type") == "DOCUMENT"
			]
			document_target = self._document_target(document, document_entities, entities)
			non_document = [
				entity for entity in chunk_entities if entity.get("entity_type") != "DOCUMENT"
			]

			for entity in non_document:
				self._add(
					relationships,
					seen,
					entity["entity_id"],
					"APPEARS_IN",
					document_target,
					document,
				)
				for document_entity in document_entities:
					self._add(
						relationships,
						seen,
						document_entity["entity_id"],
						"DESCRIBES",
						entity["entity_id"],
						document,
					)

			for source_entity in non_document:
				if source_entity.get("entity_type") in {
					"UNIT",
					"EQUIPMENT",
					"INSTRUMENT",
					"CONTROL_LOOP",
					"VALVE",
				}:
					for parameter in non_document:
						if parameter.get("entity_type") == "PARAMETER":
							self._add(
								relationships,
								seen,
								source_entity["entity_id"],
								"HAS_PARAMETER",
								parameter["entity_id"],
								document,
							)

			parameters = [
				entity for entity in non_document if entity.get("entity_type") == "PARAMETER"
			]
			values = self._values(text)
			limits = self._limits(text)
			for parameter in parameters:
				for value in values:
					self._add(
						relationships,
						seen,
						parameter["entity_id"],
						"HAS_VALUE",
						value,
						document,
					)
				for limit in limits:
					self._add(
						relationships,
						seen,
						parameter["entity_id"],
						"HAS_LIMIT",
						limit,
						document,
					)

		logger.info(
			"Extracted %d unique relationships from %d chunks",
			len(relationships),
			len(chunks),
		)
		return relationships

	def process_file(
		self,
		chunk_path: str | Path,
		entity_path: str | Path,
		output_dir: str | Path = "data/processed/relationships",
	) -> Path:
		"""Extract relationships from one chunk file and its entity file."""
		chunk_source = Path(chunk_path)
		entity_source = Path(entity_path)
		try:
			chunks = json.loads(chunk_source.read_text(encoding="utf-8"))
			entities = json.loads(entity_source.read_text(encoding="utf-8"))
			if not isinstance(chunks, list) or not isinstance(entities, list):
				raise ValueError("Chunks and entities JSON must contain lists")
			relationships = self.extract_relationships(chunks, entities)
			destination_dir = Path(output_dir)
			destination_dir.mkdir(parents=True, exist_ok=True)
			output_path = destination_dir / f"{chunk_source.stem}_relationships.json"
			output_path.write_text(
				json.dumps(relationships, indent=2, ensure_ascii=False),
				encoding="utf-8",
			)
			logger.info("Saved relationships to %s", output_path)
			return output_path
		except Exception:
			logger.exception("Unable to extract relationships from %s", chunk_source)
			raise

	def process_all_documents(
		self,
		chunks_dir: str | Path = "data/processed/chunks",
		entities_dir: str | Path = "data/processed/entities",
		output_dir: str | Path = "data/processed/relationships",
	) -> list[Path]:
		"""Extract relationships for every matching chunk/entity document pair."""
		chunk_directory = Path(chunks_dir)
		entity_directory = Path(entities_dir)
		if not chunk_directory.is_dir():
			raise FileNotFoundError(f"Chunk directory does not exist: {chunk_directory}")
		if not entity_directory.is_dir():
			raise FileNotFoundError(f"Entity directory does not exist: {entity_directory}")

		output_paths: list[Path] = []
		for chunk_path in sorted(chunk_directory.glob("*.json")):
			entity_path = entity_directory / f"{chunk_path.stem}_entities.json"
			if not entity_path.is_file():
				logger.warning("Skipping chunk without matching entities: %s", chunk_path)
				continue
			output_paths.append(self.process_file(chunk_path, entity_path, output_dir))
		return output_paths

	@staticmethod
	def _compile(pattern: str | Pattern[str]) -> Pattern[str]:
		return re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern

	@staticmethod
	def _document_target(
		document: str,
		document_entities: list[dict[str, Any]],
		all_entities: list[dict[str, Any]],
	) -> str:
		for entity in all_entities:
			if (
				entity.get("entity_type") == "DOCUMENT"
				and str(entity.get("name", "")).casefold() == document.casefold()
			):
				return str(entity["entity_id"])
		if document_entities:
			return str(document_entities[0]["entity_id"])
		return f"document:{document.strip().lower().replace(' ', '-')}"

	def _values(self, text: str) -> list[str]:
		return list(dict.fromkeys(match.group(0).strip() for match in self.value_pattern.finditer(text)))

	def _limits(self, text: str) -> list[str]:
		limits: list[str] = []
		for value_match in self.value_pattern.finditer(text):
			prefix = text[max(0, value_match.start() - 60) : value_match.start()]
			if self.limit_pattern.search(prefix + value_match.group(0)):
				limits.append(value_match.group(0).strip())
		return list(dict.fromkeys(limits))

	@staticmethod
	def _entities_in_chunk(
		text: str,
		all_entities: list[dict[str, Any]],
		chunk_entities: list[dict[str, Any]],
	) -> list[dict[str, Any]]:
		"""Return entities whose complete names occur in this chunk."""
		matched: dict[str, dict[str, Any]] = {
			str(entity["entity_id"]): entity for entity in chunk_entities
		}
		for entity in all_entities:
			name = str(entity.get("name", "")).strip()
			name_pattern = re.escape(name).replace(r"\-", r"[- ]")
			if name and re.search(rf"(?<!\w){name_pattern}(?!\w)", text, re.IGNORECASE):
				matched[str(entity["entity_id"])] = entity
		return list(matched.values())

	@staticmethod
	def _add(
		relationships: list[ExtractedRelationship],
		seen: set[tuple[str, str, str, str]],
		source: str,
		relationship: str,
		target: str,
		document: str,
	) -> None:
		key = (source, relationship, target, document)
		if not source or not target or key in seen:
			return
		seen.add(key)
		relationships.append(
			{
				"source": source,
				"relationship": relationship,
				"target": target,
				"document": document,
			}
		)


def process_all_documents(
	chunks_dir: str | Path = "data/processed/chunks",
	entities_dir: str | Path = "data/processed/entities",
	output_dir: str | Path = "data/processed/relationships",
) -> list[Path]:
	"""Extract relationships from all matching chunk and entity files."""
	return RelationshipExtractor().process_all_documents(chunks_dir, entities_dir, output_dir)
