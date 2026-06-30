import os
import json
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load environment variables from .env
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
# Neo4j AuraDB default username is typically 'neo4j', fallback to env value if overridden.
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
GRAPH_STORE_FILE = Path("storage/local_pdf/graph_store.json")

def sync_graph():
    if not NEO4J_URI or not NEO4J_PASSWORD:
        print("Error: NEO4J_URI or NEO4J_PASSWORD environment variables are not set!")
        return

    if not GRAPH_STORE_FILE.exists():
        print(f"Error: {GRAPH_STORE_FILE} not found!")
        return

    # Load local adjacency lists
    with open(GRAPH_STORE_FILE, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    # Initialize Neo4j driver
    print(f"Connecting to Neo4j AuraDB at {NEO4J_URI} as user '{NEO4J_USERNAME}'...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            print("Connected successfully! Clearing any previous nodes/edges...")
            # Clear existing database
            session.run("MATCH (n) DETACH DELETE n")

            print("Uploading entities and relations...")
            count = 0
            for head, edges in graph_data.items():
                # Create/Merge Head Node
                session.run(
                    "MERGE (h:Entity {name: $name})",
                    name=head
                )
                
                for edge in edges:
                    tail = edge["neighbor"]
                    relation = edge["relation"]
                    strength = float(edge["strength"])

                    # Cypher query merging Tail node and writing directed Relationship edge
                    query = (
                        "MERGE (h:Entity {name: $head_name}) "
                        "MERGE (t:Entity {name: $tail_name}) "
                        f"MERGE (h)-[r:RELATION {{type: $relation_type, strength: $strength}}]->(t)"
                    )
                    session.run(
                        query,
                        head_name=head,
                        tail_name=tail,
                        relation_type=relation.upper(),
                        strength=strength
                    )
                    count += 1
                    
            print(f"Sync complete! Uploaded graph with {len(graph_data)} nodes and {count} relationships.")
    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    sync_graph()
