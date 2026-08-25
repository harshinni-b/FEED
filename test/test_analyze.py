from src.orchestration.analyze import EDOCAAnalyzer, analyze


class FakeEvidenceIndex:
    def __init__(self) -> None:
        self.indexed = False

    def index_chunks(self) -> list[dict]:
        self.indexed = True
        return []

    def search_by_keyword(self, query: str) -> list[dict]:
        return [{
            "chunk_id": "c1",
            "document_id": "DOC2",
            "section": "UNIT 400",
            "subsection": "Pass 1 Temperature",
            "text": "Configured limit is 620°C; operating value is 621°C.",
            "source_type": "table",
        }] if query else []


class FakeGraph:
    class Nodes:
        def __call__(self, data=False):
            if data:
                return [("unit:400", {"name": "Unit-400", "entity_type": "UNIT"})]
            return ["unit:400"]

    def __init__(self) -> None:
        self.graph = type("Graph", (), {"nodes": self.Nodes()})()

    def build_graph(self) -> None:
        return None

    def get_graph_context(self, entity_id: str) -> dict:
        return {
            "entity_id": entity_id,
            "nodes": [{"entity_id": entity_id, "name": "Unit-400", "entity_type": "UNIT"}],
            "relationships": [],
        }


class FakeAssurance:
    def validate(self, evidence):
        return [{
            "check": "Temperature Limit",
            "status": "FAIL",
            "severity": "HIGH",
            "actual": "621°C",
            "limit": "620°C",
            "finding": "Operating value exceeds configured limit",
        }]


class FakeConnectivity:
    def validate(self, graph_context):
        return [{"check": "Connectivity", "status": "FAIL", "severity": "HIGH", "finding": "Missing dependency"}]


class FakeOperationalIntent:
    def validate(self, evidence, graph_context):
        return [{"check": "Intent", "status": "FAIL", "severity": "MEDIUM", "finding": "Conflicting intent"}]


class FakeChangeImpact:
    def __init__(self):
        self.called = False

    def analyze(self, entity_id):
        self.called = True
        return {"entity": entity_id, "affected_assets": [], "affected_documents": [], "impact_radius": {}}


class FakeReasoner:
    def __init__(self):
        self.assurance_results = None

    def reason(self, question, graph_context, evidence, assurance_results):
        assert question
        assert graph_context["nodes"]
        assert evidence[0]["chunk_id"] == "c1"
        assert assurance_results[0]["status"] == "FAIL"
        self.assurance_results = assurance_results
        return {
            "finding_title": "Temperature limit exceeded",
            "severity": "HIGH",
            "confidence": 0.99,
            "root_cause": "Operating value exceeds supplied limit.",
            "reasoning": "621°C is above 620°C.",
            "recommendation": "Investigate before operation.",
            "affected_assets": ["Unit-400"],
        }


class FakeBuilder:
    def __init__(self):
        self.assurance_results = None

    def build(self, evidence, graph_context, assurance_results, reasoning=None, query=""):
        self.assurance_results = assurance_results
        return [{
            "finding_id": "F-test",
            "title": "Temperature Limit",
            "severity": "HIGH",
            "status": "OPEN",
            "affected_assets": ["Unit-400"],
            "root_cause": assurance_results[0]["finding"],
			"reasoning": reasoning.get("reasoning", ""),
            "evidence": evidence,
            "recommendation": "Investigate.",
            "confidence": 1.0,
        }]


def test_analyze_runs_full_pipeline_and_returns_finding() -> None:
    reasoner = FakeReasoner()
    builder = FakeBuilder()
    analyzer = EDOCAAnalyzer(
        evidence_index=FakeEvidenceIndex(),
        graph=FakeGraph(),
        assurance_engine=FakeAssurance(),
        connectivity_engine=FakeConnectivity(),
        operational_intent_engine=FakeOperationalIntent(),
        reasoner=reasoner,
        finding_builder=builder,
    )

    finding = analyzer.analyze("Is there a consistency issue with Unit 400 temperature?")

    assert finding["finding_id"] == "F-test"
    assert finding["title"] == "Temperature Limit"
    assert finding["reasoning"] == "621°C is above 620°C."
    assert finding["status"] == "OPEN"
    assert len(reasoner.assurance_results) == 1
    assert len(builder.assurance_results) == 3


def test_change_impact_is_conditional() -> None:
    change_impact = FakeChangeImpact()
    analyzer = EDOCAAnalyzer(
        evidence_index=FakeEvidenceIndex(),
        graph=FakeGraph(),
        assurance_engine=FakeAssurance(),
        connectivity_engine=FakeConnectivity(),
        operational_intent_engine=FakeOperationalIntent(),
        change_impact_engine=change_impact,
        reasoner=FakeReasoner(),
        finding_builder=FakeBuilder(),
    )

    analyzer._get_reasoning = lambda query, graph_context, evidence, assurance: {
        "finding_title": "Temperature limit exceeded",
        "severity": "HIGH",
        "confidence": 1.0,
        "root_cause": "x",
        "reasoning": "x",
        "recommendation": "x",
        "affected_assets": ["Unit-400"],
    }
    analyzer.analyze("What is the impact if Unit 400 changes?")

    assert change_impact.called


def test_public_analyze_returns_complete_langgraph_state() -> None:
    state = analyze(
        "Is there a consistency issue with Unit 400 temperature?",
        evidence_index=FakeEvidenceIndex(),
        graph=FakeGraph(),
        assurance_engine=FakeAssurance(),
        connectivity_engine=FakeConnectivity(),
        operational_intent_engine=FakeOperationalIntent(),
        change_impact_engine=FakeChangeImpact(),
        reasoner=FakeReasoner(),
        finding_builder=FakeBuilder(),
    )

    assert set(state) == {
        "query", "intent", "retrieval_metadata", "assurance_results", "reasoning_output",
        "findings", "graph_context", "evidence", "executed_nodes", "errors",
    }
    assert state["query"].startswith("Is there")
    assert state["retrieval_metadata"]["retrieval_mode"] == "local_graph_keyword"
    assert state["findings"]
