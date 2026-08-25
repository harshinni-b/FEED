"""DOCX ingestion for the EDOCA structured extraction stage."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P

logger = logging.getLogger(__name__)


class DocumentParseError(RuntimeError):
	"""Raised when a DOCX document cannot be parsed."""


class DocumentParser:
	"""Parse DOCX files into JSON-serializable engineering document records."""

	def parse_document(self, path: str | Path) -> dict[str, Any]:
		"""Extract metadata, headings, sections, paragraphs, and tables from a DOCX."""
		document_path = Path(path)
		try:
			document = Document(document_path)
			metadata = self._extract_metadata(document, document_path)
			headings: list[dict[str, Any]] = []
			paragraphs: list[dict[str, Any]] = []
			tables: list[dict[str, Any]] = []
			sections: list[dict[str, Any]] = []
			current_section: dict[str, Any] = self._new_section(None, 0)
			sections.append(current_section)

			for block in self._iter_block_items(document):
				if isinstance(block, Paragraph):
					text = block.text.strip()
					if not text:
						continue
					style_name = block.style.name if block.style else ""
					heading_level = self._heading_level(style_name)
					paragraph = {
						"text": text,
						"style": style_name,
					}
					paragraphs.append(paragraph)
					if heading_level is not None:
						heading = {"text": text, "level": heading_level}
						headings.append(heading)
						current_section = self._new_section(heading, heading_level)
						sections.append(current_section)
					else:
						current_section["paragraphs"].append(paragraph)
				else:
					table = self._extract_table(block, len(tables))
					tables.append(table)
					current_section["tables"].append(table)

			sections = [
				section
				for section in sections
				if section["heading"] is not None
				or section["paragraphs"]
				or section["tables"]
			]
			return {
				"filename": document_path.name,
				"metadata": metadata,
				"headings": headings,
				"sections": sections,
				"paragraphs": paragraphs,
				"tables": tables,
			}
		except Exception as exc:
			logger.exception("Unable to parse DOCX: %s", document_path)
			raise DocumentParseError(f"Unable to parse {document_path}") from exc

	def process_all_documents(
		self,
		raw_dir: str | Path,
		output_dir: str | Path = "data/extracted",
		*,
		strict: bool = False,
	) -> list[Path]:
		"""Parse every DOCX in ``raw_dir`` and write one JSON file per document."""
		source_dir = Path(raw_dir)
		destination_dir = Path(output_dir)
		if not source_dir.is_dir():
			raise FileNotFoundError(f"DOCX source directory does not exist: {source_dir}")

		destination_dir.mkdir(parents=True, exist_ok=True)
		output_paths: list[Path] = []
		for document_path in sorted(source_dir.glob("*.docx")):
			try:
				record = self.parse_document(document_path)
				output_path = destination_dir / f"{document_path.stem}.json"
				output_path.write_text(
					json.dumps(record, indent=2, ensure_ascii=False),
					encoding="utf-8",
				)
				output_paths.append(output_path)
				logger.info("Extracted %s to %s", document_path.name, output_path)
			except DocumentParseError:
				if strict:
					raise
				logger.error("Skipping document after parse failure: %s", document_path)
		return output_paths

	@staticmethod
	def _extract_metadata(document: DocumentObject, path: Path) -> dict[str, Any]:
		properties = document.core_properties
		values = {
			"author": properties.author,
			"category": properties.category,
			"comments": properties.comments,
			"created": properties.created,
			"identifier": properties.identifier,
			"keywords": properties.keywords,
			"last_modified_by": properties.last_modified_by,
			"last_printed": properties.last_printed,
			"modified": properties.modified,
			"revision": properties.revision,
			"subject": properties.subject,
			"title": properties.title,
		}
		return {
			"source_path": str(path),
			"core_properties": {
				key: value.isoformat() if isinstance(value, (date, datetime)) else value
				for key, value in values.items()
				if value not in (None, "")
			},
		}

	@staticmethod
	def _heading_level(style_name: str) -> int | None:
		if not style_name.lower().startswith("heading"):
			return None
		try:
			return int(style_name.split()[-1])
		except (ValueError, IndexError):
			return 1

	@staticmethod
	def _new_section(
		heading: dict[str, Any] | None,
		level: int,
	) -> dict[str, Any]:
		return {"heading": heading, "level": level, "paragraphs": [], "tables": []}

	@staticmethod
	def _extract_table(table: Table, index: int) -> dict[str, Any]:
		return {
			"index": index,
			"rows": [[cell.text for cell in row.cells] for row in table.rows],
		}

	@staticmethod
	def _iter_block_items(parent: DocumentObject | _Cell) -> Iterator[Paragraph | Table]:
		"""Yield body paragraphs and tables in their original document order."""
		parent_element = parent.element.body if isinstance(parent, DocumentObject) else parent._tc
		for child in parent_element.iterchildren():
			if isinstance(child, CT_P):
				yield Paragraph(child, parent)
			elif isinstance(child, CT_Tbl):
				yield Table(child, parent)


def process_all_documents(
	raw_dir: str | Path,
	output_dir: str | Path = "data/extracted",
	*,
	strict: bool = False,
) -> list[Path]:
	"""Parse all DOCX files in ``raw_dir`` and write their extracted JSON files."""
	return DocumentParser().process_all_documents(raw_dir, output_dir, strict=strict)
