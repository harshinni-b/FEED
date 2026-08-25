from fastapi.testclient import TestClient

from app import app
from src.api.routes import get_runtime


class FakeRuntime:
	def __init__(self) -> None:
		self.findings = []
		self.findings_repository = FakeFindingsRepository()
		self.change_impact = type(
			"Impact",
			(),
			{
				"analyze": lambda _, entity, hops: {
					"entity": entity,
					"affected_assets": ["TCV-401"],
					"affected_documents": ["DOC8"],
					"impact_radius": {"max_hops": hops, "by_hop": {
						"0": {"count": 1, "entities": ["R-401"]},
						"1": {"count": 4, "entities": ["TCV-401", "DOC8", "pressure", "18 bar"]},
					}},
				}
			},
		)()

	def analyze(self, query: str) -> dict:
		self.findings = [{
			"finding_id": "F-1",
			"title": "Temperature limit",
			"severity": "HIGH",
			"status": "OPEN",
			"affected_assets": ["R-401"],
			"recommendation": "Review SIF-05.",
			"evidence": [{"chunk_id": "DOC8:001"}],
		}]
		if self.findings_repository.get_finding("F-1") is None:
			self.findings_repository.save_finding(self.findings[0])
		return {
			"query": query,
			"intent": "consistency_assurance",
			"retrieval_metadata": {"retrieval_mode": "local_graph_keyword"},
			"graph_context": {"nodes": [{"entity_id": "equipment:r-401"}], "relationships": [], "documents": []},
			"evidence": [{"chunk_id": "DOC8:001"}],
			"assurance_results": [{"check": "Temperature Limit", "status": "FAIL"}],
			"reasoning_output": {"recommendation": "Review SIF-05."},
			"findings": self.findings,
			"executed_nodes": ["retrieve_context", "build_findings"],
			"errors": [],
		}

	def graph_context(self, entity: str, depth: int = 1):
		if entity.casefold() == "r-401":
			return (
				{"entity_id": "equipment:r-401", "name": "R-401", "entity_type": "EQUIPMENT"},
				{
					"entity_id": "equipment:r-401",
					"nodes": [
						{"entity_id": "equipment:r-401", "name": "R-401", "entity_type": "EQUIPMENT"},
						{"entity_id": "valve:tcv-401", "name": "TCV-401", "entity_type": "VALVE"},
						{"entity_id": "document:doc8", "name": "DOC8", "entity_type": "DOCUMENT"},
						{"entity_id": "parameter:pressure", "name": "pressure", "entity_type": "PARAMETER"},
						{"entity_id": "18 bar", "name": "18 bar", "entity_type": "VALUE"},
					],
					"relationships": [
						{"source": "equipment:r-401", "target": "document:doc8", "relationship": "APPEARS_IN", "document": "DOC8"},
						{"source": "equipment:r-401", "target": "parameter:pressure", "relationship": "HAS_PARAMETER", "document": "DOC8"},
						{"source": "parameter:pressure", "target": "18 bar", "relationship": "HAS_VALUE", "document": "DOC8"},
					],
					"documents": ["DOC8"],
				},
			)
		return None


class FakeFindingsRepository:
	def __init__(self) -> None:
		self.records = {}

	def save_finding(self, finding):
		self.records[finding["finding_id"]] = {**finding}
		return self.records[finding["finding_id"]]

	def get_finding(self, finding_id):
		finding = self.records.get(finding_id)
		return {**finding} if finding else None

	def list_findings(self, status=None, severity=None):
		return [
			{**finding}
			for finding in self.records.values()
			if (status is None or finding.get("status") == status.upper())
			and (severity is None or finding.get("severity") == severity.upper())
		]

	def update_status(self, finding_id, status, reviewer=None, comment=None):
		if finding_id not in self.records:
			raise KeyError(f"Finding not found: {finding_id}")
		finding = self.records[finding_id]
		finding["status"] = status
		finding.setdefault("review_history", []).append({"status": status, "reviewer": reviewer, "comment": comment, "timestamp": "2026-01-01T00:00:00+00:00"})
		return {**finding}

	def add_comment(self, finding_id, reviewer, comment):
		if finding_id not in self.records:
			raise KeyError(f"Finding not found: {finding_id}")
		finding = self.records[finding_id]
		finding.setdefault("review_history", []).append({"status": finding["status"], "reviewer": reviewer, "comment": comment, "timestamp": "2026-01-01T00:00:00+00:00"})
		return {**finding}

	def get_review_history(self, finding_id):
		if finding_id not in self.records:
			raise KeyError(f"Finding not found: {finding_id}")
		return list(self.records[finding_id].get("review_history", []))


runtime = FakeRuntime()
app.dependency_overrides[get_runtime] = lambda: runtime
client = TestClient(app)


def test_analyze_returns_complete_investigation_data() -> None:
	response = client.post("/api/analyze", json={"query": "Check R-401 temperature"})

	assert response.status_code == 200
	body = response.json()
	assert body["evidence"] == [{"chunk_id": "DOC8:001"}]
	assert body["findings"][0]["finding_id"] == "F-1"
	assert body["assurance_results"][0]["status"] == "FAIL"
	assert body["recommendations"] == ["Review SIF-05."]
	assert body["graph_context"] == {"nodes": [{"entity_id": "equipment:r-401"}], "relationships": [], "documents": []}


def test_findings_returns_latest_investigation_findings() -> None:
	client.post("/api/analyze", json={"query": "Check R-401"})
	response = client.get("/api/findings")

	assert response.status_code == 200
	assert response.json()["findings"][0]["finding_id"] == "F-1"


def test_findings_filter_and_detail_include_review_history() -> None:
	client.post("/api/analyze", json={"query": "Check R-401"})
	filtered = client.get("/api/findings", params={"status": "OPEN", "severity": "HIGH"})
	detail = client.get("/api/findings/F-1")

	assert filtered.status_code == 200
	assert [finding["finding_id"] for finding in filtered.json()["findings"]] == ["F-1"]
	assert detail.status_code == 200
	assert detail.json()["finding"]["review_history"] == []


def test_review_and_comment_are_persisted_for_a_known_finding() -> None:
	client.post("/api/analyze", json={"query": "Check R-401"})
	review = client.patch("/api/findings/F-1/review", json={
		"status": "ACCEPTED", "reviewer": "Engineer", "comment": "Validated against source documents.",
	})
	comment = client.post("/api/findings/F-1/comments", json={
		"reviewer": "Engineer", "comment": "Additional review is required.",
	})

	assert review.status_code == 200
	assert review.json()["finding"]["status"] == "ACCEPTED"
	assert review.json()["finding"]["review_history"][0]["reviewer"] == "Engineer"
	assert comment.status_code == 200
	assert len(comment.json()["finding"]["review_history"]) == 2


def test_review_rejects_invalid_status_and_unknown_findings() -> None:
	invalid = client.patch("/api/findings/F-1/review", json={"status": "PENDING"})
	missing = client.get("/api/findings/F-missing")

	assert invalid.status_code == 422
	assert missing.status_code == 404


def test_graph_resolves_tag_and_returns_context() -> None:
	client.post("/api/analyze", json={"query": "Check R-401"})
	response = client.get("/api/graph/R-401", params={"depth": 1})

	assert response.status_code == 200
	body = response.json()
	assert body["requested_entity"] == "R-401"
	assert body["resolved_entity"]["entity_id"] == "equipment:r-401"
	assert body["nodes"]
	assert {node["entity_type"] for node in body["nodes"]} == {"EQUIPMENT", "VALVE", "DOCUMENT"}
	assert {node["entity_type"] for node in body["context_nodes"]} == {"PARAMETER", "VALUE"}
	assert len(body["relationships"]) == 3
	assert body["relationships"][0] == {"source": "equipment:r-401", "target": "document:doc8", "relationship_type": "APPEARS_IN", "document": "DOC8"}
	assert body["documents"] == ["DOC8"]
	assert body["related_findings"][0]["finding_id"] == "F-1"

	expanded = client.get("/api/graph/R-401", params={"depth": 1, "include_context": True}).json()
	assert expanded["context_included"] is True
	assert {node["entity_type"] for node in expanded["nodes"]} == {"EQUIPMENT", "VALVE", "DOCUMENT", "PARAMETER", "VALUE"}
	assert expanded["relationships"] == body["relationships"]


def test_graph_returns_not_found_for_unknown_entity() -> None:
	response = client.get("/api/graph/NOT-A-TAG")

	assert response.status_code == 404


def test_graph_rejects_depth_above_demo_limit() -> None:
	response = client.get("/api/graph/R-401", params={"depth": 4})

	assert response.status_code == 422


def test_impact_analysis_delegates_to_existing_engine() -> None:
	client.post("/api/analyze", json={"query": "Check R-401"})
	response = client.post("/api/impact-analysis", json={
		"entity": "R-401",
		"proposed_change": "Change Pass 1 trip setpoint from 620 C to 625 C",
		"hops": 2,
	})

	assert response.status_code == 200
	body = response.json()
	assert body["entity"] == "R-401"
	assert body["proposed_change"].startswith("Change Pass 1")
	assert body["affected_assets"] == ["TCV-401"]
	assert body["affected_relationships"][0]["relationship_type"] == "APPEARS_IN"
	assert body["assurance_results"][0]["impact_radius"]["max_hops"] == 2
	assert body["impact_radius"]["by_hop"]["1"]["entities"] == ["TCV-401", "DOC8"]
	assert body["expanded_impact_radius"]["by_hop"]["1"]["entities"] == ["TCV-401", "DOC8", "pressure", "18 bar"]
	assert {node["entity_type"] for node in body["context_nodes"]} == {"PARAMETER", "VALUE"}
	assert len(body["affected_relationships"]) == 3
	assert body["related_findings"][0]["finding_id"] == "F-1"
	assert body["review_required"] is True


def test_impact_analysis_validates_proposed_change() -> None:
	response = client.post("/api/impact-analysis", json={"entity": "R-401", "proposed_change": ""})

	assert response.status_code == 422


def test_analyze_rejects_blank_query_with_clear_validation_error() -> None:
	response = client.post("/api/analyze", json={"query": ""})

	assert response.status_code == 422
	assert response.json()["detail"][0]["loc"] == ["body", "query"]
