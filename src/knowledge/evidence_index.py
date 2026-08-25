"""Deterministic evidence indexing for extracted EDOCA chunks."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Protocol, TypedDict

logger = logging.getLogger(__name__)


class EvidenceChunk(TypedDict):
	"""Searchable evidence record retained from an engineering chunk."""

	chunk_id: str
	document_id: str
	document_type: str
	section: str
	subsection: str
	text: str
	source_type: str


class EvidenceIndexPort(Protocol):
	"""Adapter contract for replacing local search with Azure AI Search."""

	def search_by_keyword(self, query: str) -> list[EvidenceChunk]:
		"""Search indexed evidence by keyword or phrase."""


class EvidenceIndex:
	"""Build and query a deterministic local index of engineering chunks."""

	def __init__(self) -> None:
		self.records: list[EvidenceChunk] = []
		self._by_chunk_id: dict[str, EvidenceChunk] = {}

	def index_chunks(
		self,
		input_dir: str | Path = "data/processed/chunks",
		output_dir: str | Path = "data/processed/evidence",
	) -> list[EvidenceChunk]:
		"""Load chunk JSON files, retain evidence fields, and persist the index."""
		source_dir = Path(input_dir)
		if not source_dir.is_dir():
			raise FileNotFoundError(f"Chunk directory does not exist: {source_dir}")

		records: list[EvidenceChunk] = []
		for path in sorted(source_dir.glob("*.json")):
			try:
				loaded = json.loads(path.read_text(encoding="utf-8"))
				if not isinstance(loaded, list):
					raise ValueError("Chunk JSON must contain a list")
				for chunk in loaded:
					records.append(self._to_evidence_chunk(chunk))
			except Exception:
				logger.exception("Unable to index chunks from %s", path)
				raise

		self.records = list(dict.fromkeys(tuple(record.items()) for record in records))
		self.records = [dict(items) for items in self.records]
		self._by_chunk_id = {record["chunk_id"]: record for record in self.records}

		destination_dir = Path(output_dir)
		destination_dir.mkdir(parents=True, exist_ok=True)
		output_path = destination_dir / "index.json"
		output_path.write_text(
			json.dumps(self.records, indent=2, ensure_ascii=False),
			encoding="utf-8",
		)
		logger.info("Indexed %d evidence chunks to %s", len(self.records), output_path)
		return self.records

	def search_by_keyword(self, query: str) -> list[EvidenceChunk]:
		"""Return chunks containing all query terms, case-insensitively."""
		terms = self._terms(query)
		if not terms:
			return []
		return [
			record
			for record in self.records
			if all(term in self._search_text(record) for term in terms)
		]

	def search_by_entity(self, entity_name: str) -> list[EvidenceChunk]:
		"""Return chunks containing a complete engineering entity name."""
		return self._search_phrase(entity_name)

	def search_by_document(self, document_name: str) -> list[EvidenceChunk]:
		"""Return chunks belonging to a document ID or document name."""
		query = self._normalize(document_name)
		return [
			record
			for record in self.records
			if query in self._normalize(record["document_id"])
		]

	def search_by_section(self, section_name: str) -> list[EvidenceChunk]:
		"""Return chunks whose section or subsection contains the query."""
		query = self._normalize(section_name)
		return [
			record
			for record in self.records
			if query in self._normalize(record["section"])
			or query in self._normalize(record["subsection"])
		]

	def search_by_unit(self, unit_name: str) -> list[EvidenceChunk]:
		"""Return chunks containing a complete unit name."""
		return self._search_phrase(unit_name)

	def search_by_sif(self, sif_name: str) -> list[EvidenceChunk]:
		"""Return chunks containing a complete SIF name."""
		return self._search_phrase(sif_name)

	@staticmethod
	def _to_evidence_chunk(chunk: Any) -> EvidenceChunk:
		if not isinstance(chunk, dict):
			raise ValueError("Each chunk must be an object")
		source_type = str(chunk.get("source_type", ""))
		if source_type not in {"paragraph", "table"}:
			raise ValueError(f"Unsupported chunk source_type: {source_type}")
		return {
			"chunk_id": str(chunk.get("chunk_id", "")),
			"document_id": str(chunk.get("document_id", "")),
			"document_type": str(chunk.get("document_type", "")),
			"section": str(chunk.get("section", "")),
			"subsection": str(chunk.get("subsection", "")),
			"text": str(chunk.get("text", "")),
			"source_type": source_type,
		}

	@staticmethod
	def _normalize(value: str) -> str:
		return re.sub(r"\s+", " ", value).strip().casefold()

	@classmethod
	def _terms(cls, query: str) -> list[str]:
		return [cls._normalize(term) for term in query.split() if term.strip()]

	@classmethod
	def _search_text(cls, record: EvidenceChunk) -> str:
		return cls._normalize(
			" ".join(
				(record["section"], record["subsection"], record["text"])
			)
		)

	def _search_phrase(self, phrase: str) -> list[EvidenceChunk]:
		query = self._normalize(phrase)
		if not query:
			return []
		pattern = re.escape(query).replace(r"\ ", r"\s+")
		return [
			record
			for record in self.records
			if re.search(rf"(?<!\w){pattern}(?!\w)", self._search_text(record))
		]


def index_chunks(
	input_dir: str | Path = "data/processed/chunks",
	output_dir: str | Path = "data/processed/evidence",
) -> list[EvidenceChunk]:
	"""Index all extracted chunks using the default local evidence index."""
	return EvidenceIndex().index_chunks(input_dir, output_dir)
