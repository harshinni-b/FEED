"""Hierarchy-preserving chunking for extracted engineering documents."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, TypedDict

logger = logging.getLogger(__name__)


class EngineeringChunk(TypedDict):
	"""Schema for one paragraph or table engineering chunk."""

	chunk_id: str
	document_id: str
	document_type: str
	section: str
	subsection: str
	text: str
	source_type: str
	metadata: dict[str, Any]


class EngineeringChunker:
	"""Create one searchable chunk per source paragraph or table."""

	def chunk_document(self, document: Mapping[str, Any]) -> list[EngineeringChunk]:
		"""Convert one extracted document record into hierarchy-aware chunks."""
		filename = str(document.get("filename", "document"))
		document_id = Path(filename).stem
		document_type = self._document_type(filename)
		chunks: list[EngineeringChunk] = []
		chunk_number = 0

		sections = document.get("sections", [])
		if not isinstance(sections, list):
			raise ValueError("Extracted document sections must be a list")

		current_section = ""
		current_subsection = ""
		for section_record in sections:
			if not isinstance(section_record, Mapping):
				raise ValueError("Each extracted section must be an object")
			heading = section_record.get("heading")
			level = int(section_record.get("level", 0))
			if isinstance(heading, Mapping):
				heading_text = str(heading.get("text", "")).strip()
				heading_level = int(heading.get("level", level))
				if heading_level <= 1:
					current_section = heading_text
					current_subsection = ""
				else:
					current_subsection = heading_text

			for paragraph in section_record.get("paragraphs", []):
				if not isinstance(paragraph, Mapping):
					raise ValueError("Each extracted paragraph must be an object")
				text = str(paragraph.get("text", "")).strip()
				if text:
					chunks.append(
						self._paragraph_chunk(
							chunk_number,
							document_id,
							document_type,
							current_section,
							current_subsection,
							text,
							paragraph,
						)
					)
					chunk_number += 1

			for table in section_record.get("tables", []):
				if not isinstance(table, Mapping):
					raise ValueError("Each extracted table must be an object")
				rows = table.get("rows", [])
				if not isinstance(rows, list):
					raise ValueError("Extracted table rows must be a list")
				chunks.append(
					self._table_chunk(
						chunk_number,
						document_id,
						document_type,
						current_section,
						current_subsection,
						rows,
						table,
					)
				)
				chunk_number += 1

		logger.info("Created %d engineering chunks for %s", len(chunks), filename)
		return chunks

	def process_file(
		self,
		input_path: str | Path,
		output_dir: str | Path = "data/processed/chunks",
	) -> Path:
		"""Chunk one extracted JSON document and save its chunk list."""
		source_path = Path(input_path)
		destination_dir = Path(output_dir)
		try:
			document = json.loads(source_path.read_text(encoding="utf-8"))
			chunks = self.chunk_document(document)
			destination_dir.mkdir(parents=True, exist_ok=True)
			output_path = destination_dir / f"{source_path.stem}_chunks.json"
			output_path.write_text(
				json.dumps(chunks, indent=2, ensure_ascii=False),
				encoding="utf-8",
			)
			logger.info("Saved chunks to %s", output_path)
			return output_path
		except Exception:
			logger.exception("Unable to chunk extracted document: %s", source_path)
			raise

	def process_all_documents(
		self,
		input_dir: str | Path = "data/extracted",
		output_dir: str | Path = "data/processed/chunks",
	) -> list[Path]:
		"""Chunk every extracted JSON document and save one chunk file per document."""
		source_dir = Path(input_dir)
		if not source_dir.is_dir():
			raise FileNotFoundError(f"Extracted document directory does not exist: {source_dir}")
		return [
			self.process_file(path, output_dir)
			for path in sorted(source_dir.glob("*.json"))
		]

	@staticmethod
	def _document_type(filename: str) -> str:
		"""Derive a stable document type from the source filename."""
		return Path(filename).stem.split("_", 1)[-1].replace(" 1", "")

	@staticmethod
	def _base_chunk(
		number: int,
		document_id: str,
		document_type: str,
		section: str,
		subsection: str,
		text: str,
		source_type: str,
		metadata: dict[str, Any],
	) -> EngineeringChunk:
		return {
			"chunk_id": f"{document_id}:chunk:{number:04d}",
			"document_id": document_id,
			"document_type": document_type,
			"section": section,
			"subsection": subsection,
			"text": text,
			"source_type": source_type,
			"metadata": metadata,
		}

	def _paragraph_chunk(
		self,
		number: int,
		document_id: str,
		document_type: str,
		section: str,
		subsection: str,
		text: str,
		paragraph: Mapping[str, Any],
	) -> EngineeringChunk:
		return self._base_chunk(
			number,
			document_id,
			document_type,
			section,
			subsection,
			text,
			"paragraph",
			{"style": paragraph.get("style", "")},
		)

	def _table_chunk(
		self,
		number: int,
		document_id: str,
		document_type: str,
		section: str,
		subsection: str,
		rows: list[Any],
		table: Mapping[str, Any],
	) -> EngineeringChunk:
		return self._base_chunk(
			number,
			document_id,
			document_type,
			section,
			subsection,
			"\n".join(" | ".join(str(cell) for cell in row) for row in rows),
			"table",
			{"table_index": table.get("index"), "rows": rows},
		)


def process_all_documents(
	input_dir: str | Path = "data/extracted",
	output_dir: str | Path = "data/processed/chunks",
) -> list[Path]:
	"""Chunk all extracted documents using the default engineering chunker."""
	return EngineeringChunker().process_all_documents(input_dir, output_dir)
