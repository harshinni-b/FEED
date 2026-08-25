import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { Activity, AlertTriangle, FileText, Network, Search } from "lucide-react";
import { getGraphContext } from "../api/client";

const NODE_STYLES = {
  UNIT: { label: "Unit", color: "#3478f6" },
  EQUIPMENT: { label: "Equipment", color: "#7c5ce7" },
  INSTRUMENT: { label: "Instrument", color: "#26a7c7" },
  CONTROL_LOOP: { label: "Control loop", color: "#35b77b" },
  SIF: { label: "SIF", color: "#ef5b70" },
  VALVE: { label: "Valve", color: "#ef9b46" },
  DOCUMENT: { label: "Document", color: "#9aa8bf" },
  PARAMETER: { label: "Parameter", color: "#b36ee2" },
  OTHER: { label: "Other", color: "#64748b" },
};

const visibleLegendTypes = ["UNIT", "EQUIPMENT", "INSTRUMENT", "CONTROL_LOOP", "SIF", "VALVE", "DOCUMENT", "PARAMETER"];
const endpointId = endpoint => typeof endpoint === "object" ? endpoint.id : endpoint;
const comparable = value => String(value || "").trim().toLowerCase();

function visualType(entityType) {
  const type = String(entityType || "OTHER").toUpperCase();
  if (type === "VALUE" || type === "LIMIT") return "PARAMETER";
  return NODE_STYLES[type] ? type : "OTHER";
}

function displayValue(value) {
  if (value === undefined || value === null || value === "") return "Not available";
  if (Array.isArray(value)) return value.join(" · ") || "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function GraphCanvas({ graphData, selectedId, onNodeClick, width }) {
  const graphRef = useRef(null);

  const drawNode = useCallback((node, context, globalScale) => {
    const radius = node.inFinding ? 8 : 6;
    context.beginPath();
    context.arc(node.x, node.y, radius, 0, 2 * Math.PI);
    context.fillStyle = node.color;
    context.fill();
    context.lineWidth = node.id === selectedId ? 2.5 : node.inFinding ? 2 : 1;
    context.strokeStyle = node.id === selectedId ? "#ffffff" : node.inFinding ? "#ffcc66" : "#17213a";
    context.stroke();

    if (globalScale < 0.65 && node.id !== selectedId && !node.inFinding) return;
    const fontSize = Math.max(3.5, 11 / globalScale);
    context.font = `600 ${fontSize}px Inter, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "top";
    const textWidth = context.measureText(node.label).width;
    context.fillStyle = "rgba(8, 13, 27, .86)";
    context.fillRect(node.x - textWidth / 2 - 2, node.y + radius + 2, textWidth + 4, fontSize + 3);
    context.fillStyle = "#dce7ff";
    context.fillText(node.label, node.x, node.y + radius + 3);
  }, [selectedId]);

  const drawLinkLabel = useCallback((link, context, globalScale) => {
    if (!link.label || typeof link.source !== "object" || typeof link.target !== "object") return;
    const x = (link.source.x + link.target.x) / 2;
    const y = (link.source.y + link.target.y) / 2;
    const fontSize = Math.max(3, 8 / globalScale);
    context.font = `500 ${fontSize}px Inter, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    const textWidth = context.measureText(link.label).width;
    context.fillStyle = "rgba(8, 13, 27, .9)";
    context.fillRect(x - textWidth / 2 - 2, y - fontSize / 2 - 1, textWidth + 4, fontSize + 2);
    context.fillStyle = "#8fa4c8";
    context.fillText(link.label, x, y);
  }, []);

  const selectNode = useCallback(node => {
    graphRef.current?.centerAt(node.x, node.y, 500);
    graphRef.current?.zoom(3.2, 500);
    onNodeClick(node);
  }, [onNodeClick]);

  return <ForceGraph2D
    ref={graphRef}
    width={width}
    height={520}
    graphData={graphData}
    nodeId="id"
    nodeCanvasObject={drawNode}
    nodePointerAreaPaint={(node, color, context) => { context.fillStyle = color; context.beginPath(); context.arc(node.x, node.y, node.inFinding ? 10 : 8, 0, 2 * Math.PI); context.fill(); }}
    linkColor={() => "rgba(104, 128, 172, .55)"}
    linkWidth={1}
    linkDirectionalArrowLength={3.5}
    linkDirectionalArrowRelPos={1}
    linkCanvasObjectMode={() => "after"}
    linkCanvasObject={drawLinkLabel}
    backgroundColor="#080d1b"
    cooldownTicks={80}
    d3AlphaDecay={0.035}
    d3VelocityDecay={0.35}
    onNodeClick={selectNode}
    onEngineStop={() => graphRef.current?.zoomToFit(450, 45)}
  />;
}

export default function PlantGraphView({ initialEntity, currentFinding }) {
  const containerRef = useRef(null);
  const [entity, setEntity] = useState(initialEntity || "");
  const [depth, setDepth] = useState(1);
  const [includeContext, setIncludeContext] = useState(false);
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [width, setWidth] = useState(720);

  const loadGraph = useCallback(async (requestedEntity, requestedDepth, requestedContext = false) => {
    const query = String(requestedEntity || "").trim();
    if (!query) return;
    setLoading(true);
    setError("");
    try {
      const response = await getGraphContext(query, requestedDepth, { includeContext: requestedContext });
      setResult(response);
      setSelectedId(response.resolved_entity?.entity_id || response.nodes?.[0]?.entity_id || "");
    } catch (requestError) {
      setResult(null);
      setSelectedId("");
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!initialEntity) return;
    setEntity(initialEntity);
    loadGraph(initialEntity, depth, includeContext);
  }, [initialEntity, loadGraph]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const measure = () => setWidth(Math.max(420, element.clientWidth));
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const affectedEntities = useMemo(() => new Set((currentFinding?.affected_assets || []).map(comparable)), [currentFinding]);
  const graphData = useMemo(() => {
    const nodes = (result?.nodes || []).map(node => {
      const id = String(node.entity_id || node.id || node.name);
      const label = String(node.name || node.entity_id || node.id);
      const category = visualType(node.entity_type);
      return {
        id,
        label,
        category,
        entityType: String(node.entity_type || "OTHER").toUpperCase(),
        color: NODE_STYLES[category].color,
        inFinding: affectedEntities.has(comparable(id)) || affectedEntities.has(comparable(label)),
        raw: node,
      };
    });
    const knownIds = new Set(nodes.map(node => node.id));
    const links = (result?.relationships || []).flatMap((relationship, index) => {
      const source = String(relationship.source || "");
      const target = String(relationship.target || "");
      if (!knownIds.has(source) || !knownIds.has(target)) return [];
      return [{
        id: `${source}:${target}:${relationship.relationship_type || index}`,
        source,
        target,
        label: relationship.relationship_type || "",
        document: relationship.document || "",
      }];
    });
    return { nodes, links };
  }, [affectedEntities, result]);

  const selectedNode = graphData.nodes.find(node => node.id === selectedId) || null;
  const selectedDocuments = useMemo(() => {
    if (!selectedNode || !result) return [];
    const nodeById = new Map(graphData.nodes.map(node => [node.id, node]));
    const documents = new Set(selectedNode.category === "DOCUMENT" ? [selectedNode.label] : []);
    result.relationships.forEach(relationship => {
      const source = endpointId(relationship.source);
      const target = endpointId(relationship.target);
      if (source !== selectedNode.id && target !== selectedNode.id) return;
      if (relationship.document) documents.add(relationship.document);
      const adjacent = nodeById.get(source === selectedNode.id ? target : source);
      if (adjacent?.category === "DOCUMENT") documents.add(adjacent.label);
    });
    return [...documents].filter(Boolean).sort();
  }, [graphData.nodes, result, selectedNode]);

  const relatedFindings = useMemo(() => {
    if (!selectedNode) return [];
    const candidates = [...(result?.related_findings || []), ...(currentFinding ? [currentFinding] : [])];
    const unique = new Map(candidates.filter(Boolean).map(finding => [finding.finding_id, finding]));
    return [...unique.values()].filter(finding => (finding.affected_assets || []).some(asset => comparable(asset) === comparable(selectedNode.id) || comparable(asset) === comparable(selectedNode.label)));
  }, [currentFinding, result, selectedNode]);

  const changeDepth = nextDepth => {
    setDepth(nextDepth);
    loadGraph(entity, nextDepth, includeContext);
  };

  const toggleContext = () => {
    const nextValue = !includeContext;
    setIncludeContext(nextValue);
    loadGraph(entity, depth, nextValue);
  };

  return <div className="plant-graph-view">
    <section className="graph-panel graph-explorer">
      <div className="graph-toolbar">
        <form onSubmit={event => { event.preventDefault(); loadGraph(entity, depth, includeContext); }} className="graph-entity-search"><Search size={15}/><input value={entity} onChange={event => setEntity(event.target.value)} placeholder="Entity ID or display name"/><button type="submit">Load graph</button></form>
        <div className="graph-depth"><span>DEPTH</span>{[1, 2].map(option => <button key={option} className={depth === option ? "active" : ""} onClick={() => changeDepth(option)} disabled={loading || !entity.trim()}>{option} hop{option > 1 ? "s" : ""}</button>)}<button className={includeContext ? "active" : ""} onClick={toggleContext} disabled={loading || !entity.trim()}>Raw context ({result?.context_nodes?.length || 0})</button></div>
      </div>
      <div className="graph-legend enterprise-legend">{visibleLegendTypes.filter(type => includeContext || type !== "PARAMETER").map(type => <span key={type}><i style={{ background: NODE_STYLES[type].color }}></i>{NODE_STYLES[type].label}</span>)}<span className="finding-legend"><i></i>Current finding</span></div>
      <div className="force-graph-shell" ref={containerRef}>
        {graphData.nodes.length > 0 && <GraphCanvas graphData={graphData} selectedId={selectedId} onNodeClick={node => setSelectedId(node.id)} width={width}/>} 
        {!loading && graphData.nodes.length === 0 && <div className="graph-empty"><Network size={27}/><strong>No graph context loaded</strong><p>Enter an entity from the Plant Knowledge Graph or run an investigation first.</p></div>}
        {loading && <div className="graph-loading"><Activity className="spin" size={21}/>Retrieving {depth}-hop graph context…</div>}
      </div>
      {error && <div className="graph-error"><AlertTriangle size={15}/>{error}</div>}
    </section>

    <aside className="graph-detail-panel">
      <div className="section-heading"><div><p className="eyebrow">SELECTED ENTITY</p><h2>{selectedNode?.label || "Select a node"}</h2></div>{selectedNode && <span className="graph-type" style={{ color: selectedNode.color }}>{NODE_STYLES[selectedNode.category].label}</span>}</div>
      {selectedNode ? <>
        {selectedNode.inFinding && <div className="finding-highlight"><AlertTriangle size={14}/> Involved in current finding</div>}
        <dl className="entity-properties">{Object.entries(selectedNode.raw).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{displayValue(value)}</dd></div>)}</dl>
        <section className="graph-linked-section"><h3><FileText size={14}/> Linked documents</h3>{selectedDocuments.length ? selectedDocuments.map(document => <span key={document}>{document}</span>) : <p>No document provenance returned for this entity.</p>}</section>
        <section className="graph-linked-section"><h3><AlertTriangle size={14}/> Related findings</h3>{relatedFindings.length ? relatedFindings.map(finding => <article key={finding.finding_id}><strong>{finding.finding_id}</strong><span className={`review-status ${(finding.status || "OPEN").toLowerCase()}`}>{finding.status || "OPEN"}</span><p>{finding.title || finding.root_cause}</p></article>) : <p>No related findings returned for this entity.</p>}</section>
      </> : <p className="graph-detail-empty">Click a node to center it and inspect its engineering context.</p>}
    </aside>
  </div>;
}
