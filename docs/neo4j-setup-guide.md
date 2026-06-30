# 🕸️ Neo4j Setup & Integration Guide for GraphRAG

This guide details how to install, configure, and integrate **Neo4j** into the GraphRAG pipeline as a scalable graph database replacement for the default file-based `GraphStore`.

---

## 1. Installation Options

Choose one of the following methods to run Neo4j locally or in the cloud.

### Option A: Running with Docker (Recommended)
This is the fastest method. Make sure you have Docker Desktop installed.

Run the following command in your terminal/PowerShell:
```bash
docker run \
  --name neo4j-graphrag \
  -p 7474:7474 -p 7687:7687 \
  -d \
  -v $HOME/neo4j/data:/data \
  -v $HOME/neo4j/logs:/logs \
  -v $HOME/neo4j/import:/var/lib/neo4j/import \
  -v $HOME/neo4j/plugins:/plugins \
  --env NEO4J_AUTH=neo4j/password \
  neo4j:latest
```
- **Port 7474**: HTTP console port (Neo4j Browser GUI).
- **Port 7687**: Bolt binary protocol port (Python connection driver).
- **Credentials**: Username `neo4j`, password `password` (change as needed).

---

### Option B: Neo4j Desktop (GUI Application)
If you prefer a graphical desktop app:
1. Download **Neo4j Desktop** from [neo4j.com/download-center](https://neo4j.com/download-center/).
2. Run the installer and open Neo4j Desktop.
3. Click **Add** -> **Local DBMS**.
4. Set the name, specify a password, and click **Create**.
5. Once created, hover over the database and click **Start**.

---

### Option C: Neo4j AuraDB (Cloud Hosted - Free Tier)
If you do not want to install anything locally:
1. Sign up at [neo4j.com/cloud/auradb](https://neo4j.com/cloud/auradb/).
2. Create a **Free Instance** (AuraDB Free).
3. Download the generated credentials file containing the Bolt URL (looks like `neo4j+s://xxxxxx.databases.neo4j.io`), username (`neo4j`), and password.

---

## 2. Accessing the Neo4j Browser Console

Once Neo4j is running (via Docker, Desktop, or AuraDB), open your browser and navigate to:
```text
http://localhost:7474
```
- Select Connection type: `bolt` (or `neo4j+s` for cloud AuraDB).
- Port: `7687`
- Username: `neo4j`
- Password: The password you set during installation.

This console allows you to run **Cypher** queries and interactively inspect nodes and relationship edges.

---

## 3. Environment Configuration

Add your Neo4j connection details to your project's local configuration file (`.env`):

```env
# Neo4j Graph Database Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
```

---

## 4. Python Integration

### Step 1: Install the Neo4j Driver
Install the official Neo4j python package in your project environment:
```bash
uv add neo4j
# or: pip install neo4j
```

### Step 2: Connection Adapter Code
Below is a helper script you can run (e.g. save to `scripts/sync_to_neo4j.py`) to sync the JSON-based `graph_store.json` records to your active Neo4j database:

```python
import json
from pathlib import Path
from neo4j import GraphDatabase

# 1. Configs
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "password"
GRAPH_STORE_FILE = Path("storage/local_pdf/graph_store.json")

def sync_graph():
    if not GRAPH_STORE_FILE.exists():
        print(f"Error: {GRAPH_STORE_FILE} not found!")
        return

    # Load local adjacency lists
    with open(GRAPH_STORE_FILE, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    # Initialize Neo4j driver
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    with driver.session() as session:
        print("Connected to Neo4j. Clearing previous graph...")
        # Clear existing nodes & edges
        session.run("MATCH (n) DETACH DELETE n")

        print("Populating entities and relations...")
        for head, edges in graph_data.items():
            # Create/Merge Head Entity Node
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
                
        print("Sync complete!")
    driver.close()

if __name__ == "__main__":
    sync_graph()
```

Run this script:
```bash
uv run scripts/sync_to_neo4j.py
```

---

## 5. Visualizing the Graph (Cypher Basics)

Inside the Neo4j Browser Console (`http://localhost:7474`), run the following commands to inspect the knowledge graph:

- **Get all nodes and relationships (up to limit 50)**:
  ```cypher
  MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50
  ```
- **Find neighbors of a specific entity (e.g., "VF 8")**:
  ```cypher
  MATCH (h:Entity {name: "VF 8"})-[r]->(t) RETURN h, r, t
  ```
- **Search relationships with a specific type label (e.g., "COOCCUR")**:
  ```cypher
  MATCH (n)-[r:RELATION {type: "COOCCUR"}]->(m) RETURN n, r, m LIMIT 25
  ```
