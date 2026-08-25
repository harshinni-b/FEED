import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, Bell, Bot, ChevronDown, ChevronRight,
  CircleCheck, Clock3, FileText, GitBranch, LayoutDashboard,
  Moon, Network, PanelRightClose, PanelRightOpen, Play,
  Plus, Search, Send, Settings2, ShieldCheck, Sparkles, Sun, X
} from "lucide-react";
import "./styles.css";
import ChangeImpactView from "./components/ChangeImpactView";
import CommandCenter from "./components/CommandCenter";
import PlantGraphView from "./components/PlantGraphView";
import {
  addFindingComment,
  analyzeQuery,
  getFinding,
  runImpactAnalysis,
  updateFindingReview,
} from "./api/client";

const DEMO_FALLBACK_ENABLED = import.meta.env.VITE_EDOCA_DEMO_FALLBACK === "true";
const REVIEWER_NAME = "Harshinni B.";

const DEMO_FINDING = DEMO_FALLBACK_ENABLED ? {
  id: "EDOCA-2417", severity: "Critical", status: "Open", confidence: "98%",
  title: "Pass 1 surge temperature exceeds SIS trip threshold",
  actual: "621 °C", limit: "620 °C", asset: "Converter Pass 1 · R-401",
  root: "At 110% surge load, the expected outlet temperature is 1 °C above the configured SIS trip setpoint. The operating envelope therefore creates a recurring demand on SIF-05.",
  recommendation: "Resolve the process design deficiency before approving the SRS. Review catalyst bed height and TCV-401 capacity; then realign alarm, trip, and operating limits under MOC.",
} : null;

const EMPTY_FINDING = { id: "", severity: "", status: "", confidence: "Not available", title: "Run an investigation to view findings", actual: "Not available", limit: "Not available", asset: "No asset selected", root: "EDOCA will display evidence-grounded findings after analysis completes.", reasoning: "No analysis has been run.", recommendation: "Submit an engineering query to begin.", affectedAssets: [] };

const DEMO_RECENT_FINDINGS = DEMO_FALLBACK_ENABLED ? [
  ["EDOCA-2417", "Pass 1 surge temperature exceeds SIS trip threshold", "Critical", "2m ago"],
  ["EDOCA-2409", "WHB tube velocity operating margin", "High", "18m ago"],
  ["EDOCA-2398", "SIF-03 recovery condition inconsistency", "Medium", "1h ago"],
] : [];
const nav = [
  ["Command Center", LayoutDashboard], ["Investigation Workspace", Sparkles],
  ["Knowledge Graph", Network], ["Change Impact Analysis", GitBranch], ["Findings Repository", FileText],
];
const DEMO_EVIDENCE = DEMO_FALLBACK_ENABLED ? [
  { doc: "SRS & SIL Records", documentId: "DOC8", section: "3. Safety Requirements Specification — SIF by SIF", subsection: "SIF-05: Converter Pass 1 Temperature High-High", kind: "Supporting", text: "SIF ID / Tag | SIF-05 / TSHH-401\nProcess Demand Condition | Converter Pass 1 outlet temperature exceeds 620°C\nCRITICAL SRS CONFLICT | At 110% surge load the Pass 1 outlet temperature reaches 621°C — 1°C above the SIS trip setpoint. This means the SIF will demand on every surge operation.", score: "0.98" },
  { doc: "Heat & Material Balance", documentId: "DOC2", section: "Converter Heat & Material Balance", subsection: "Pass 1 design and surge case", kind: "Supporting", text: "Pass 1 outlet temperature: Normal 600°C. Surge case calculated outlet temperature: 621°C. Design review action is required before the surge condition can be approved.", score: "0.96" },
  { doc: "Operating Philosophy", documentId: "DOC11", section: "4. Operating Envelope", subsection: "4.2 Surge operation", kind: "Contradicting", text: "The surge operating envelope is stated as available without an SIS demand. This statement conflicts with the SRS demand condition at the calculated Pass 1 surge temperature.", score: "0.89" },
  { doc: "Vendor Datasheet", documentId: "DOC14", section: "Vendor Datasheet Consistency Summary", subsection: "R-401 Converter", kind: "Linked", text: "R-401 catalyst bed height specification must be reduced by approximately 5% before the purchase specification can be finalised. Do not issue the purchase specification until the H&MB Pass 1 temperature finding is resolved.", score: "0.92" },
] : [];

const WORKFLOW_LABELS = {
  detect_intent: "Understanding query",
  retrieve_context: "Retrieving engineering evidence",
  run_attribute_assurance: "Checking attribute consistency",
  attribute_assurance: "Checking attribute consistency",
  run_connectivity_assurance: "Checking graph connectivity",
  connectivity_assurance: "Checking graph connectivity",
  run_operational_intent_assurance: "Comparing operational intent",
  operational_intent_assurance: "Comparing operational intent",
  run_change_impact_assurance: "Assessing change impact",
  change_impact_assurance: "Assessing change impact",
  reason_with_genai: "Generating engineering explanation",
  build_findings: "Building evidence-backed findings",
};

function displayFinding(finding, assuranceResults = []) {
  if (!finding) return DEMO_FINDING || EMPTY_FINDING;
  const matchingCheck = assuranceResults.find(result => result.status === "FAIL" && (result.check === finding.title || result.finding === finding.root_cause)) || assuranceResults.find(result => result.actual || result.limit) || {};
  return {
    id: finding.finding_id,
    severity: finding.severity || "INFO",
    status: finding.status || "OPEN",
    title: finding.title || "Engineering consistency finding",
    actual: matchingCheck.actual || "Not available",
    limit: matchingCheck.limit || "Not available",
    asset: finding.affected_assets?.join(" · ") || "No affected asset identified",
    root: finding.root_cause || "No root cause supplied.",
    reasoning: finding.reasoning || "No additional reasoning was supplied.",
    recommendation: finding.recommendation || "Review the retrieved evidence with the engineering team.",
    confidence: Number.isFinite(finding.confidence) ? `${Math.round(finding.confidence * 100)}%` : "Not available",
    affectedAssets: finding.affected_assets || [],
  };
}

function calculateExceedance(actual, limit) {
  const parse = value => {
    const match = String(value || "").trim().match(/^([-+]?\d[\d,]*(?:\.\d+)?)\s*(.*)$/);
    return match ? { value: Number(match[1].replaceAll(",", "")), unit: match[2].trim() } : null;
  };
  const actualValue = parse(actual);
  const limitValue = parse(limit);
  if (!actualValue || !limitValue || !Number.isFinite(actualValue.value) || !Number.isFinite(limitValue.value)) return "Not available";
  if (actualValue.unit.toLowerCase() !== limitValue.unit.toLowerCase()) return "Not available";
  const difference = actualValue.value - limitValue.value;
  return `${difference > 0 ? "+" : ""}${Number(difference.toPrecision(6))}${actualValue.unit ? ` ${actualValue.unit}` : ""}`;
}

function investigationMetrics(data, finding) {
  if (!data) return [["Retrieved evidence", "Not available", "blue"], ["Assurance checks", "Not available", "violet"], ["Graph connections", "Not available", "cyan"], ["Affected entities", "Not available", "violet"], ["Review confidence", finding.confidence, "green"]];
  return [
    ["Retrieved evidence", data.evidence?.length ?? 0, "blue"],
    ["Assurance checks", data.assurance_results?.length ?? 0, "violet"],
    ["Graph connections", data.graph_context?.relationships?.length ?? 0, "cyan"],
    ["Affected entities", finding.affectedAssets.length, "violet"],
    ["Review confidence", finding.confidence, "green"],
  ];
}

function App() {
  const [page, setPage] = useState("Investigation Workspace");
  const [tab, setTab] = useState("Finding");
  const [dark, setDark] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [query, setQuery] = useState(DEMO_FALLBACK_ENABLED ? "Review the Pass 1 surge temperature inconsistency" : "");
  const [running, setRunning] = useState(false);
  const [sourceContext, setSourceContext] = useState(null);
  const [impactEntity, setImpactEntity] = useState(DEMO_FALLBACK_ENABLED ? "R-401" : "");
  const [impactProposedChange, setImpactProposedChange] = useState(DEMO_FALLBACK_ENABLED ? "Change setpoint from 620°C to 625°C" : "");
  const [impactResult, setImpactResult] = useState(null);
  const [impactRunning, setImpactRunning] = useState(false);
  const [analysisData, setAnalysisData] = useState(null);
  const [apiError, setApiError] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [reviewFinding, setReviewFinding] = useState(null);
  const [selectedReviewFindingId, setSelectedReviewFindingId] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [toast, setToast] = useState("");
  const runInvestigation = async () => { if (!query.trim()) return; setRunning(true); setToast(""); setApiError(""); try { const result = await analyzeQuery(query); setSelectedReviewFindingId(""); setAnalysisData(result); setToast(`Investigation complete: ${result.findings.length} finding(s), ${result.evidence.length} evidence record(s).`); } catch (error) { if (DEMO_FALLBACK_ENABLED) { setAnalysisData(null); setToast("API unavailable; explicit demo fallback is active."); } else setApiError(error.message); } finally { setRunning(false); } };
  const runImpact = async () => { if (!impactEntity.trim() || !impactProposedChange.trim()) return; setImpactRunning(true); setToast(""); setApiError(""); try { const result = await runImpactAnalysis({ entity: impactEntity.trim(), proposed_change: impactProposedChange.trim() }); setImpactResult(result); setToast(`Impact analysis complete: ${result.affected_assets.length} assets and ${result.affected_documents.length} documents affected.`); } catch (error) { setImpactResult(null); setApiError(error.message); } finally { setImpactRunning(false); } };
  const activeFinding = { affectedAssets: [], ...displayFinding(analysisData?.findings?.[0], analysisData?.assurance_results) };
  const metrics = useMemo(() => investigationMetrics(analysisData, activeFinding), [analysisData, activeFinding.confidence]);
  const reviewFindingId = selectedReviewFindingId || analysisData?.findings?.[0]?.finding_id || "";
  const workflowNodes = analysisData?.executed_nodes || [];

  useEffect(() => {
    if (page !== "Findings Repository" || !reviewFindingId) {
      if (!reviewFindingId) {
        setReviewFinding(null);
        setReviewLoading(false);
      }
      return undefined;
    }

    let active = true;
    setReviewLoading(true);
    setApiError("");
    getFinding(reviewFindingId)
      .then(response => {
        if (active) setReviewFinding(response.finding);
      })
      .catch(error => {
        if (active) {
          setReviewFinding(null);
          setApiError(`Unable to load finding ${reviewFindingId}. ${error.message}`);
        }
      })
      .finally(() => {
        if (active) setReviewLoading(false);
      });

    return () => { active = false; };
  }, [page, reviewFindingId]);

  const updateReviewStatus = async nextStatus => {
    if (!reviewFindingId || reviewSaving) return;
    const previousFinding = reviewFinding;
    const comment = reviewComment.trim() || null;
    const optimisticEvent = {
      status: nextStatus,
      reviewer: REVIEWER_NAME,
      comment,
      timestamp: new Date().toISOString(),
    };
    setReviewFinding(current => ({
      ...(current || analysisData.findings[0]),
      status: nextStatus,
      review_history: [...(current?.review_history || []), optimisticEvent],
    }));
    setReviewSaving(true);
    setApiError("");
    setToast("");
    try {
      const response = await updateFindingReview(reviewFindingId, {
        status: nextStatus,
        reviewer: REVIEWER_NAME,
        comment,
      });
      setReviewFinding(response.finding);
      setAnalysisData(current => current ? {
        ...current,
        findings: current.findings.map(item => item.finding_id === reviewFindingId ? response.finding : item),
      } : current);
      setReviewComment("");
      setToast(`Finding ${reviewFindingId} moved to ${nextStatus}.`);
    } catch (error) {
      setReviewFinding(previousFinding);
      setApiError(`Review update failed and was rolled back. ${error.message}`);
    } finally {
      setReviewSaving(false);
    }
  };

  const submitReviewComment = async () => {
    const comment = reviewComment.trim();
    if (!reviewFindingId || !comment || reviewSaving) return;
    const previousFinding = reviewFinding;
    const currentStatus = reviewFinding?.status || "OPEN";
    const optimisticEvent = {
      status: currentStatus,
      reviewer: REVIEWER_NAME,
      comment,
      timestamp: new Date().toISOString(),
    };
    setReviewFinding(current => ({
      ...(current || analysisData.findings[0]),
      review_history: [...(current?.review_history || []), optimisticEvent],
    }));
    setReviewComment("");
    setReviewSaving(true);
    setApiError("");
    setToast("");
    try {
      const response = await addFindingComment(reviewFindingId, {
        reviewer: REVIEWER_NAME,
        comment,
      });
      setReviewFinding(response.finding);
      setToast(`Comment added to finding ${reviewFindingId}.`);
    } catch (error) {
      setReviewFinding(previousFinding);
      setReviewComment(comment);
      setApiError(`Comment could not be saved and was rolled back. ${error.message}`);
    } finally {
      setReviewSaving(false);
    }
  };

  const createImpactReviewCase = async finding => {
    const findingId = finding?.finding_id;
    if (!findingId || !impactResult?.review_required || reviewSaving) return;
    setReviewSaving(true);
    setApiError("");
    setToast("");
    try {
      const response = await updateFindingReview(findingId, {
        status: "REVIEW",
        reviewer: REVIEWER_NAME,
        comment: `Change impact review required: ${impactResult.proposed_change}`,
      });
      setSelectedReviewFindingId(findingId);
      setReviewFinding(response.finding);
      setPage("Findings Repository");
      setToast(`Review case created for finding ${findingId}.`);
    } catch (error) {
      setApiError(`Review case could not be created. ${error.message}`);
    } finally {
      setReviewSaving(false);
    }
  };
  return <div className={dark ? "app dark" : "app"}>
    <aside className="left-rail">
      <div className="brand"><div className="brand-mark"><Bot size={19}/></div><div><strong>EDOCA</strong><span>ENGINEERING INTELLIGENCE</span></div></div>
      <button className="new-investigation" onClick={() => { setPage("Investigation Workspace"); setTab("Finding"); }}><Plus size={16}/> New investigation</button>
      <nav>{nav.map(([label, Icon]) => <button key={label} onClick={() => setPage(label)} className={page === label ? "nav active" : "nav"}><Icon size={17}/><span>{label}</span>{label === "Findings Repository" && analysisData?.findings?.length > 0 && <b>{analysisData.findings.length}</b>}</button>)}</nav>
      <div className="sidebar-label">RECENT INVESTIGATIONS</div>
      <div className="recent">{DEMO_RECENT_FINDINGS.map(([id, name, level]) => <button key={id} className={id === activeFinding.id ? "recent-item selected" : "recent-item"}><span className={'severity-dot ' + level.toLowerCase()}></span><div><strong>{id}</strong><small>{name}</small></div></button>)}</div>
      <div className="progress-card"><div className="progress-head"><span>INVESTIGATION PROGRESS</span><strong>{workflowNodes.length} / 8</strong></div><div className="progress"><i style={{ width: `${Math.min(100, (workflowNodes.length / 8) * 100)}%` }}></i></div>{running && <div className="progress-line pending"><Activity className="spin" size={14}/><span>Running LangGraph workflow</span></div>}{workflowNodes.map(node => <div className="progress-line" key={node}><CircleCheck size={14}/><span>{WORKFLOW_LABELS[node] || node}</span></div>)}{!running && workflowNodes.length === 0 && <div className="progress-line pending"><Clock3 size={14}/><span>Awaiting investigation</span></div>}</div>
      <div className="profile"><div className="avatar">HB</div><div><strong>Harshinni B.</strong><small>Process Engineering</small></div><ChevronDown size={15}/></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="crumb"><span>EDOCA</span><ChevronRight size={14}/><strong>{page}</strong></div><div className="top-actions"><div className="system-ok"><i></i> System operational</div><button onClick={() => setDark(!dark)} title="Toggle theme">{dark ? <Sun size={17}/> : <Moon size={17}/>}</button><button className="notification"><Bell size={17}/><i></i></button><button onClick={() => setRightOpen(!rightOpen)}>{rightOpen ? <PanelRightClose size={18}/> : <PanelRightOpen size={18}/>}</button></div></header>
      <section className="workspace">
        <div className="workspace-header"><div><p className="eyebrow">ACTIVE INVESTIGATION <span>•</span> {activeFinding.id || "NOT RUN"}</p><h1>{page === "Investigation Workspace" ? "Investigation Workspace" : page}</h1><p className="subhead">{analysisData?.query ? `Cross-document consistency assurance for: ${analysisData.query}` : "Submit an engineering question to begin an investigation."}</p></div><div className="header-actions"><button className="secondary"><Settings2 size={16}/> Configure</button><button className="primary" onClick={runInvestigation} disabled={running}>{running ? <Activity className="spin" size={16}/> : <Play size={16}/>} {running ? "Analysing…" : "Run analysis"}</button></div></div>
        <div className="query-bar"><Search size={18}/><input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && runInvestigation()}/><button onClick={runInvestigation}><Send size={16}/></button></div>
        {toast && <div className="toast"><CircleCheck size={16}/>{toast}<button onClick={() => setToast("")}><X size={15}/></button></div>}
        {apiError && <div className="toast error-toast"><AlertTriangle size={16}/>{apiError}<button onClick={() => setApiError("")}><X size={15}/></button></div>}
        {page === "Command Center" ? <CommandCenter /> : page === "Change Impact Analysis" ? <ChangeImpactView entity={impactEntity} setEntity={setImpactEntity} proposedChange={impactProposedChange} setProposedChange={setImpactProposedChange} result={impactResult} loading={impactRunning} run={runImpact} onCreateReviewCase={createImpactReviewCase} reviewCreating={reviewSaving} /> : page === "Findings Repository" ? <EngineerReviewView finding={reviewFinding} displayFinding={activeFinding} loading={reviewLoading} saving={reviewSaving} comment={reviewComment} setComment={setReviewComment} onStatus={updateReviewStatus} onComment={submitReviewComment} /> : <><div className="tabs">{["Finding", "Analysis", "Graph View", "Assurance Details"].map(item => <button className={tab === item ? "tab current" : "tab"} onClick={() => setTab(item)} key={item}>{item}{item === "Finding" && analysisData?.findings?.length > 0 && <span>{analysisData.findings.length}</span>}</button>)}</div>
        {tab === "Finding" && <WorkspaceFindingView metrics={metrics} finding={activeFinding} data={analysisData} empty={!analysisData && !DEMO_FALLBACK_ENABLED} />}
        {tab === "Analysis" && <WorkspaceAnalysisView data={analysisData} />}
        {tab === "Graph View" && <PlantGraphView initialEntity={activeFinding.affectedAssets[0] || analysisData?.graph_context?.nodes?.[0]?.name || ""} currentFinding={analysisData?.findings?.[0] || null} />}
        {tab === "Assurance Details" && <WorkspaceAssuranceView data={analysisData} />}</>}
      </section>
    </main>
    {rightOpen && <EvidencePanel evidence={analysisData?.evidence || DEMO_EVIDENCE} graph={analysisData?.graph_context} findings={analysisData?.findings || []} retrievalMetadata={analysisData?.retrieval_metadata} onSelect={setSourceContext} />}
    {sourceContext && <EvidenceDrawer record={sourceContext} findings={analysisData?.findings || []} graph={analysisData?.graph_context} assuranceResults={analysisData?.assurance_results || []} onClose={() => setSourceContext(null)} />}
  </div>;
}

function formatReviewTimestamp(timestamp) {
  if (!timestamp) return "Not available";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
}

function EngineerReviewView({ finding, displayFinding: displayed, loading, saving, comment, setComment, onStatus, onComment }) {
  if (loading) {
    return <div className="review-screen"><section className="review-card review-empty"><Activity className="spin" size={20}/><div><h2>Loading engineer review</h2><p>Retrieving the persisted finding and review history.</p></div></section></div>;
  }
  if (!finding) {
    return <div className="review-screen"><section className="review-card review-empty"><FileText size={22}/><div><h2>No finding selected</h2><p>Run an investigation to create and load an evidence-backed finding for engineer review.</p></div></section></div>;
  }

  const status = finding.status || "OPEN";
  const history = Array.isArray(finding.review_history) ? finding.review_history : [];
  const latestReview = history[history.length - 1];
  const evidenceCount = Array.isArray(finding.evidence) ? finding.evidence.length : 0;
  const severity = finding.severity || displayed.severity || "INFO";
  const displayedValuesMatch = displayed.id === finding.finding_id;

  return <div className="review-screen">
    <section className="review-hero">
      <div><p className="eyebrow">ENGINEER REVIEW WORKFLOW</p><h2>Review finding {finding.finding_id}</h2><p>Record the engineering decision, supporting rationale, and disposition for this evidence-grounded finding.</p></div>
      <div className="status-block"><span>CURRENT STATUS</span><strong className={'review-status ' + status.toLowerCase()}>{status}</strong><small>{latestReview?.reviewer || "No reviewer yet"}</small><small>{formatReviewTimestamp(latestReview?.timestamp)}</small></div>
    </section>
    <div className="review-grid">
      <section className="review-card review-finding">
        <div className="section-heading"><div><p className="eyebrow">FINDING UNDER REVIEW</p><h2>{finding.title || displayed.title}</h2></div><span className="critical-badge"><AlertTriangle size={14}/> {severity}</span></div>
        <div className="review-fields"><div><span>ASSET</span><strong>{finding.affected_assets?.join(" · ") || displayed.asset}</strong></div><div><span>ACTUAL / LIMIT</span><strong className="danger">{displayedValuesMatch ? `${displayed.actual} / ${displayed.limit}` : "Not available"}</strong></div><div><span>EVIDENCE</span><strong>{evidenceCount} linked source{evidenceCount === 1 ? "" : "s"}</strong></div></div>
        <p>{finding.root_cause || displayed.root}</p><button className="review-source"><FileText size={15}/> Open source-of-truth evidence <ChevronRight size={15}/></button>
      </section>
      <section className="review-card disposition">
        <p className="eyebrow">SET DISPOSITION</p><h2>Engineer decision</h2><p>Select a status to record the review outcome. Include a comment when engineering rationale is required.</p>
        <div className="status-options">{["OPEN", "REVIEW", "ACCEPTED", "REJECTED", "CLOSED"].map(option => <button key={option} disabled={saving} onClick={() => onStatus(option)} className={status === option ? `status-option current ${option.toLowerCase()}` : `status-option ${option.toLowerCase()}`}><i></i>{option}</button>)}</div>
        <div className="decision-actions"><button disabled={saving} onClick={() => onStatus("ACCEPTED")} className="accept"><CircleCheck size={16}/> Accept finding</button><button disabled={saving} onClick={() => onStatus("REJECTED")} className="reject"><X size={16}/> Reject finding</button></div>
      </section>
    </div>
    <section className="review-card comment-card">
      <div className="section-heading"><div><p className="eyebrow">REVIEW RECORD</p><h2>Engineer comments</h2></div><span>{history.length} record{history.length === 1 ? "" : "s"}</span></div>
      <textarea value={comment} disabled={saving} onChange={event => setComment(event.target.value)} placeholder="Add your engineering rationale, review notes, or required next steps…"/>
      <div className="comment-actions"><span><ShieldCheck size={14}/> Your comment will be recorded with the current status.</span><button disabled={saving || !comment.trim()} onClick={onComment} className="primary">{saving ? <Activity className="spin" size={15}/> : <Send size={15}/>} {saving ? "Saving…" : "Add comment"}</button></div>
      {history.length > 0 ? <div className="comment-history">{history.slice().reverse().map((item, index) => <article key={`${item.timestamp || "review"}-${index}`}><div className="avatar">{(item.reviewer || "Engineer").split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase()}</div><div><strong>{item.reviewer || "Not available"}</strong><small>{formatReviewTimestamp(item.timestamp)} · {item.status || "Not available"}</small><p>{item.comment || "No comment supplied for this status change."}</p></div></article>)}</div> : <p className="review-history-empty">No review activity has been recorded.</p>}
    </section>
  </div>;
}

function WorkspaceFindingView({ metrics, finding, data, empty }) {
  const rawFinding = data?.findings?.[0];
  const findingEvidence = rawFinding?.evidence || [];
  const documentCount = new Set(findingEvidence.map(record => record.document_id).filter(Boolean)).size;
  const exceedance = calculateExceedance(finding.actual, finding.limit);
  return <div className="content-grid"><div className="finding-column"><article className="finding-card"><div className="finding-top"><div><div className="finding-id"><span className="critical-badge"><AlertTriangle size={14}/> {finding.severity || "INFO"}</span><span className="open-badge">{finding.status || "OPEN"}</span></div><h2>{finding.title}</h2><p><Network size={14}/> {finding.asset}</p></div></div>{empty ? <div className="finding-section"><h3>No finding yet</h3><p>Submit an engineering question to retrieve evidence and build findings.</p></div> : <><div className="numbers"><div><span>ACTUAL VALUE</span><strong className="danger">{finding.actual}</strong><small>Assurance result</small></div><div><span>LIMIT VALUE</span><strong>{finding.limit}</strong><small>Assurance result</small></div><div><span>EXCEEDANCE</span><strong className="danger">{exceedance}</strong><small>Actual minus limit</small></div><div><span>CONFIDENCE</span><strong>{finding.confidence}</strong><small>Evidence grounded</small></div></div><div className="finding-section"><h3>Root cause</h3><p>{finding.root}</p></div><div className="finding-section"><h3>Engineering reasoning</h3><p>{finding.reasoning}</p></div><div className="recommendation"><div className="rec-icon"><Sparkles size={18}/></div><div><span>RECOMMENDED ACTION</span><p>{finding.recommendation}</p></div></div></>}</article>{!empty && <section className="executive"><div className="section-heading"><div><p className="eyebrow">EVIDENCE-GROUNDED BRIEF</p><h2>Executive summary</h2></div><span className="ai-label"><Sparkles size={13}/> Workflow output</span></div><p>{finding.reasoning || finding.root}</p><div className="summary-points"><span><AlertTriangle size={15}/> {finding.severity || "Not available"} · {finding.title}</span><span><FileText size={15}/> {findingEvidence.length} evidence reference{findingEvidence.length === 1 ? "" : "s"} across {documentCount} document{documentCount === 1 ? "" : "s"}</span><span><GitBranch size={15}/> {finding.affectedAssets.length} affected entit{finding.affectedAssets.length === 1 ? "y" : "ies"}</span></div></section>}</div><aside className="metric-column"><div className="section-heading"><div><p className="eyebrow">INVESTIGATION HEALTH</p><h2>Assurance metrics</h2></div></div><div className="metric-list">{metrics.map(([label,value,color]) => <div className="metric" key={label}><div className={'metric-icon '+color}><Activity size={17}/></div><div><span>{label}</span><strong>{value}</strong></div></div>)}</div></aside></div>;
}

function WorkspaceAnalysisView({ data }) {
  const reasoning = data?.reasoning_output || {};
  const steps = data?.executed_nodes || [];
  const summaries = {
    detect_intent: data?.intent ? `Detected intent: ${data.intent}.` : "Intent was not returned.",
    retrieve_context: `${data?.evidence?.length ?? 0} evidence records retrieved using ${data?.retrieval_metadata?.retrieval_mode || "an unspecified retrieval mode"}.`,
    run_attribute_assurance: `${(data?.assurance_results || []).filter(result => result.actual !== undefined || result.limit !== undefined).length} value/limit results returned.`,
    run_connectivity_assurance: `${data?.graph_context?.nodes?.length ?? 0} nodes and ${data?.graph_context?.relationships?.length ?? 0} relationships available in graph context.`,
    run_operational_intent_assurance: `${(data?.assurance_results || []).filter(result => Array.isArray(result.supporting_evidence)).length} evidence-linked assurance results returned.`,
    run_change_impact_assurance: `${(data?.assurance_results || []).flatMap(result => result.affected_assets || []).length} affected-asset references returned.`,
    reason_with_genai: data?.findings?.[0]?.reasoning || reasoning.reasoning || "No explanation was returned.",
    build_findings: `${data?.findings?.length ?? 0} evidence-backed findings built.`,
  };
  return <div className="analysis-panel"><p className="eyebrow">REASONING TRACE</p><h2>How EDOCA reached this finding</h2>{steps.length ? steps.map((node, index) => <div className="reason-step" key={node}><div>{index + 1}</div><section><strong>{WORKFLOW_LABELS[node] || node}</strong><p>{summaries[node] || "The workflow completed this stage."}</p></section><CircleCheck size={19}/></div>) : <p className="subhead">Run an investigation to view the LangGraph execution trace.</p>}{reasoning.root_cause && <div className="finding-section"><h3>Reasoning output</h3><p>{data?.findings?.[0]?.reasoning || reasoning.reasoning}</p></div>}</div>;
}

function WorkspaceAssuranceView({ data }) {
  const results = data?.assurance_results || [];
  return <div className="assurance-table"><div className="table-row table-head"><span>ASSURANCE CHECK</span><span>RESULT</span><span>EVIDENCE</span><span>STATUS</span></div>{results.length ? results.map((result, index) => { const documents = [...new Set((result.supporting_evidence || []).map(record => record.document_id).filter(Boolean))]; return <div className="table-row" key={`${result.check || result.entity || "assurance"}-${index}`}><strong>{result.check || result.entity || "Change impact"}</strong><span>{result.actual !== undefined || result.limit !== undefined ? `${result.actual ?? "Not available"} / ${result.limit ?? "Not available"}` : result.finding || `${result.affected_assets?.length ?? 0} affected assets`}</span><span>{documents.length ? documents.join(", ") : result.affected_assets?.join(", ") || "Not available"}</span><b className={(result.status || "review").toLowerCase()}>{result.status || "REVIEW"}</b></div>; }) : <div className="table-row"><span>No assurance results yet.</span></div>}</div>;
}

function evidenceRecord(record, graph, findings, index) {
  const text = record.text || "";
  const graphEntities = (graph?.nodes || []).filter(node => node.name && text.toLowerCase().includes(String(node.name).toLowerCase())).map(node => node.name);
  const linkedFinding = findings.find(finding => (finding.evidence || []).some(item => item.chunk_id === record.chunk_id));
  const suppliedClassification = String(record.classification || record.evidence_classification || record.kind || "").toUpperCase();
  return {
    ...record,
    chunk_id: record.chunk_id || `demo-evidence-${index}`,
    document_id: record.document_id || record.documentId,
    document_type: record.document_type || record.doc,
    source_type: record.source_type || "Not available",
    classification: ["SUPPORTING", "CONTRADICTING", "CONTEXT"].includes(suppliedClassification) ? suppliedClassification : linkedFinding ? "SUPPORTING" : "CONTEXT",
    linkedFinding,
    graphEntities: [...new Set(graphEntities)],
  };
}

function HighlightedText({ text }) {
  const pattern = /(\b(?:SIF|TSHH|TSH|PSHH|PSH|TIC|PIC|FIC|LIC|TCV|PCV|FCV|SDV|XV|TT|PT|FT|LT|AT|R|P|E|WHB)-\d{1,5}[A-Z]?\b|\b[-+]?\d[\d,]*(?:\.\d+)?\s*(?:°C|C|barg?|bar|%|kg\/h|t\/d|m³\/h|m3\/h|kW)\b)/gi;
  return <>{String(text || "Not available.").split(pattern).map((part, index) => index % 2 ? <mark key={index}>{part}</mark> : part)}</>;
}

function EvidencePanel({ evidence, graph, findings, retrievalMetadata, onSelect }) {
  const [tab, setTab] = useState("ALL");
  const records = evidence.map((record, index) => evidenceRecord(record, graph, findings, index));
  const displayed = records.filter(record => tab === "ALL" || (tab === "GRAPH" ? record.graphEntities.length > 0 : record.classification === tab));
  const tabs = [["ALL", "All Evidence"], ["SUPPORTING", "Supporting"], ["CONTRADICTING", "Contradicting"], ["GRAPH", "Graph-linked"]];
  const documentCount = new Set(records.map(record => record.document_id).filter(Boolean)).size;
  return <aside className="source-truth-panel"><div className="rail-title"><div><p className="eyebrow">SOURCE OF TRUTH</p><h2>Evidence trail</h2></div></div><div className="evidence-summary"><div><strong>{records.length}</strong><span>retrieved records</span></div><div><strong>{documentCount}</strong><span>documents</span></div><div><strong>{retrievalMetadata?.retrieval_mode || "Not available"}</strong><span>retrieval mode</span></div></div><div className="source-filter">{tabs.map(([value, label]) => <button key={value} className={tab === value ? "selected" : ""} onClick={() => setTab(value)}>{label}</button>)}</div><div className="evidence-list">{displayed.length ? displayed.map(record => <button key={record.chunk_id} className="evidence-item" onClick={() => onSelect(record)}><div className="evidence-meta"><span className={'tag ' + record.classification.toLowerCase()}>{record.classification}</span><span>{record.source_type || "Not available"}</span></div><strong>{record.document_id || "Not available"}</strong><small>{record.document_type || "Not available"}</small><small className="subsection">{record.section || "Not available"} · {record.subsection || "Not available"}</small><p><HighlightedText text={record.text}/></p></button>) : <p className="empty-evidence">No evidence in this classification.</p>}</div></aside>;
}

function EvidenceDrawer({ record, findings, graph, assuranceResults, onClose }) {
  const linkedFinding = record.linkedFinding || findings.find(finding => (finding.evidence || []).some(item => item.chunk_id === record.chunk_id));
  const assurance = assuranceResults.find(result => (result.supporting_evidence || []).some(item => item.chunk_id === record.chunk_id));
  return <div className="evidence-drawer-overlay" onClick={onClose}><section className="evidence-drawer" onClick={event => event.stopPropagation()}><header><div><p className="eyebrow">EVIDENCE CONTEXT</p><h2>{record.document_id || "Not available"}</h2><span>{record.document_type || "Not available"}</span></div><button onClick={onClose}><X size={18}/></button></header><div className="source-classification"><span className={'tag ' + record.classification.toLowerCase()}>{record.classification}</span><span>{record.source_type || "Not available"}</span></div><dl><div><dt>Section</dt><dd>{record.section || "Not available"}</dd></div><div><dt>Subsection</dt><dd>{record.subsection || "Not available"}</dd></div><div><dt>Revision</dt><dd>{record.revision || "Not available"}</dd></div><div><dt>Page reference</dt><dd>{record.page_reference || "Not available"}</dd></div><div><dt>Linked finding</dt><dd>{linkedFinding?.finding_id || "Not available"}</dd></div><div><dt>Assurance check</dt><dd>{assurance?.check || "Not available"}</dd></div><div><dt>Graph entities</dt><dd>{record.graphEntities?.join(" · ") || "Not available"}</dd></div></dl><div className="source-text"><span>RETRIEVED TEXT</span><p><HighlightedText text={record.text}/></p></div></section></div>;
}

createRoot(document.getElementById("root")).render(<App />);
