import { useState } from "react";
import { Activity, AlertTriangle, FileText, GitBranch, Network, Search, ShieldCheck } from "lucide-react";

const GROUPS = [
  ["instrument", "Instruments"],
  ["sif", "Safety instrumented functions"],
  ["control_loop", "Control loops"],
  ["equipment", "Equipment"],
  ["document", "Documents"],
];

const SEVERITY_RANK = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0 };
const CONTROL_LOOP = /^(?:FIC|LIC|PIC|TIC|AIC|DIC|SIC|TSC|LSH|LSHH|PSH|PSHH|TSH|TSHH)-/i;
const INSTRUMENT = /^(?:AI|AT|FI|FIT|FT|LI|LIT|LT|MFM|PI|PIT|PT|TI|TIT|TT|ZV)(?:-|$)/i;

const normalizedEntity = value => String(value || "").trim().toLowerCase().replace(/^[a-z_]+:/, "");

function groupForAsset(asset) {
  const name = String(asset || "");
  if (/^SIF-/i.test(name)) return "sif";
  if (CONTROL_LOOP.test(name)) return "control_loop";
  if (INSTRUMENT.test(name)) return "instrument";
  return "equipment";
}

function highestSeverity(result) {
  const values = [
    ...(result?.assurance_results || []).map(item => item.severity),
    ...(result?.related_findings || []).map(item => item.severity),
  ].map(value => String(value || "").toUpperCase()).filter(value => value in SEVERITY_RANK);
  return values.sort((left, right) => SEVERITY_RANK[right] - SEVERITY_RANK[left])[0] || "";
}

function primaryFinding(findings) {
  return [...findings].sort((left, right) => (SEVERITY_RANK[String(right.severity || "").toUpperCase()] ?? -1) - (SEVERITY_RANK[String(left.severity || "").toUpperCase()] ?? -1))[0];
}

export default function ChangeImpactView({
  entity,
  setEntity,
  proposedChange,
  setProposedChange,
  result,
  loading,
  run,
  onCreateReviewCase,
  reviewCreating,
}) {
  const [showContext, setShowContext] = useState(false);
  const assets = result?.affected_assets || [];
  const documents = result?.affected_documents || [];
  const relationships = result?.affected_relationships || [];
  const assuranceResults = result?.assurance_results || [];
  const findings = result?.related_findings || [];
  const radius = (showContext ? result?.expanded_impact_radius : result?.impact_radius)?.by_hop || {};
  const severity = highestSeverity(result);
  const reviewFinding = primaryFinding(findings);

  const severeEntities = new Set(findings
    .filter(finding => ["CRITICAL", "HIGH"].includes(String(finding.severity || "").toUpperCase()))
    .flatMap(finding => finding.affected_assets || [])
    .map(normalizedEntity));

  const grouped = Object.fromEntries(GROUPS.map(([key]) => [key, []]));
  assets.forEach(asset => grouped[groupForAsset(asset)].push(asset));
  documents.forEach(document => grouped.document.push(document));

  const isHighImpact = value => severeEntities.has(normalizedEntity(value));
  const contextEntityIds = new Set((result?.context_nodes || []).flatMap(node => [node.entity_id, node.name]).map(normalizedEntity));
  const visibleRelationships = showContext ? relationships : relationships.filter(relationship => !contextEntityIds.has(normalizedEntity(relationship.source)) && !contextEntityIds.has(normalizedEntity(relationship.target)));
  const canRun = entity.trim() && proposedChange.trim() && !loading;

  return <div className="impact-screen api-impact-screen">
    <section className="impact-hero impact-form-hero">
      <div><p className="eyebrow">DETERMINISTIC GRAPH ASSESSMENT</p><h2>Assess engineering change impact</h2><p>Trace only graph-derived dependencies and document provenance returned by EDOCA.</p></div>
      <form onSubmit={event => { event.preventDefault(); if (canRun) run(); }} className="impact-form">
        <label>ENGINEERING ENTITY</label><div className="impact-field"><Search size={16}/><input value={entity} onChange={event => setEntity(event.target.value)} placeholder="e.g. TSHH-401"/></div>
        <label>PROPOSED CHANGE</label><textarea value={proposedChange} onChange={event => setProposedChange(event.target.value)} placeholder="Describe the engineering change to assess"/>
        <button className="primary" type="submit" disabled={!canRun}>{loading ? <Activity className="spin" size={16}/> : <GitBranch size={16}/>} {loading ? "Assessing impact…" : "Analyse impact"}</button>
      </form>
    </section>

    {!result && !loading && <section className="impact-card impact-empty"><Network size={26}/><div><h2>No impact analysis yet</h2><p>Submit an engineering entity and proposed change to retrieve deterministic impact results.</p></div></section>}

    {result && <>
      <div className="impact-overview impact-overview-five">
        <div><span>SELECTED ENTITY</span><strong>{result.entity || "Not available"}</strong><small>{result.proposed_change || "Not available"}</small></div>
        <div><span>AFFECTED ASSETS</span><strong>{assets.length}</strong><small>API-returned dependencies</small></div>
        <div><span>AFFECTED DOCUMENTS</span><strong>{documents.length}</strong><small>With graph provenance</small></div>
        <div><span>SEVERITY</span><strong className={severity ? `impact-severity ${severity.toLowerCase()}` : "impact-severity unavailable"}>{severity || "Not available"}</strong><small>From findings or assurance</small></div>
        <div><span>ENGINEER REVIEW</span><strong className={result.review_required ? "review-required" : "review-not-required"}>{result.review_required ? "REQUIRED" : "NOT REQUIRED"}</strong><small>API determination</small></div>
      </div>

      <section className="impact-card dependency-card">
        <div className="section-heading"><div><p className="eyebrow">DEPENDENCY TRAIL</p><h2>Impact radius</h2></div><div><button className="secondary" onClick={() => setShowContext(value => !value)}>{showContext ? "Hide raw context" : `Expand raw context (${result.context_nodes?.length || 0})`}</button><span className="hop-label">{result.impact_radius?.max_hops ?? "Not available"} HOPS</span></div></div>
        <div className="dependency-trail">{Object.entries(radius).map(([hop, details]) => {
          const entities = Array.isArray(details) ? details : details.entities || [];
          return <div className="dependency-hop" key={hop}><div className="dependency-marker"><span>{hop}</span></div><section><strong>{hop === "0" ? "Changed entity" : `Hop ${hop} dependencies`}</strong><small>{details.count ?? entities.length} entities</small><div>{entities.map(item => <span key={item} className={isHighImpact(item) ? "dependency-entity high-impact" : "dependency-entity"}>{isHighImpact(item) && <AlertTriangle size={11}/>} {item}</span>)}</div></section></div>;
        })}</div>
      </section>

      <section className="impact-card grouped-impact-card">
        <div className="section-heading"><div><p className="eyebrow">IMPACT CLASSIFICATION</p><h2>Affected entities and documents</h2></div><span className="count-pill">{assets.length + documents.length}</span></div>
        <div className="impact-groups">{GROUPS.map(([key, label]) => <article key={key}><header><span className={`impact-group-icon ${key}`}></span><strong>{label}</strong><b>{grouped[key].length}</b></header>{grouped[key].length ? <div>{grouped[key].map(item => <span key={item} className={isHighImpact(item) ? "high-impact" : ""}>{key === "document" && <FileText size={12}/>} {item}{isHighImpact(item) && <AlertTriangle size={11}/>}</span>)}</div> : <p>No API-returned impacts.</p>}</article>)}</div>
      </section>

      <div className="impact-grid impact-detail-grid">
        <section className="impact-card relationship-card"><div className="section-heading"><div><p className="eyebrow">GRAPH PROVENANCE</p><h2>Affected relationships</h2></div><span className="count-pill">{visibleRelationships.length}</span></div>{visibleRelationships.length ? <div className="relationship-list">{visibleRelationships.map((relationship, index) => { const highImpact = isHighImpact(relationship.source) || isHighImpact(relationship.target); return <article key={`${relationship.source}-${relationship.target}-${relationship.relationship_type}-${index}`} className={highImpact ? "high-impact" : ""}><div><span>{relationship.source || "Not available"}</span><b>{relationship.relationship_type || "Not available"}</b><span>{relationship.target || "Not available"}</span></div><small>{relationship.document || "Document provenance not available"}</small></article>; })}</div> : <p className="impact-none">No affected relationships returned for this context level.</p>}</section>

        <section className="impact-card checks-card"><div className="section-heading"><div><p className="eyebrow">RE-ASSESSMENT SCOPE</p><h2>Assurance checks requiring rerun</h2></div><span className="count-pill">{assuranceResults.length}</span></div>{assuranceResults.length ? <div className="impact-checks">{assuranceResults.map((check, index) => <div key={`${check.check || check.assurance_check || "change-impact"}-${index}`}><div className={`check-severity ${String(check.severity || "unavailable").toLowerCase()}`}></div><section><strong>{check.check || check.assurance_check || check.name || "Change Impact Assurance"}</strong><p>{check.finding || `${(check.affected_assets || []).length} affected assets · ${(check.affected_documents || []).length} affected documents`}</p></section><span className={`check-status ${String(check.status || "unavailable").toLowerCase()}`}>{check.status || "NOT SPECIFIED"}</span></div>)}</div> : <p className="impact-none">No assurance checks were returned for rerun.</p>}</section>
      </div>

      <section className="impact-card related-findings-card"><div className="section-heading"><div><p className="eyebrow">ENGINEERING REVIEW</p><h2>Related findings</h2></div><button className="primary" disabled={!result.review_required || !reviewFinding || reviewCreating} onClick={() => onCreateReviewCase(reviewFinding)}>{reviewCreating ? <Activity className="spin" size={15}/> : <ShieldCheck size={15}/>} {reviewCreating ? "Creating…" : "Create Review Case"}</button></div>{findings.length ? <div className="related-impact-findings">{findings.map(finding => <article key={finding.finding_id}><span className={`impact-severity ${String(finding.severity || "unavailable").toLowerCase()}`}>{finding.severity || "Not available"}</span><div><strong>{finding.finding_id}</strong><p>{finding.title || finding.root_cause || "Not available"}</p></div><span className={`review-status ${String(finding.status || "OPEN").toLowerCase()}`}>{finding.status || "OPEN"}</span></article>)}</div> : <p className="impact-none">No related findings were returned. A review case cannot be created without a persisted finding.</p>}</section>
    </>}
  </div>;
}
