import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Network, RefreshCw } from "lucide-react";
import { getFindings, getGraphContext } from "../api/client";

const STATUSES = ["OPEN", "REVIEW", "ACCEPTED", "REJECTED", "CLOSED"];
const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

const normalized = value => String(value || "").trim().toUpperCase();

function assuranceType(finding) {
  return String(finding.assurance_type || finding.source_check || finding.check || finding.title || "Not available");
}

function evidenceDocuments(finding) {
  const documents = (finding.evidence || []).flatMap(record => {
    if (!record || typeof record !== "object") return [];
    return [record.document_id, record.document_type].filter(Boolean).map(String);
  });
  return [...new Set(documents)];
}

function distribution(items, keyForItem, orderedKeys = []) {
  const counts = new Map(orderedKeys.map(key => [key, 0]));
  items.forEach(item => {
    const key = keyForItem(item);
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()];
}

function MetricCard({ label, value, detail, tone = "blue", unavailable = false }) {
  return <article className={`command-metric ${tone} ${unavailable ? "unavailable" : ""}`}><span>{label}</span><strong>{unavailable ? "Not available." : value}</strong><small>{detail}</small></article>;
}

function DistributionCard({ title, items, total, available, loading }) {
  return <section className="command-card distribution-card"><div className="section-heading"><div><p className="eyebrow">LIVE FINDINGS DATA</p><h2>{title}</h2></div></div><div className="distribution-list">{loading ? <p>Loading API data…</p> : !available ? <p>Not available.</p> : items.length ? items.map(([label, count]) => <div key={label}><header><span>{label}</span><strong>{count}</strong></header><div><i style={{ width: `${total ? (count / total) * 100 : 0}%` }}></i></div></div>) : <p>No findings returned.</p>}</div></section>;
}

export default function CommandCenter() {
  const [findings, setFindings] = useState([]);
  const [graphScope, setGraphScope] = useState(null);
  const [graphScopeEntity, setGraphScopeEntity] = useState("");
  const [loading, setLoading] = useState(true);
  const [findingsAvailable, setFindingsAvailable] = useState(false);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ severity: "", document: "", assurance: "", status: "" });

  const loadData = async () => {
    setLoading(true);
    setFindingsAvailable(false);
    setError("");
    setGraphScope(null);
    setGraphScopeEntity("");
    try {
      const response = await getFindings();
      const records = Array.isArray(response.findings) ? response.findings : [];
      setFindings(records);
      setFindingsAvailable(true);
      const entity = records.flatMap(finding => finding.affected_assets || []).find(Boolean);
      if (entity) {
        setGraphScopeEntity(String(entity));
        try {
          setGraphScope(await getGraphContext(String(entity), 2));
        } catch {
          setGraphScope(null);
        }
      }
    } catch (requestError) {
      setFindings([]);
      setFindingsAvailable(false);
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const filterOptions = useMemo(() => ({
    documents: [...new Set(findings.flatMap(evidenceDocuments))].sort(),
    assuranceTypes: [...new Set(findings.map(assuranceType))].sort(),
  }), [findings]);

  const filteredFindings = useMemo(() => findings.filter(finding => {
    if (filters.severity && normalized(finding.severity) !== filters.severity) return false;
    if (filters.status && normalized(finding.status || "OPEN") !== filters.status) return false;
    if (filters.assurance && assuranceType(finding) !== filters.assurance) return false;
    if (filters.document && !evidenceDocuments(finding).includes(filters.document)) return false;
    return true;
  }), [filters, findings]);

  const statusDistribution = useMemo(() => distribution(findings, finding => normalized(finding.status || "OPEN"), STATUSES), [findings]);
  const assuranceDistribution = useMemo(() => distribution(findings, assuranceType), [findings]);
  const openFindings = findings.filter(finding => normalized(finding.status || "OPEN") === "OPEN").length;
  const highSeverity = findings.filter(finding => ["CRITICAL", "HIGH"].includes(normalized(finding.severity))).length;
  const corpusSummary = graphScope?.corpus_summary || graphScope?.metadata?.corpus_summary || {};
  const corpusDocuments = Number.isFinite(corpusSummary.total_documents) ? corpusSummary.total_documents : null;
  const corpusNodes = Number.isFinite(corpusSummary.total_nodes) ? corpusSummary.total_nodes : null;
  const corpusRelationships = Number.isFinite(corpusSummary.total_relationships) ? corpusSummary.total_relationships : null;

  const updateFilter = (name, value) => setFilters(current => ({ ...current, [name]: value }));

  return <div className="command-center">
    <section className="command-hero"><div><p className="eyebrow">EDOCA ASSET OVERVIEW</p><h2>Engineering assurance command center</h2><p>Live finding metrics and available Plant Knowledge Graph context.</p></div><button className="secondary" disabled={loading} onClick={loadData}>{loading ? <Activity className="spin" size={15}/> : <RefreshCw size={15}/>} Refresh API data</button></section>

    {error && <div className="command-error"><AlertTriangle size={15}/>{error}</div>}

    <section className="command-metrics">
      <MetricCard label="TOTAL DOCUMENTS" value={corpusDocuments} unavailable={corpusDocuments === null} detail="Corpus aggregate not exposed by graph API" tone="cyan"/>
      <MetricCard label="TOTAL GRAPH NODES" value={corpusNodes} unavailable={corpusNodes === null} detail="Corpus aggregate not exposed by graph API" tone="violet"/>
      <MetricCard label="TOTAL RELATIONSHIPS" value={corpusRelationships} unavailable={corpusRelationships === null} detail="Corpus aggregate not exposed by graph API" tone="blue"/>
      <MetricCard label="TOTAL FINDINGS" value={loading ? "…" : findings.length} unavailable={!loading && !findingsAvailable} detail="Persisted findings returned by API" tone="blue"/>
      <MetricCard label="OPEN FINDINGS" value={loading ? "…" : openFindings} unavailable={!loading && !findingsAvailable} detail="Status equals OPEN" tone="amber"/>
      <MetricCard label="HIGH-SEVERITY FINDINGS" value={loading ? "…" : highSeverity} unavailable={!loading && !findingsAvailable} detail="CRITICAL and HIGH severity" tone="red"/>
    </section>

    <section className="command-card command-filters"><div className="section-heading"><div><p className="eyebrow">INVESTIGATION FILTERS</p><h2>Filter findings</h2></div><button onClick={() => setFilters({ severity: "", document: "", assurance: "", status: "" })}>Clear filters</button></div><div>
      <label>SEVERITY<select value={filters.severity} onChange={event => updateFilter("severity", event.target.value)}><option value="">All severities</option>{SEVERITIES.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>DOCUMENT<select value={filters.document} onChange={event => updateFilter("document", event.target.value)}><option value="">All documents</option>{filterOptions.documents.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>ASSURANCE TYPE<select value={filters.assurance} onChange={event => updateFilter("assurance", event.target.value)}><option value="">All assurance types</option>{filterOptions.assuranceTypes.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>STATUS<select value={filters.status} onChange={event => updateFilter("status", event.target.value)}><option value="">All statuses</option>{STATUSES.map(value => <option key={value}>{value}</option>)}</select></label>
    </div></section>

    <div className="command-grid">
      <DistributionCard title="Findings by assurance type" items={assuranceDistribution} total={findings.length} available={findingsAvailable} loading={loading}/>
      <DistributionCard title="Findings by review status" items={statusDistribution} total={findings.length} available={findingsAvailable} loading={loading}/>
    </div>

    <div className="command-grid command-bottom-grid">
      <section className="command-card command-findings"><div className="section-heading"><div><p className="eyebrow">FILTERED RESULT SET</p><h2>Findings</h2></div><span>{filteredFindings.length} of {findings.length}</span></div>{loading ? <div className="command-loading"><Activity className="spin" size={17}/>Loading findings…</div> : !findingsAvailable ? <p className="command-empty">Not available.</p> : filteredFindings.length ? <div className="command-finding-list">{filteredFindings.map(finding => <article key={finding.finding_id}><span className={`severity-pill ${normalized(finding.severity).toLowerCase()}`}>{finding.severity || "Not available"}</span><div><strong>{finding.finding_id}</strong><p>{finding.title || finding.root_cause || "Not available"}</p><small>{assuranceType(finding)} · {evidenceDocuments(finding).join(" · ") || "No document metadata"}</small></div><span className={`review-status ${normalized(finding.status || "OPEN").toLowerCase()}`}>{finding.status || "OPEN"}</span></article>)}</div> : <p className="command-empty">No findings match the selected filters.</p>}</section>

      <section className="command-card graph-scope-card"><div className="section-heading"><div><p className="eyebrow">GRAPH API CONNECTION</p><h2>Available graph context</h2></div><Network size={18}/></div>{graphScope ? <><strong>{graphScopeEntity}</strong><p>Two-hop entity context returned by the graph API. These counts are intentionally not presented as corpus totals.</p><div><span><b>{graphScope.nodes?.length || 0}</b> scoped nodes</span><span><b>{graphScope.relationships?.length || 0}</b> scoped relationships</span><span><b>{graphScope.documents?.length || 0}</b> scoped documents</span></div></> : <><strong>Not available.</strong><p>{graphScopeEntity ? "The entity-scoped graph request was unavailable." : "No affected entity was available to query the graph API."}</p></>}</section>
    </div>
  </div>;
}
