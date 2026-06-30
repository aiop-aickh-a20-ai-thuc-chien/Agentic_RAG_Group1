import os
import html
import json
import pathlib
import sys
from typing import Any, Dict, List

# Add project root to sys.path to resolve imports
project_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
load_dotenv()

from src.agentic_rag.retrieval.graph_store import GraphStore

def fetch_graph_data(store: GraphStore) -> Dict[str, Any]:
    """Fetches all nodes, relationships, and calculates stats depending on provider."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    
    if store.use_neo4j:
        try:
            with store.driver.session() as session:
                # Fetch all nodes
                nodes_res = session.run("MATCH (n:Entity) RETURN n.name AS name")
                for record in nodes_res:
                    name = record["name"]
                    # Count degrees/relationships of this node
                    deg_res = session.run("MATCH (n:Entity {name: $name})-[r]-() RETURN count(r) AS deg", name=name)
                    deg = deg_res.single()["deg"]
                    nodes.append({"name": name, "degree": deg})
                
                # Fetch all relations
                edges_res = session.run("MATCH (h:Entity)-[r:RELATION]->(t:Entity) RETURN h.name AS head, type(r) AS relation, t.name AS tail, r.strength AS strength")
                for record in edges_res:
                    edges.append({
                        "head": record["head"],
                        "relation": record["relation"],
                        "tail": record["tail"],
                        "strength": record["strength"]
                    })
        except Exception as e:
            print(f"Error querying Neo4j database: {e}", file=sys.stderr)
    else:
        # File fallback
        for node, neighbors in store.adj.items():
            nodes.append({"name": node, "degree": len(neighbors)})
            for edge in neighbors:
                # Avoid duplicate printing in undirected display list
                if node < edge["neighbor"]:
                    edges.append({
                        "head": node,
                        "relation": edge["relation"].upper(),
                        "tail": edge["neighbor"],
                        "strength": edge["strength"]
                    })
                    
    # Sort lists
    nodes.sort(key=lambda x: x["degree"], reverse=True)
    edges.sort(key=lambda x: x["head"])
    return {"nodes": nodes, "edges": edges}

def run_bfs_simulations(store: GraphStore) -> List[Dict[str, Any]]:
    """Runs a series of neighbor lookup simulations for standard seed concepts."""
    test_seeds = ["VF 8", "VF 9", "PIN", "SẠC", "ECO", "PLUS", "THUÊ PIN"]
    simulations = []
    for seed in test_seeds:
        # Perform 1-hop BFS
        neighbors_1 = store.get_neighbors([seed], max_depth=1)
        # Perform 2-hop BFS
        neighbors_2 = store.get_neighbors([seed], max_depth=2)
        
        simulations.append({
            "seed": seed,
            "neighbors_1": neighbors_1,
            "neighbors_2": neighbors_2
        })
    return simulations

def generate_html_report(
    store: GraphStore,
    graph: Dict[str, Any],
    simulations: List[Dict[str, Any]],
    output_dir: pathlib.Path
):
    """Generates a premium dark-themed HTML dashboard emulating the graph frontend."""
    
    # 1. Status and Provider variables
    provider_str = "Neo4j AuraDB (Cloud)" if store.use_neo4j else "Local JSON Adjacency File Store"
    host_str = store.neo4j_uri if store.use_neo4j else str(store.filepath.resolve())
    status_class = "status-active" if store.use_neo4j or store.filepath.exists() else "status-inactive"
    
    # 2. Render Node Table rows
    node_rows = []
    for n in graph["nodes"]:
        node_rows.append(
            f"""<tr>
                <td><strong>{html.escape(n["name"])}</strong></td>
                <td><span class="badge">{n["degree"]}</span></td>
            </tr>"""
        )
        
    # 3. Render Edge Table rows
    edge_rows = []
    for e in graph["edges"]:
        edge_rows.append(
            f"""<tr>
                <td><strong>{html.escape(e["head"])}</strong></td>
                <td><span class="relation-label">{html.escape(e["relation"])}</span></td>
                <td><strong>{html.escape(e["tail"])}</strong></td>
                <td><code>{e["strength"]}</code></td>
            </tr>"""
        )

    # 4. Render BFS Simulation rows
    sim_cards = []
    for sim in simulations:
        n1_badges = " ".join([f'<span class="badge badge-n1">{html.escape(n)}</span>' for n in sim["neighbors_1"]]) or '<span class="empty-msg">No 1-hop neighbors found.</span>'
        n2_badges = " ".join([f'<span class="badge badge-n2">{html.escape(n)}</span>' for n in sim["neighbors_2"]]) or '<span class="empty-msg">No 2-hop neighbors found.</span>'
        
        sim_cards.append(
            f"""
            <div class="glass-card simulation-card">
                <h3>🔍 Expansion Seed: <span class="seed-text">"{html.escape(sim["seed"])}"</span></h3>
                <div class="hop-section">
                    <strong>1-Hop Neighbors (Depth = 1):</strong>
                    <div class="badge-container">{n1_badges}</div>
                </div>
                <div class="hop-section">
                    <strong>2-Hop Neighbors (Depth = 2):</strong>
                    <div class="badge-container">{n2_badges}</div>
                </div>
            </div>
            """
        )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GraphRAG Database Review & Emulator</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #090b11;
                --card-bg: rgba(22, 28, 45, 0.4);
                --card-border: rgba(255, 255, 255, 0.08);
                --text: #e2e8f0;
                --text-muted: #94a3b8;
                --primary: #4f46e5;
                --primary-glow: rgba(79, 70, 229, 0.4);
                --secondary: #10b981;
                --accent: #f59e0b;
                --code-bg: rgba(15, 23, 42, 0.6);
            }}
            * {{ box-sizing: border-box; }}
            body {{
                font-family: "Plus Jakarta Sans", sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 2rem;
                background-image: radial-gradient(circle at 10% 20%, rgba(31, 38, 103, 0.1) 0%, rgba(9, 11, 17, 1) 90%);
            }}
            h1, h2, h3 {{ font-weight: 800; margin-top: 0; }}
            h1 {{
                font-size: 2.5rem;
                background: linear-gradient(135deg, #fff 0%, var(--text-muted) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
            }}
            .container {{ max-width: 1400px; margin: auto; }}
            
            /* Status header bar */
            .header-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2.5rem;
                border-bottom: 1px solid var(--card-border);
                padding-bottom: 1.5rem;
            }}
            .status-indicator {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-weight: 600;
                font-size: 0.9rem;
                background: var(--card-bg);
                padding: 0.5rem 1rem;
                border-radius: 99px;
                border: 1px solid var(--card-border);
            }}
            .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
            .status-active .dot {{ background-color: var(--secondary); box-shadow: 0 0 8px var(--secondary); }}
            .status-inactive .dot {{ background-color: #ef4444; box-shadow: 0 0 8px #ef4444; }}

            /* Glassmorphism Cards */
            .glass-card {{
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                padding: 1.5rem;
                margin-bottom: 2rem;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            }}
            
            /* Stats Section */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2.5rem;
            }}
            .stat-value {{ font-size: 2.5rem; font-weight: 800; color: #fff; margin-top: 0.5rem; }}

            /* Tables */
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
            th, td {{ padding: 14px; text-align: left; border-bottom: 1px solid var(--card-border); }}
            th {{ font-weight: 600; color: #fff; background-color: rgba(255, 255, 255, 0.02); }}
            tr:hover {{ background-color: rgba(255, 255, 255, 0.01); }}
            
            /* Badges & Labels */
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 99px;
                font-weight: 600;
                font-size: 0.85rem;
                background-color: var(--primary);
                color: #fff;
            }}
            .badge-n1 {{ background-color: var(--secondary); }}
            .badge-n2 {{ background-color: var(--accent); }}
            .relation-label {{
                background: rgba(245, 158, 11, 0.1);
                color: var(--accent);
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.8rem;
                font-weight: bold;
                font-family: 'JetBrains Mono', monospace;
            }}
            code {{
                font-family: 'JetBrains Mono', monospace;
                background: var(--code-bg);
                padding: 2px 6px;
                border-radius: 4px;
                color: #f43f5e;
            }}

            /* Simulation Cards */
            .seed-text {{ color: #a5b4fc; font-family: 'JetBrains Mono', monospace; }}
            .hop-section {{ margin-top: 1rem; padding: 0.8rem; background: rgba(0,0,0,0.2); border-radius: 8px; }}
            .badge-container {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
            .empty-msg {{ color: var(--text-muted); font-style: italic; font-size: 0.9rem; }}

            /* Grid Layout for details */
            .details-grid {{
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: 2rem;
            }}
            @media (max-width: 900px) {{
                .details-grid {{ grid-template-columns: 1fr; }}
            }}
            
            .table-container {{
                max-height: 500px;
                overflow-y: auto;
                border: 1px solid var(--card-border);
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-bar">
                <div>
                    <h1>GraphRAG Database Monitor</h1>
                    <p style="color: var(--text-muted); margin: 0;">Onboarding visualizer and BFS expansion simulator</p>
                </div>
                <div class="status-indicator {status_class}">
                    <span class="dot"></span>
                    <span>{provider_str}</span>
                </div>
            </div>

            <!-- Stats grid -->
            <div class="stats-grid">
                <div class="glass-card">
                    <span style="color: var(--text-muted); font-size: 0.9rem; font-weight: 600;">Total Entities (Nodes)</span>
                    <div class="stat-value">{len(graph["nodes"])}</div>
                </div>
                <div class="glass-card">
                    <span style="color: var(--text-muted); font-size: 0.9rem; font-weight: 600;">Total Relationships (Edges)</span>
                    <div class="stat-value">{len(graph["edges"])}</div>
                </div>
                <div class="glass-card" style="grid-column: span 1;">
                    <span style="color: var(--text-muted); font-size: 0.9rem; font-weight: 600;">Connected Target Host</span>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; margin-top: 0.8rem; word-break: break-all; color: #a5b4fc;">{host_str}</div>
                </div>
            </div>

            <!-- BFS Emulator -->
            <h2>⚡ BFS Neighbor Expansion Emulator</h2>
            <p style="color: var(--text-muted); margin-bottom: 1.5rem;">Emulates query routing pre-filter behavior by traversing the entity graph for common query seed terms.</p>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 1.5rem; margin-bottom: 3rem;">
                {''.join(sim_cards)}
            </div>

            <!-- Detailed Grid Tables -->
            <div class="details-grid">
                <!-- Nodes -->
                <div>
                    <h2>🏷️ Entities Adjacency</h2>
                    <div class="glass-card" style="padding: 0;">
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Entity Name</th>
                                        <th>Degree</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {''.join(node_rows)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Edges -->
                <div>
                    <h2>🔗 Relationships Index</h2>
                    <div class="glass-card" style="padding: 0;">
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Head Entity</th>
                                        <th>Relation</th>
                                        <th>Tail Entity</th>
                                        <th>Weight</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {''.join(edge_rows)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    report_path = output_dir / "neo4j_review.html"
    report_path.write_text(html_content, encoding="utf-8")
    print(f"Graph emulator dashboard generated: {report_path.resolve()}")

def main():
    output_dir = project_root / "guide_2" / "demo" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Initializing GraphStore driver...")
    store = GraphStore()
    
    print("Fetching graph nodes and relationships...")
    graph = fetch_graph_data(store)
    
    print("Running BFS neighbor lookup simulations...")
    simulations = run_bfs_simulations(store)
    
    print("Writing HTML dashboard...")
    generate_html_report(store, graph, simulations, output_dir)
    print("Done!")

if __name__ == "__main__":
    main()
