# Data Models

## 📋 Overview

Axon.MCP.Server uses a **relational database (PostgreSQL 15)** with the **pgvector extension** for storing code structure, metadata, relationships, and vector embeddings. The schema supports **14 core entities** with optimized indexes, cascading deletes, and unique constraints for data integrity.

**Total Tables**: 14  
**Total Indexes**: 45+  
**Database Size**: ~500MB per 10,000 files  
**Vector Dimensions**: 768 (local) or 1536 (OpenAI)

---

## 🗂️ Entity Relationship Diagram

```mermaid
erDiagram
    Repository ||--|{ File : contains
    Repository ||--|{ Solution : has
    Repository ||--|{ Project : has
    Repository ||--|{ Service : has
    Repository ||--|{ Commit : has
    Repository ||--|{ EfEntity : has
    
    Commit ||--|{ File : modifies
    Commit ||--|{ Symbol : modifies
    
    Solution ||--|{ Project : contains
    
    File ||--|{ Symbol : defines
    File ||--|{ Chunk : chunked_into
    
    Symbol ||--o{ Symbol : parent_of
    Symbol ||--|{ Relation : from
    Symbol ||--o{ Relation : to
    Symbol ||--o{ Embedding : has_embedding
    
    Service ||--|{ Symbol : contains
    
    EfEntity ||--o| Symbol : mapped_to
    
    Chunk ||--|{ Embedding : has_embedding
```

---

## 📊 Core Entities

### 1. Repository (`repositories`)

**Purpose**: Represents a source code repository from GitLab, Azure DevOps, or GitHub.

**Schema**:
```python
class Repository(Base):
    id: int                          # Primary key
    provider: SourceControlProviderEnum  # gitlab, azure_devops, github, local
    name: str                        # Repository name
    path_with_namespace: str         # Unique path (e.g., "axon/devops/mcp-server")
    url: str                         # Web URL
    clone_url: str                   # Git clone URL
    default_branch: str              # Main/master
    status: RepositoryStatusEnum     # pending, syncing, completed, failed
    last_synced_at: datetime         # Last successful sync
    last_commit_sha: str             # HEAD commit SHA
    total_files: int                 # File count
    total_symbols: int               # Symbol count
    
    # GitLab specific
    gitlab_project_id: int
    
    # Azure DevOps specific
    azuredevops_project_name: str
    azuredevops_repo_id: str
```

**Relationships**:
- Has many: `files`, `solutions`, `projects`, `services`, `commits`, `ef_entities`

**Indexes**:
- `idx_repo_provider_path` - Fast lookups by provider + path
- `idx_repo_status` - Filter by sync status
- `idx_repo_last_synced` - Sort by last sync time

**Use Cases**:
- List all repositories for a project: `SELECT * FROM repositories WHERE provider = 'gitlab'`
- Find failed syncs: `SELECT * FROM repositories WHERE status = 'failed'`

---

### 2. File (`files`)

**Purpose**: A source code file within a repository.

**Schema**:
```python
class File(Base):
    id: int                          # Primary key
    repository_id: int               # FK to repositories
    commit_id: int                   # FK to commits (optional)
    path: str                        # Relative path (e.g., "src/api/main.py")
    language: LanguageEnum           # csharp, python, javascript, typescript
    content_hash: str                # SHA256 of content (for change detection)
    size_bytes: int                  # File size
    line_count: int                  # Total lines
    last_modified: datetime          # Git last modified time
```

**Relationships**:
- Belongs to: `repository`, `commit`
- Has many: `symbols`, `chunks`

**Indexes**:
- `idx_file_repo_path` - Unique: `(repository_id, path)`
- `idx_file_language_repo` - Filter by language
- `idx_file_hash` - Detect duplicate files

**Change Detection**:
```python
# Only re-process if content changed
existing_hash = db.query(File.content_hash).filter_by(path="main.py").first()
new_hash = hashlib.sha256(content.encode()).hexdigest()
if existing_hash != new_hash:
    # Re-parse file
```

---

### 3. Symbol (`symbols`)

**Purpose**: A code entity (class, function, method, variable, interface, etc.).

**Schema**:
```python
class Symbol(Base):
    id: int                          # Primary key
    file_id: int                     # FK to files
    repository_id: int               # FK to repositories (denormalized for speed)
    service_id: int                  # FK to services (optional)
    commit_id: int                   # FK to commits (optional)
    parent_symbol_id: int            # FK to self (for nested symbols)
    
    name: str                        # Simple name (e.g., "UserService")
    fully_qualified_name: str        # Full namespace
    kind: SymbolKindEnum             # class, function, method, variable, etc.
    language: LanguageEnum           # csharp, python, javascript
    access_modifier: AccessModifierEnum  # public, private, protected, internal
    
    signature: str                   # Function signature
    docstring: str                   # Documentation/comments
    complexity_score: int            # Cyclomatic complexity
    
    start_line: int                  # Location in file
    end_line: int
    
    attributes: JSON                 # Decorators, attributes, annotations
    ai_enrichment: JSON              # LLM-generated summary
    
    created_at: datetime
    updated_at: datetime
```

**Relationships**:
- Belongs to: `file`, `repository`, `service`, `commit`, `parent_symbol`
- Has many: `relations_from`, `relations_to`, `children`

**Indexes**:
- `idx_symbol_name_kind` - Search by name + kind
- `idx_symbol_fqn` - Unique lookup by fully qualified name
- `idx_symbol_repo_kind` - Filter symbols by repository + type
- `idx_symbol_complexity` - Sort by complexity

**AI Enrichment Example**:
```json
{
  "summary": "Handles user authentication and JWT token generation",
  "purpose": "Validates credentials and creates secure sessions",
  "related_concepts": ["Authentication", "Security", "Session Management"]
}
```

---

### 4. Relation (`relations`)

**Purpose**: Relationship between two symbols.

**Schema**:
```python
class Relation(Base):
    id: int                          # Primary key
    from_symbol_id: int              # FK to symbols
    to_symbol_id: int                # FK to symbols
    relation_type: RelationTypeEnum  # calls, inherits, implements, uses, imports, contains
    metadata: JSON                   # Line numbers, context
```

**Relation Types**:
- `inherits`: Class inheritance (A inherits B)
- `implements`: Interface implementation (A implements IB)
- `calls`: Function call (A calls B)
- `references`: Variable/type reference
- `contains`: Containment (class contains method)
- `uses`: Dependency usage
- `imports`: Module import

**Indexes**:
- `idx_relation_from_type` - Find all outgoing relations
- `idx_relation_to_type` - Find all incoming relations

**Use Cases**:
```sql
-- Who calls UserService.CreateUser?
SELECT s.name, s.fully_qualified_name
FROM symbols s
JOIN relations r ON r.from_symbol_id = s.id
WHERE r.to_symbol_id = (SELECT id FROM symbols WHERE fully_qualified_name = 'UserService.CreateUser')
  AND r.relation_type = 'calls';

-- What does UserController.Login call?
SELECT s.name, s.signature
FROM symbols s
JOIN relations r ON r.to_symbol_id = s.id
WHERE r.from_symbol_id = (SELECT id FROM symbols WHERE fully_qualified_name = 'UserController.Login')
  AND r.relation_type = 'calls';
```

---

### 5. Service (`services`)

**Purpose**: A detected service or bounded context (API, Worker, Library).

**Schema**:
```python
class Service(Base):
    id: int                          # Primary key
    repository_id: int               # FK to repositories
    name: str                        # Service name (e.g., "UserAPI")
    type: str                        # api, worker, library, test
    entry_point: str                 # Main file path
    framework: str                   # ASP.NET Core, FastAPI, Celery, etc.
    metadata: JSON                   # Routes, dependencies, config
```

**Metadata Example (API Service)**:
```json
{
  "framework": "ASP.NET Core",
  "base_route": "/api/v1",
  "controllers": ["UserController", "AuthController"],
  "endpoints_count": 12,
  "dependencies": ["Entity Framework", "JWT", "Redis"]
}
```

**Use Cases**:
- List all APIs: `SELECT * FROM services WHERE type = 'api'`
- Find service for symbol: `SELECT s.* FROM services s JOIN symbols sy ON sy.service_id = s.id WHERE sy.id = ?`

---

### 6. EfEntity (`ef_entities`)

**Purpose**: Entity Framework Core entity mapping.

**Schema**:
```python
class EfEntity(Base):
    id: int                          # Primary key
    repository_id: int               # FK to repositories
    symbol_id: int                   # FK to symbols (class symbol)
    entity_name: str                 # Entity class name
    table_name: str                  # Database table name
    schema: str                      # Database schema (e.g., "dbo")
    properties: JSON                 # List of properties with types
    relationships: JSON              # FK and navigation properties
```

**Properties Example**:
```json
[
  {"name": "Id", "type": "int", "is_key": true},
  {"name": "Email", "type": "string", "max_length": 255, "is_unique": true},
  {"name": "PasswordHash", "type": "string"},
  {"name": "CreatedAt", "type": "datetime"}
]
```

**Relationships Example**:
```json
[
  {
    "property": "Orders",
    "type": "one-to-many",
    "target_entity": "Order",
    "foreign_key": "UserId"
  }
]
```

**Unique Constraint**: `uq_ef_entity_repo_name` - One entity per name per repository

**Use Cases**:
- Map class to table: `SELECT table_name FROM ef_entities WHERE entity_name = 'User'`
- Find all entities for a project: `SELECT * FROM ef_entities WHERE repository_id = ?`

---

### 7. Chunk (`chunks`)

**Purpose**: Text chunk for embedding generation (RAG).

**Schema**:
```python
class Chunk(Base):
    id: int                          # Primary key
    file_id: int                     # FK to files
    symbol_id: int                   # FK to symbols (optional)
    content: str                     # Code snippet
    start_line: int                  # Location in file
    end_line: int
    chunk_type: str                  # function, class, module, docstring
    token_count: int                 # Estimated tokens for LLM
```

**Chunking Strategy**:
- **Function chunks**: Entire function body (avg 50-200 tokens)
- **Class chunks**: Class definition + methods (avg 200-500 tokens)
- **Module chunks**: File overview (first 100 lines or docstring)

**Use Cases**:
- Get chunks for a file: `SELECT * FROM chunks WHERE file_id = ?`
- Find chunks by symbol: `SELECT * FROM chunks WHERE symbol_id = ?`

---

### 8. Embedding (`embeddings`)

**Purpose**: Vector representation for semantic search.

**Schema**:
```python
class Embedding(Base):
    id: int                          # Primary key
    chunk_id: int                    # FK to chunks
    symbol_id: int                   # FK to symbols (optional)
    vector: pgvector                 # Vector data (768 or 1536 dimensions)
    model: str                       # Model name (e.g., "all-mpnet-base-v2")
    created_at: datetime
```

**Vector Search (pgvector)**:
```sql
-- Find similar code chunks
SELECT c.content, e.vector <=> ?::vector AS distance
FROM embeddings e
JOIN chunks c ON c.id = e.chunk_id
ORDER BY distance
LIMIT 10;
```

**Indexes**:
- `idx_embedding_vector` - HNSW index for fast cosine similarity

**Storage**:
- 768 dims: ~3KB per embedding
- 1536 dims: ~6KB per embedding

---

### 9. Solution (`solutions`)

**Purpose**: Visual Studio solution (.sln file).

**Schema**:
```python
class Solution(Base):
    id: int                          # Primary key
    repository_id: int               # FK to repositories
    name: str                        # Solution name
    path: str                        # Relative path to .sln
    version: str                     # Visual Studio version
```

**Relationships**:
- Belongs to: `repository`
- Has many: `projects`

---

### 10. Project (`projects`)

**Purpose**: Project from .sln or .csproj.

**Schema**:
```python
class Project(Base):
    id: int                          # Primary key
    repository_id: int               # FK to repositories
    solution_id: int                 # FK to solutions (optional)
    name: str                        # Project name
    path: str                        # Relative path to .csproj
    project_guid: str                # GUID from solution
    project_type: str                # Library, Executable, Test, Web
    target_framework: str            # net8.0, net6.0, etc.
```

**Use Cases**:
- List all projects in a solution: `SELECT * FROM projects WHERE solution_id = ?`
- Find executable projects: `SELECT * FROM projects WHERE project_type = 'Executable'`

---

### 11. Commit (`commits`)

**Purpose**: Git commit information.

**Schema**:
```python
class Commit(Base):
    id: int                          # Primary key
    repository_id: int               # FK to repositories
    sha: str                         # Commit SHA (unique)
    message: str                     # Commit message
    author_name: str                 # Author name
    author_email: str                # Author email
    committed_date: datetime         # Commit timestamp
    parent_sha: str                  # Parent commit (optional)
```

**Use Cases**:
- Get commit history: `SELECT * FROM commits WHERE repository_id = ? ORDER BY committed_date DESC`
- Find who last modified a file: `SELECT c.* FROM commits c JOIN files f ON f.commit_id = c.id WHERE f.path = ?`

---

## 📈 Data Model Statistics

### Typical Sizes (10K files codebase)

| Entity | Count | Avg Size | Total |
|--------|-------|----------|-------|
| Repositories | 1 | 1KB | 1KB |
| Files | 10,000 | 2KB | 20MB |
| Symbols | 100,000 | 1KB | 100MB |
| Relations | 200,000 | 200B | 40MB |
| Chunks | 50,000 | 500B | 25MB |
| Embeddings | 50,000 | 6KB | 300MB |
| **Total** | - | - | **~500MB** |

---

## 🔍 Indexing Strategy

### Performance-Critical Indexes

1. **Symbol Lookup**:
   - `idx_symbol_fqn` (UNIQUE) - Exact symbol lookup (O(log n))
   - `idx_symbol_name_kind` - Fuzzy name search
   - `idx_symbol_repo_kind` - Filter by repository + type

2. **Relation Queries**:
   - `idx_relation_from_type` - Forward traversal (calls, uses)
   - `idx_relation_to_type` - Backward traversal (callers, dependencies)
   - Composite index for bidirectional queries

3. **Vector Search**:
   - `idx_embedding_vector` - HNSW index (pgvector)
   - Parameters: `m=16, ef_construction=64` (balanced speed/accuracy)

4. **File Operations**:
   - `idx_file_repo_path` (UNIQUE) - Fast file lookup
   - `idx_file_hash` - Change detection

---

## 🔐 Data Integrity

### Cascading Deletes

```python
# When a repository is deleted, all related data is automatically cleaned up
Repository
  ├── Files (CASCADE)
  │   ├── Symbols (CASCADE)
  │   │   └── Relations (CASCADE)
  │   └── Chunks (CASCADE)
  │       └── Embeddings (CASCADE)
  ├── Solutions (CASCADE)
  │   └── Projects (CASCADE)
  ├── Services (CASCADE)
  └── EfEntities (CASCADE)
```

### Unique Constraints

- `uq_repository_provider_path` - No duplicate repositories
- `uq_file_repo_path` - No duplicate files per repository
- `uq_symbol_fqn_repo` - No duplicate symbols (by FQN) per repository
- `uq_ef_entity_repo_name` - One EF entity per name per repository

---

## 🎯 Query Examples

### 1. Find All API Controllers

```sql
SELECT s.name, s.fully_qualified_name, f.path
FROM symbols s
JOIN files f ON f.id = s.file_id
WHERE s.kind = 'class'
  AND s.name LIKE '%Controller'
  AND s.repository_id = ?;
```

### 2. Build Call Graph (BFS)

```python
def get_call_graph(symbol_id, max_depth=3):
    """Get all functions called by symbol_id up to max_depth levels."""
    visited = set()
    queue = [(symbol_id, 0)]
    result = []
    
    while queue:
        current_id, depth = queue.pop(0)
        if current_id in visited or depth > max_depth:
            continue
            
        visited.add(current_id)
        
        # Get all relations of type 'calls'
        relations = db.query(Relation).filter_by(
            from_symbol_id=current_id,
            relation_type='calls'
        ).all()
        
        for rel in relations:
            result.append((current_id, rel.to_symbol_id, depth))
            queue.append((rel.to_symbol_id, depth + 1))
    
    return result
```

### 3. Semantic Search

```python
def semantic_search(query: str, limit: int = 10):
    """Search code using vector similarity."""
    # Generate query embedding
    query_vector = embedding_model.encode(query)
    
    # Vector search
    results = db.execute("""
        SELECT c.content, s.fully_qualified_name, f.path,
               e.vector <=> :query_vector AS distance
        FROM embeddings e
        JOIN chunks c ON c.id = e.chunk_id
        JOIN symbols s ON s.id = c.symbol_id
        JOIN files f ON f.id = c.file_id
        ORDER BY distance
        LIMIT :limit
    """, {"query_vector": query_vector, "limit": limit})
    
    return results
```

### 4. Find Entity Framework Entities for a Table

```sql
SELECT ef.entity_name, s.file_id, f.path
FROM ef_entities ef
JOIN symbols s ON s.id = ef.symbol_id
JOIN files f ON f.id = s.file_id
WHERE ef.table_name = 'Users';
```

---

## 🔮 Future Enhancements

### Planned Schema Changes

1. **Conversation Table** (for RAG):
   ```python
   class Conversation(Base):
       id: int
       user_id: int
       title: str
       messages: List[ConversationMessage]
   ```

2. **Architecture Snapshot Table**:
   ```python
   class ArchitectureSnapshot(Base):
       id: int
       repository_id: int
       diagram_type: str  # service_map, layer_diagram
       mermaid_code: str
       created_at: datetime
   ```

3. **Dependency Graph Table**:
   ```python
   class Dependency(Base):
       id: int
       from_project_id: int
       to_project_id: int
       dependency_type: str  # nuget, npm, internal
   ```

---

## 📖 Additional Resources

- [Architecture Overview](overview.md) - System architecture
- [Infrastructure](infrastructure.md) - Deployment details
- [API Reference](../api/rest_api.md) - REST endpoints
