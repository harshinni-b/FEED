"""Shared state contract for the EDOCA orchestration workflow."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class EDOCAState(TypedDict):
	"""State passed between EDOCA workflow nodes."""

	query: str
	intent: str
	selected_entities: list[str]
	evidence: list[dict]
	graph_context: dict
	retrieval_metadata: dict
	assurance_results: Annotated[list[dict], operator.add]
	reasoning_output: dict
	findings: Annotated[list[dict], operator.add]
	change_impact_requested: bool
	executed_nodes: Annotated[list[str], operator.add]
	errors: Annotated[list[str], operator.add]