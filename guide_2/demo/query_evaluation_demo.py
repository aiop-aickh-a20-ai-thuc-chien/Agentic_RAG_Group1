import os
import sys
import html
import json
import time
import pathlib
from typing import Any, Dict, List

# Add project root to sys.path to resolve imports
project_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv()

from agentic_rag.runtime_env import load_local_env
load_local_env()

from agentic_rag.generation.evidence import source_provider_from_env
from agentic_rag.core.contracts import RetrievalInput, LLMCompletionInput
from agentic_rag.model_runtime.factory import get_llm_client
from agentic_rag.retrieval.graph_store import GraphStore

# Configure UTF-8 stdout for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Questions definition
EVALUATION_QUESTIONS = [
    {
        "id": "Q1",
        "question": "Có bao nhiêu màu cho các loại xe VF9 Eco, Plus 7 chỗ, Plus cơ trưởng ?",
        "seeds": ["VF9", "VF 9", "ECO", "PLUS", "CƠ TRƯỞNG"]
    },
    {
        "id": "Q2",
        "question": "Thống kê các khoản chi và chi phí lăn bánh cuối cùng là bao nhiêu khi tôi chọn VF9 ECO màu đen huyền với quyền lợi thành viên VinClub Bạch Kim ?",
        "seeds": ["VF9", "VF 9", "CHI PHÍ LĂN BÁNH"]
    },
    {
        "id": "Q3",
        "question": "Dự toán trả góp hàng tháng cho xe VF 9 Plus khi vay 70% giá trị xe tại ngân hàng BIDV trong thời hạn 60 tháng là bao nhiêu?",
        "seeds": ["VF9", "VF 9", "DỰ TOÁN TRẢ GÓP", "BIDV", "60 THÁNG"]
    }
]

def generate_answer(llm_client: Any, question: str, context: str) -> str:
    """Uses LLM to synthesize answer from retrieved context."""
    if not llm_client:
        return "LLM Generation skipped (No active LLM credentials)."
        
    prompt = f"""
    Bạn là trợ lý thông tin xe VinFast. Trả lời câu hỏi của người dùng dựa vào ngữ cảnh sau:
    ---
    Ngữ cảnh:
    {context}
    ---
    Câu hỏi:
    {question}
    
    Hãy viết câu trả lời chi tiết, chính xác dựa trên các thông số trong ngữ cảnh. Không tự bịa thông tin và tuân thủ các hướng dẫn bảo vệ (guardrails).
    """
    
    system_message = (
        "You are the primary Synthesizer for the VinNavigator GraphRAG pipeline.\n\n"
        "When answering questions about car colors, pricing configurations, or math-heavy loan rules:\n"
        "1. CHECK YOUR CONTEXT: Scan both the graph schema properties and text chunks for matching trims (\"Eco\", \"Plus 7 chỗ\", \"Plus cơ trưởng\").\n"
        "2. VALIDATE MISSING VARIABLES: If a cell in a Markdown table is empty (e.g., \"| Lãi suất (%) | % |\") or text chunks mention generic placeholders like \"Màu cơ bản/Màu nâng cao\" without specifying names, DO NOT simply say \"Information is not available.\"\n"
        "3. EXECUTE THE VALIDATION PROTOCOL: Clearly state exactly what raw information was found in the text context, identify what crucial variables are missing from the current database state, and list the exact missing parameters required to compute or supply the final answer.\n\n"
        "Follow these strict guardrails:\n"
        "1. ABSENCE OF DATA / COLOR COUNTING:\n"
        "- If the user asks for the number or names of available colors, check the context for specific text descriptions or image-substitute attributes (e.g., color names, counts).\n"
        "- If the text chunks only contain generic placeholders (such as \"Màu cơ bản\" or \"Màu nâng cao\") without specific names or numbers, explicitly state that the specific colors and exact counts are not present in the current database. Do not guess.\n\n"
        "2. EMPTY DATA TABLES & INTEREST RATES (\"TRẢ GÓP\"):\n"
        "- When asked to calculate financial projections, loan installments (trả góp), or specific bank rates (e.g., BIDV), inspect the retrieved data tables for missing values.\n"
        "- If a column like \"Lãi suất (%)\" contains empty percentages or placeholders (e.g., \"%\"), DO NOT assume a hidden rate or guess a default unless explicitly instructed by the user's query parameters.\n"
        "- Instead, clearly identify which piece of data is missing from the source website, explain what is needed (e.g., \"The exact interest rate for BIDV is not specified in the data\"), and offer a clear, step-by-step mathematical breakdown using a clearly labeled, hypothetical placeholder rate (e.g., \"Assuming a baseline rate of X% for demonstration purposes...\").\n\n"
        "3. MULTIMODAL / TEXT SUBSTITUTES:\n"
        "- Look out for any structured blocks labeled as image descriptions or color attributes. Treat these text substitutes as ground truth for what the vehicle looks like.\n\n"
        "Tone: Professional, technically precise, and transparent about data limitations.\n"
        "Language: Match the language of the user's query (Vietnamese or English)."
    )
    
    try:
        res = llm_client.complete(
            LLMCompletionInput(
                prompt=prompt,
                system_message=system_message,
                temperature=0.0
            )
        )
        return res.text.strip()
    except Exception as e:
        return f"Error during LLM answer generation: {e}"

def build_html_report(results: List[Dict[str, Any]], store: GraphStore, output_path: pathlib.Path) -> None:
    provider_str = "Neo4j AuraDB (Cloud)" if store.use_neo4j else "Local JSON Adjacency File"
    
    query_sections = []
    for r in results:
        q_escaped = html.escape(r["question"])
        ans_escaped = html.escape(r["answer"]).replace("\n", "<br>")
        
        # Build neighbor badges
        neighbors_html = " ".join([f'<span class="badge badge-neighbor">{html.escape(n)}</span>' for n in r["neighbors"]]) or '<span class="empty-msg">No graph neighbors expanded.</span>'
        seed_badges = " ".join([f'<span class="badge badge-seed">{html.escape(s)}</span>' for s in r["seeds"]])
        
        # Build chunks list
        chunk_cards = []
        for idx, res in enumerate(r["chunks"], 1):
            meta = res.chunk.metadata
            src = meta.get("source") or meta.get("file_name") or "unknown"
            page = meta.get("page_number")
            page_str = f" | Page {page}" if page else ""
            score = res.score
            retriever = res.retriever
            
            chunk_cards.append(
                f"""
                <div class="chunk-card">
                    <div class="chunk-header">
                        <strong>[{idx}] {html.escape(src)}{page_str}</strong>
                        <span class="chunk-meta">Score: {score:.4f} | {html.escape(retriever)}</span>
                    </div>
                    <pre class="chunk-text">{html.escape(res.chunk.text.strip())}</pre>
                </div>
                """
            )
        chunks_html = "".join(chunk_cards) or '<div class="empty-msg">No relevant document chunks retrieved.</div>'
        
        query_sections.append(
            f"""
            <div class="glass-card query-block">
                <h2>❓ Query: {q_escaped}</h2>
                <div class="grid">
                    <!-- Graph context -->
                    <div class="graph-context">
                        <h3>🕸️ Graph Store BFS Expansion</h3>
                        <div class="subsection">
                            <strong>Query Seeds:</strong>
                            <div class="badge-container">{seed_badges}</div>
                        </div>
                        <div class="subsection">
                            <strong>Expanded Entity Neighbors (BFS Depth=1):</strong>
                            <div class="badge-container">{neighbors_html}</div>
                        </div>
                    </div>
                    
                    <!-- Synthesized Answer -->
                    <div class="llm-answer">
                        <h3>🤖 Synthesized Answer</h3>
                        <div class="answer-box">{ans_escaped}</div>
                    </div>
                </div>
                
                <!-- Retrieved Evidence Chunks -->
                <button type="button" class="collapsible">📚 View Retrieved Chunks ({len(r["chunks"])})</button>
                <div class="collapsible-content">
                    {chunks_html}
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
        <title>GraphRAG + RAG Hybrid Evaluation Panel</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #090b11;
                --card-bg: rgba(22, 28, 45, 0.4);
                --card-border: rgba(255, 255, 255, 0.08);
                --text: #e2e8f0;
                --text-muted: #94a3b8;
                --primary: #4f46e5;
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
                font-size: 2.3rem;
                background: linear-gradient(135deg, #fff 0%, var(--text-muted) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
            }}
            .container {{ max-width: 1200px; margin: auto; }}
            
            .header-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2.5rem;
                border-bottom: 1px solid var(--card-border);
                padding-bottom: 1.5rem;
            }}
            .status-indicator {{
                font-weight: 600;
                font-size: 0.9rem;
                background: var(--card-bg);
                padding: 0.5rem 1rem;
                border-radius: 99px;
                border: 1px solid var(--card-border);
            }}
            
            .glass-card {{
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                padding: 2rem;
                margin-bottom: 2.5rem;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            }}
            
            .grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 2rem;
                margin-top: 1.5rem;
                margin-bottom: 1.5rem;
            }}
            @media (max-width: 900px) {{
                .grid {{ grid-template-columns: 1fr; }}
            }}
            
            /* Graph Section */
            .subsection {{ margin-bottom: 1.2rem; }}
            .badge-container {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 99px;
                font-weight: 600;
                font-size: 0.85rem;
                color: #fff;
            }}
            .badge-seed {{ background-color: var(--primary); }}
            .badge-neighbor {{ background-color: var(--accent); }}
            
            /* Answer Box */
            .answer-box {{
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid var(--card-border);
                border-radius: 8px;
                padding: 1.2rem;
                font-size: 0.95rem;
                line-height: 1.7;
                color: #f8fafc;
                border-left: 4px solid var(--secondary);
            }}
            
            /* Collapsible Section */
            .collapsible {{
                background-color: rgba(255,255,255,0.05);
                color: var(--text);
                cursor: pointer;
                padding: 12px;
                width: 100%;
                border: 1px solid var(--card-border);
                text-align: left;
                outline: none;
                font-size: 0.95rem;
                font-weight: 600;
                border-radius: 6px;
                transition: background-color 0.2s;
            }}
            .collapsible:hover, .active {{ background-color: rgba(255,255,255,0.1); }}
            .collapsible-content {{
                padding: 1rem;
                display: none;
                background-color: rgba(0,0,0,0.15);
                border: 1px solid var(--card-border);
                border-top: none;
                border-radius: 0 0 6px 6px;
            }}
            
            /* Chunks */
            .chunk-card {{
                background: rgba(15, 23, 42, 0.4);
                border: 1px solid var(--card-border);
                border-radius: 6px;
                padding: 1rem;
                margin-bottom: 1rem;
            }}
            .chunk-header {{
                display: flex;
                justify-content: space-between;
                font-size: 0.85rem;
                color: var(--text-muted);
                border-bottom: 1px solid rgba(255,255,255,0.05);
                padding-bottom: 0.5rem;
                margin-bottom: 0.8rem;
            }}
            .chunk-text {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                font-size: 0.9rem;
                white-space: pre-wrap;
                margin: 0;
                color: #e2e8f0;
            }}
            .empty-msg {{ color: var(--text-muted); font-style: italic; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-bar">
                <div>
                    <h1>GraphRAG + RAG Hybrid Evaluation Panel</h1>
                    <p style="color: var(--text-muted); margin: 0;">Evaluation of VF 9 dynamic-data configurations & dynamic pricing queries</p>
                </div>
                <div class="status-indicator">
                    <span>Graph Provider: <strong>{provider_str}</strong></span>
                </div>
            </div>

            {''.join(query_sections)}

            <script>
                var coll = document.getElementsByClassName("collapsible");
                for (var i = 0; i < coll.length; i++) {{
                    coll[i].addEventListener("click", function() {{
                        this.classList.toggle("active");
                        var content = this.nextElementSibling;
                        if (content.style.display === "block") {{
                            content.style.display = "none";
                        }} else {{
                            content.style.display = "block";
                        }}
                    }});
                }}
            </script>
        </div>
    </body>
    </html>
    """
    report_path = output_path / "query_evaluation.html"
    report_path.write_text(html_content, encoding="utf-8")
    print(f"\nEvaluation HTML Report generated at: {report_path.resolve()}")

def main():
    print("=========================================================")
    print("  Initializing Retrieval & Graph Connection Providers    ")
    print("=========================================================")
    
    # 1. Initialize RAG evidence provider
    try:
        provider = source_provider_from_env()
    except Exception as e:
        print(f"Error: Failed to initialize source evidence provider: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Initialize local GraphStore (which now resolves Neo4j)
    store = GraphStore()
    
    # 3. Initialize LLM client
    llm_client = get_llm_client("generation") or get_llm_client("ingestion")
    
    results = []
    
    # 4. Loop queries
    for q_item in EVALUATION_QUESTIONS:
        qid = q_item["id"]
        query = q_item["question"]
        seeds = q_item["seeds"]
        
        print(f"\n[{qid}] Query: '{query}'")
        
        # 4a. Run Graph Store BFS Neighbor expansion
        print(" -> Querying GraphStore BFS neighbors...")
        neighbors = store.get_neighbors(seeds, max_depth=1)
        print(f"    Neighbors found: {neighbors}")
        
        # 4b. Run Hybrid Retrieval
        print(" -> Querying Qdrant / Local vector database chunks...")
        retrieval_res = provider.retrieve(RetrievalInput(question=query))
        chunks = retrieval_res.results
        print(f"    Retrieved {len(chunks)} chunks.")
        
        # 4c. Construct context text
        context_text = "\n\n".join([c.chunk.text for c in chunks])
        
        # 4d. Synthesize Answer
        print(" -> Generating synthesized LLM answer...")
        answer = generate_answer(llm_client, query, context_text)
        
        results.append({
            "id": qid,
            "question": query,
            "seeds": seeds,
            "neighbors": neighbors,
            "chunks": chunks,
            "answer": answer
        })
        
    # 5. Output reports
    output_dir = project_root / "guide_2" / "demo" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    build_html_report(results, store, output_dir)
    print("\nEvaluation successfully completed!")

if __name__ == "__main__":
    main()
