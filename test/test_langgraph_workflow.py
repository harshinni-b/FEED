from src.orchestration.langgraph_workflow import build_edoca_graph, run_edoca_graph


class FakeEvidenceIndex:
    def __init__(self):
        self.records = []

    def index_chunks(self):
        self.records = [{
            "chunk_id": "c1",
            "document_id": "DOC-1",
            "document_type": "process",
            "section": "Unit-400",
            "subsection": "Temperature",
            "text": "Operating value is 621 C; configured limit is 620 C.",
            "source_type": "table",
        }]
        return self.records

    def search_by_keyword(self, query):
        return self.records if query else []


class FakeGraph:
    class Nodes:
        def __call__(self, data=False):
            if data:
                return [("unit:400", {"name": "Unit-400", "entity_type": "UNIT"})]
            return ["unit:400"]

    def __init__(self):
        self.graph = type("Graph", (), {"nodes": self.Nodes(), "number_of_nodes": lambda _: 1})()

    def build_graph(self):
        return None

    def get_graph_context(self, entity_id):
        return {
            "entity_id": entity_id,
            "nodes": [{"entity_id": entity_id, "name": "Unit-400", "entity_type": "UNIT"}],
            "relationships": [],
        }


class FakeAttribute:
    def validate(self, evidence):
        return [{"check": "Temperature", "status": "FAIL", "severity": "HIGH", "actual": "621 C", "limit": "620 C", "finding": "Over limit"}]


class FakeConnectivity:
    def validate(self, context):
        return []


class FakeIntent:
    def validate(self, evidence, context):
        return []


class FakeChangeImpact:
    def __init__(self):
        self.called = False

    def analyze(self, entity):
        self.called = True
        return {"entity": entity, "affected_assets": [], "affected_documents": [], "impact_radius": {}}


class FakeReasoner:
    def reason(self, query, graph_context, evidence, assurance_results):
        return {
            "finding_title": "Temperature issue",
            "severity": "HIGH",
            "confidence": 0.9,
            "root_cause": "Value exceeds limit",
            "reasoning": "621 C is greater than 620 C.",
            "recommendation": "Investigate.",
            "affected_assets": ["Unit-400"],
        }


class FakeBuilder:
    def build(self, evidence, graph_context, assurance_results, reasoning, query=""):
        if not assurance_results:
            return []
        return [{"finding_id": "F-1", "title": reasoning["finding_title"]}]


def make_components(change_impact):
    return {
        "evidence_index": FakeEvidenceIndex(),
        "plant_graph": FakeGraph(),
        "attribute_engine": FakeAttribute(),
        "connectivity_engine": FakeConnectivity(),
        "operational_intent_engine": FakeIntent(),
        "change_impact_engine": change_impact,
        "reasoner": FakeReasoner(),
        "finding_builder": FakeBuilder(),
    }


def test_workflow_compiles_and_runs_without_openai_key():
    state = run_edoca_graph("Is Unit-400 temperature consistent?", **make_components(FakeChangeImpact()))

    assert state["errors"] == []
    assert state["findings"] == [{"finding_id": "F-1", "title": "Temperature issue"}]
    assert state["retrieval_metadata"]["retrieval_mode"] == "local_graph_keyword"
    assert state["executed_nodes"] == [
        "detect_intent",
        "retrieve_context",
        "run_attribute_assurance",
        "run_connectivity_assurance",
        "run_operational_intent_assurance",
        "reason_with_genai",
        "build_findings",
    ]


def test_change_intent_routes_through_change_impact():
    change_impact = FakeChangeImpact()
    state = run_edoca_graph("What happens if Unit-400 is replaced?", **make_components(change_impact))

    assert state["change_impact_requested"] is True
    assert change_impact.called is True
    assert "run_change_impact_assurance" in state["executed_nodes"]


def test_runtime_failures_are_captured():
    components = make_components(FakeChangeImpact())
    components["attribute_engine"] = type("FailingAttribute", (), {"validate": lambda self, evidence: (_ for _ in ()).throw(RuntimeError("boom"))})()

    state = run_edoca_graph("Check Unit-400", **components)

    assert state["errors"] == ["run_attribute_assurance: boom"]
