# Axon Project: Master Roadmap & Architecture

**Project Name:** Axon MCP Server  
**Architecture Version:** 3.2 (Production Ready / Hybrid)  
**Core Philosophy:** "Sub-second Latency for Users, Deep Intelligence via Background Async."  
**Date:** 2025-12-12

---

## Part I: Background & Analysis Findings
*(Summary of the Gap Analysis & Strategic Pivot that led to v3.2)*

### 1. The Semantic Gap (Current State)
Axon started as a **Structural Analyzer** (Roslyn/Tree-sitter) that could index code and map API topology. However, it lacked:
- **Domain Context**: No concept of "Bounded Contexts" (e.g., Sales vs. Shipping).
- **Business Intent**: Known *what* code exists, but not *why*.
- **Infrastructure Awareness**: No visibility into Redis, RabbitMQ, or S3 dependencies.

### 2. The Strategic Pivot (Red Team Critique)
We initially proposed a complex "Knowledge Graph" (Neo4j) + "Real-time LLM" approach. This was rejected due to:
- **Latency Trap**: 3-8s query latency (Unacceptable for chat).
- **Stale Graph**: Impossible to keep a graph in sync with 50+ commits/day.
- **Complexity**: Over-engineered for what is essentially a "Search" problem.

**The Decision**: Adopt a **Pragmatic Hybrid Architecture** (v3.2) described below.

---

## Part II: Architecture Specification (Axon v3.2)

### 1. Executive Summary & Architecture Strategy
* **The Problem:** Traditional "Knowledge Graphs" are too slow (3-8s latency) and expensive to build in real-time. Pure "Grep" tools lack understanding of Business Intent.
* **The Solution:** A **Hybrid "Fast/Slow" Architecture**.
    * **Fast Loop (Synchronous):** A SQL-backed index providing instant structural search (<50ms).
    * **Slow Loop (Asynchronous):** A background worker using a local 120B LLM to "read" code, extract intent, and generate vector embeddings over time.
* **Key Capabilities:**
    * Instant structural navigation (Find Class/Method).
    * Semantic discovery ("Where is the logic for refunds?").
    * Infrastructure awareness (Redis, RabbitMQ detection).
    * Self-healing cache (Smart invalidation on file edits).

### 2. Data Layer Specification (PostgreSQL + PGVector)
* **Extension Requirement:** Enable `vector` extension (pgvector) for semantic similarity.
* **Table 1: `code_index` (The Search Node)**
    * `id` (PK): Unique identifier.
    * `service_name` (Text): The Bounded Context/Project (e.g., "Order.API").
    * `file_path` (Text): Physical location.
    * `file_hash` (Text): MD5/SHA256 of the content (Critical for cache invalidation).
    * `symbol_name` (Text): Class/Method name (e.g., "SubmitOrder").
    * `symbol_type` (Text): e.g., "class", "interface", "endpoint", **"infrastructure"** (NEW).
    * `ai_enrichment` (JSONB): Stores "Business Goal", "Ubiquitous Language", "Infra Dependencies".
    * `embedding` (Vector[768]): The semantic vector representation of the summary.
* **Table 2: `code_relations` (The Graph Skeleton)**
    * `source_id` (FK): The caller.
    * `target_id` (FK): The callee.
    * `relation_type` (Text): e.g., "calls", "inherits", "publishes_event".
* **Indexes:**
    * B-Tree on `symbol_name`, `service_name` (For exact lookups).
    * HNSW/IVFFlat on `embedding` (For fast vector search).

### 3. Component 1: The Indexer (Synchronous / Fast Path)
* **Technology:** C# Console App (Roslyn) or Tree-sitter.
* **Target Files:** 
    * **Source Code:** `*.cs` (C#), `*.ts` (TypeScript).
    * **Infrastructure/Config:** `Dockerfile`, `*.yaml` (k8s/docker-compose), `*.json` (appsettings), `*.tf` (Terraform).
* **Trigger:** Runs on startup or file watcher event.
* **Logic (The "Cache Invalidation" Strategy):**
    1.  Calculate current `file_hash` on disk.
    2.  Compare with stored `file_hash` in DB.
    3.  **If Match:** Do nothing (Skip analysis).
    4.  **If Mismatch:**
        * Update `symbol_name`, `line_range`, `service_name`.
        * **Infrastructure Handling:** If file is config (e.g., `k8s.yaml`), set `symbol_type = "infrastructure"`.
        * **CRITICAL:** Set `ai_enrichment = NULL` and `embedding = NULL`.
        * *Why:* This signals the Background Worker that this file is "fresh" and needs re-thinking (especially for extracting infra dependencies).

### 4. Component 2: The Brain (Asynchronous / Slow Path)
* **Technology:** Python Script + External Ollama Service.
* **Trigger:** Polling loop querying `WHERE ai_enrichment IS NULL`.
* **The 120B Pipeline:**
    1.  **Fetch:** Get raw code for the pending row.
    2.  **Analyze (The Prompt):**
        * *Goal:* "Summarize Business Intent (not syntax)."
        * *Vocabulary:* "Extract Ubiquitous Language."
        * *Infra:* "Detect dependencies (MassTransit, SQL, Redis)."
    3.  **Embed:** Generate vector embedding for the *summary* (not the raw code).
    4.  **Update:** Write JSON + Vector back to PostgreSQL.

### 5. Component 3: The Consumption Layer (MCP API)
* **Tool 1: `search_code(query, service_filter=None)` (The Hybrid Search)**
    * **Path A (Exact):** SQL `LIKE` query on `symbol_name` (Priority).
    * **Path B (Semantic):** Cosine similarity search on `embedding` column.
    * **Path C (Infra):** JSONB search on `ai_enrichment -> 'infra_deps'`.
    * *Result:* Merged list of highly relevant entry points.
* **Tool 2: `get_dependencies(symbol_name)`**
    * Query `code_relations` to show Upstream (who calls me) and Downstream (who I call) links.
* **Tool 3: `read_source(path, line_start, line_end)`**
    * Returns raw source code for grounding.
* **Tool 4: `get_system_map()`**
    * Returns the content of `SYSTEM_CONTEXT.md` (see below).

### 6. Component 4: The System Context Generator (The "Satellite View")
* **Purpose:** Solves the "Cold Start" problem where the AI doesn't know what services exist.
* **Mechanism:** A scheduled job (or on-change hook).
* **Output:** Generates a root file `SYSTEM_CONTEXT.md`.
* **Content Format:**
    * **Services List:** Grouped by `service_name`.
    * **Stats:** "Contains 5 Controllers, 20 Domain Entities."
    * **Key Flows:** (Derived from frequent relations).
* **Usage:** This file is injected into the Agent's "Read-only Context" or available via `get_system_map()`.

---

## Part III: Deployment & Orchestration

### 1. Docker Compose Architecture
The system runs via `docker-compose.yml`, connecting to an external Ollama service.

### 2. Service Definitions
*   **axon-db**:
    *   **Image**: `pgvector/pgvector:pg16`
    *   **Purpose**: Stores `code_index` (text + vectors) and `code_relations`.
    *   **Persistence**: Volume mapped to host data folder.

*   **axon-worker** (The Background Mind):
    *   **Image**: `axon-python-worker:latest` (Custom Build)
    *   **Purpose**: Runs the "120B Loop" (Python).
    *   **Configuration**:
        *   `OLLAMA_BASE_URL`: "http://host.docker.internal:11434" (Access host's Ollama)
    *   **Dependencies**: Connects to `axon-db`.
    *   **Volume Strategy**:
        *   **Bind Mount**: `- ./:/app/source:ro` (Must match path seen by Indexer).

*   **axon-server** (The Brain & API):
    *   **Image**: `axon-mcp-server:latest` (Custom Build)
    *   **Components**: Hosted MCP Server (C#), Roslyn Indexer, System Context Generator.
    *   **Access**: Exposes MCP Protocol (SSE/Stdio) to the Agent.
    *   **Volume Strategy**:
        *   **Bind Mount**: `- ./:/app/source:ro` (Read-only access to the Host's Source Code).
        *   *Why*: The Indexer needs to scan files (`*.cs`, `Dockerfile`) on the Host.

### 3. Volume Strategy Detail
To ensure paths match between the Host (where the User works) and the Container (where Axon analyzes), we use a consistent Bind Mount strategy.
*   **Host Path**: The root of the repository (e.g., `E:\Health\Axon.MCP.Server`).
*   **Container Path**: `/app/source`.
*   **Path Mapping**: The Indexer stores `file_path` as relative paths (e.g., `src/Order.API/Startup.cs`) to avoid "E:/" vs "/app/" anomalies.

### 4. External Dependencies
*   **Ollama Service**:
    *   **Requirement**: Must be running on the host or accessible network location.
    *   **URL**: Configured via `OLLAMA_BASE_URL` env var.
    *   **Model**: 120B parameter model (or configured equivalent) must be pulled and ready.

---

## Part IV: Implementation Roadmap (Phased Rollout)
* **Phase 1: The Skeleton (Days 1-5)**
    * Setup `docker-compose` with `axon-db` (pgvector).
    * Build Roslyn Indexer with Hashing + **Config Scanning**.
    * Implement basic `search_code` (SQL only).
* **Phase 2: The Brain (Days 6-10)**
    * Deploy `axon-worker` and connect to External Ollama.
    * Enable Embedding generation (Infrastructure + Semantic).
* **Phase 3: The Full Experience (Days 11-14)**
    * Update MCP `search_code` to use Vectors.
    * Implement `code_relations` extraction in Roslyn.
    * Deploy `SYSTEM_CONTEXT.md` generator.
