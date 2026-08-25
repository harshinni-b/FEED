import operator
from typing import Annotated, get_args, get_origin, get_type_hints

from src.orchestration.state import EDOCAState


def test_edoca_state_declares_full_workflow_contract() -> None:
	annotations = get_type_hints(EDOCAState, include_extras=True)

	assert set(annotations) == {
		"query",
		"intent",
		"selected_entities",
		"evidence",
		"graph_context",
		"retrieval_metadata",
		"assurance_results",
		"reasoning_output",
		"findings",
		"change_impact_requested",
		"executed_nodes",
		"errors",
	}
	assert annotations["query"] is str
	assert annotations["intent"] is str
	assert annotations["selected_entities"] == list[str]
	assert annotations["evidence"] == list[dict]
	assert annotations["graph_context"] is dict
	assert annotations["reasoning_output"] is dict
	assert annotations["change_impact_requested"] is bool


def test_append_only_fields_use_operator_add_reducers() -> None:
	annotations = get_type_hints(EDOCAState, include_extras=True)

	for field in ("assurance_results", "findings", "executed_nodes", "errors"):
		annotation = annotations[field]
		assert get_origin(annotation) is Annotated
		assert operator.add in get_args(annotation)


def test_append_only_reducers_preserve_updates() -> None:
	annotations = get_type_hints(EDOCAState, include_extras=True)

	for field, initial, update in (
		("assurance_results", [{"check": "attribute"}], [{"check": "connectivity"}]),
		("findings", [{"id": "F-1"}], [{"id": "F-2"}]),
		("executed_nodes", ["retrieve"], ["assure"]),
		("errors", ["first"], ["second"]),
	):
		reducer = get_args(annotations[field])[1]
		assert reducer(initial, update) == initial + update