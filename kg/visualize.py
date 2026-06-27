"""Interactive graph visualization -> self-contained HTML (vis-network via CDN)."""

from __future__ import annotations

import json

from kg.store import GraphStore

_TYPE_COLORS = {
    "product": "#2563eb",
    "org": "#dc2626",
    "feature": "#16a34a",
    "policy": "#9333ea",
    "value": "#d97706",
    "location": "#0891b2",
    "": "#64748b",
}

_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>/*TITLE*/</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0}
  header{padding:12px 18px;background:#111827;border-bottom:1px solid #334155}
  header h1{margin:0;font-size:16px}
  header span{color:#94a3b8;font-size:12px}
  #wrap{display:flex;height:calc(100vh - 52px)}
  #graph{flex:1;background:#0b1220}
  #side{width:320px;border-left:1px solid #334155;padding:14px;overflow:auto;background:#0f172a;font-size:13px}
  .legend span{display:inline-block;margin:2px 8px 2px 0}
  .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}
  .ev{color:#94a3b8;border-left:2px solid #334155;padding-left:8px;margin:6px 0}
  h3{margin:10px 0 4px;font-size:13px;color:#cbd5e1}
  code{color:#38bdf8}
</style>
</head>
<body>
<header><h1>/*TITLE*/</h1> <span>/*SUBTITLE*/ — bấm vào một node để xem quan hệ & bằng chứng</span></header>
<div id="wrap">
  <div id="graph"></div>
  <div id="side">
    <div class="legend" id="legend"></div>
    <div id="detail"><p style="color:#94a3b8">Chọn một node…</p></div>
  </div>
</div>
<script>
const NODES = /*NODES*/;
const EDGES = /*EDGES*/;
const COLORS = /*COLORS*/;
const visNodes = NODES.map(n => ({
  id:n.id, label:n.label, group:n.type,
  color:{background:COLORS[n.type]||COLORS[""],border:"#0b1220"},
  font:{color:"#e2e8f0"}, value:1+(n.freq||1), shape:"dot"
}));
const visEdges = EDGES.map((e,i) => ({
  id:i, from:e.source, to:e.target, label:e.predicate, arrows:"to",
  color:{color:"#475569"}, font:{color:"#94a3b8",size:11,strokeWidth:0}, width:1+(e.weight||1)*0.6
}));
const nodeById = Object.fromEntries(NODES.map(n=>[n.id,n]));
const network = new vis.Network(document.getElementById("graph"),
  {nodes:new vis.DataSet(visNodes), edges:new vis.DataSet(visEdges)},
  {physics:{stabilization:true,barnesHut:{springLength:140}},interaction:{hover:true}});
// legend
const seen=[...new Set(NODES.map(n=>n.type))];
document.getElementById("legend").innerHTML = "<h3>Loại node</h3>" + seen.map(t=>
  `<span><i class="dot" style="background:${COLORS[t]||COLORS[""]}"></i>${t||"(none)"}</span>`).join("");
// click detail
network.on("click", p => {
  if(!p.nodes.length){return;}
  const id=p.nodes[0], n=nodeById[id];
  const rel = EDGES.filter(e=>e.source===id||e.target===id).map(e=>{
    const dir = e.source===id ? "→" : "←";
    const other = e.source===id ? e.target : e.source;
    const on = nodeById[other];
    const ev = (e.evidence||[]).map(x=>`<div class="ev">“${x}”</div>`).join("");
    return `<div><code>${n.label}</code> ${dir} <b>${e.predicate}</b> ${dir} <code>${on?on.label:other}</code>${ev}</div>`;
  }).join("");
  document.getElementById("detail").innerHTML =
    `<h3>${n.label}</h3><div>type: <b>${n.type||"-"}</b> · aliases: ${(n.aliases||[]).join(", ")}</div><h3>Quan hệ</h3>${rel||"(không có)"}`;
});
</script>
</body>
</html>
"""


def render_graph_html(
    store: GraphStore, path: str, title: str = "Knowledge Graph", subtitle: str = ""
) -> None:
    data = store.to_node_link()
    html = (
        _TEMPLATE.replace("/*TITLE*/", title)
        .replace("/*SUBTITLE*/", subtitle)
        .replace("/*NODES*/", json.dumps(data["nodes"], ensure_ascii=False))
        .replace("/*EDGES*/", json.dumps(data["edges"], ensure_ascii=False))
        .replace("/*COLORS*/", json.dumps(_TYPE_COLORS, ensure_ascii=False))
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
