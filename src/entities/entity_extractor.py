"""Configurable rule-based entity extraction for engineering chunks."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Pattern, TypedDict

logger = logging.getLogger(__name__)


class ExtractedEntity(TypedDict):
	"""Schema for an entity linked to its source chunk."""

	entity_id: str
	entity_type: str
	name: str
	source_chunk: str


DEFAULT_PATTERNS: dict[str, str] = {
	"UNIT": r"\b(?:UNIT|U|PASS)[ -]\d{1,5}[A-Z]?\b",
	"SIF": r"\bSIF-\d{1,5}[A-Z]?\b",
	"CONTROL_LOOP": r"\b(?:FIC|LIC|PIC|TIC|AIC|DIC|SIC|TSC|LSH|LSHH|PSH|PSHH|TSH|TSHH)-\d{1,5}[A-Z]?\b",
	"VALVE": r"\b(?:XV|FCV|LCV|TCV|PCV|PSV|SDV|BDV|MOV|HV)-\d{1,5}[A-Z]?\b",
	"INSTRUMENT": r"\b(?:AI|AT|FI|FIT|FT|LI|LIT|LT|MFM|PI|PIT|PT|TI|TIT|TT|ZV)(?:-[A-Z]{1,5})?-\d{1,5}[A-Z]?\b",
	"EQUIPMENT": r"\b(?:AG|BL|BU|C|D|E|H|HX|K|M|P|R|T|TK|V|WHB)-\d{1,5}[A-Z]?\b",
	"LINE": r"\b(?:LINE|L)-\d{1,6}[A-Z]?\b",
	"PARAMETER": r"\b(?:capacity|flow|pressure|temperature|level|thickness|density|concentration|power|duty|rate|volume)\b",
	"DOCUMENT": r"\b(?:[A-Z]{2,8}-){2,}[A-Z0-9]*\d[A-Z0-9-]*\b",
}

PARAMETER_CONTEXT_PATTERN = re.compile(
	r"\bPass[ -](\d{1,3})\s+(temperature|pressure|flow|level|concentration|power)\b",
	re.IGNORECASE,
)


class RuleBasedEntityExtractor:
	"""Extract engineering entities with configurable regular expressions."""

	def __init__(self, patterns: dict[str, str | Pattern[str]] | None = None) -> None:
		configured = patterns or DEFAULT_PATTERNS
		self.patterns: dict[str, Pattern[str]] = {
			entity_type: re.compile(pattern, re.IGNORECASE)
			if isinstance(pattern, str)
			else pattern
			for entity_type, pattern in configured.items()
		}

	def extract_entities(self, chunks: list[dict[str, Any]]) -> list[ExtractedEntity]:
		"""Extract and deduplicate entities from engineering chunks."""
		entities: list[ExtractedEntity] = []
		seen: set[tuple[str, str]] = set()
		for chunk in chunks:
			if not isinstance(chunk, dict):
				raise ValueError("Each engineering chunk must be an object")
			chunk_id = str(chunk.get("chunk_id", ""))
			text = " ".join(
				str(chunk.get(field, ""))
				for field in ("section", "subsection", "text")
				if chunk.get(field)
			)
			document_id = str(chunk.get("document_id", "")).strip()
			if document_id:
				self._append_entity(
					entities,
					seen,
					"DOCUMENT",
					document_id,
					chunk_id,
				)
			for match in PARAMETER_CONTEXT_PATTERN.finditer(text):
				self._append_entity(
					entities,
					seen,
					"PARAMETER",
					f"Pass-{match.group(1)} {match.group(2).title()}",
					chunk_id,
				)
			for entity_type, pattern in self.patterns.items():
				for match in pattern.finditer(text):
					name = match.group(0).strip()
					if entity_type == "UNIT":
						unit_match = re.fullmatch(r"(UNIT|U|PASS)[ -](\d{1,5}[A-Z]?)", name, re.IGNORECASE)
						if unit_match:
							prefix = "Pass" if unit_match.group(1).casefold() == "pass" else "Unit"
							name = f"{prefix}-{unit_match.group(2)}"
					self._append_entity(
						entities,
						seen,
						entity_type,
						name,
						chunk_id,
					)
		logger.info("Extracted %d unique entities from %d chunks", len(entities), len(chunks))
		return entities

	def process_file(
		self,
		input_path: str | Path,
		output_dir: str | Path = "data/processed/entities",
	) -> Path:
		"""Extract entities from one chunk JSON file and save its entity list."""
		source_path = Path(input_path)
		try:
			chunks = json.loads(source_path.read_text(encoding="utf-8"))
			if not isinstance(chunks, list):
				raise ValueError("Chunk JSON must contain a list")
			entities = self.extract_entities(chunks)
			destination_dir = Path(output_dir)
			destination_dir.mkdir(parents=True, exist_ok=True)
			output_path = destination_dir / f"{source_path.stem}_entities.json"
			output_path.write_text(
				json.dumps(entities, indent=2, ensure_ascii=False),
				encoding="utf-8",
			)
			logger.info("Saved entities to %s", output_path)
			return output_path
		except Exception:
			logger.exception("Unable to extract entities from %s", source_path)
			raise

	def process_all_documents(
		self,
		input_dir: str | Path = "data/processed/chunks",
		output_dir: str | Path = "data/processed/entities",
	) -> list[Path]:
		"""Extract entities from every chunk JSON file in an input directory."""
		source_dir = Path(input_dir)
		if not source_dir.is_dir():
			raise FileNotFoundError(f"Chunk directory does not exist: {source_dir}")
		return [
			self.process_file(path, output_dir)
			for path in sorted(source_dir.glob("*.json"))
		]

	@staticmethod
	def _append_entity(
		entities: list[ExtractedEntity],
		seen: set[tuple[str, str]],
		entity_type: str,
		name: str,
		source_chunk: str,
	) -> None:
		normalized_name = re.sub(r"\s+", " ", name).strip().upper()
		key = (entity_type, normalized_name)
		if not normalized_name or key in seen:
			return
		seen.add(key)
		entities.append(
			{
				"entity_id": f"{entity_type.lower()}:{normalized_name.lower().replace(' ', '-')}",
				"entity_type": entity_type,
				"name": name,
				"source_chunk": source_chunk,
			}
		)


def process_all_documents(
	input_dir: str | Path = "data/processed/chunks",
	output_dir: str | Path = "data/processed/entities",
) -> list[Path]:
	"""Extract entities from all chunk files using the default rule set."""
	return RuleBasedEntityExtractor().process_all_documents(input_dir, output_dir)
