<div align="center">

<!-- Banner Placeholder - Replace with actual logo/banner image -->
<img src="assets/axon-mcp-banner.png" alt="Axon MCP Server Banner" width="800"/>

# Axon.MCP.Server

**Model Context Protocol (MCP) Server for AI IDEs - Cursor, AntiGravity & Claude**

*Transform your codebase into an intelligent knowledge base for AI-powered development with Cursor IDE, Google AntiGravity, and MCP-enabled assistants*

---

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Commercial License](https://img.shields.io/badge/License-Commercial_Available-purple.svg)](#-license--commercial-use)
[![Build Status](https://github.com/ali-kamali/Axon.MCP.Server/actions/workflows/ci.yml/badge.svg?branch=public-release)](https://github.com/ali-kamali/Axon.MCP.Server/actions/workflows/ci.yml)
[![Docker Image](https://img.shields.io/badge/docker-GHCR-blue.svg)](https://github.com/ali-kamali/Axon.MCP.Server/pkgs/container/axon-mcp-server)
[![Coverage](https://img.shields.io/badge/coverage-85%25-yellowgreen.svg)]()
[![MCP Protocol](https://img.shields.io/badge/MCP-v1.0-purple.svg)](https://modelcontextprotocol.io)
[![Documentation](https://img.shields.io/badge/docs-latest-blue.svg)](https://ali-kamali.github.io/Axon.MCP.Server/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

</div>

---

## 📋 Table of Contents

- [The Problem](#-the-problem)
- [The Solution](#-the-solution)
- [See It In Action](#-see-it-in-action)
- [Architecture Overview](#️-architecture-overview)
- [MCP Tools for AI Assistants](#-mcp-tools-for-ai-assistants)
- [Key Features](#-key-features)
- [Quick Start](#-quick-start)
- [Use Cases](#-use-cases)
- [Documentation](#-documentation)
- [Development](#-development)
- [Roadmap](#️-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

---


## 🎯 The Problem

Modern codebases are complex labyrinths—thousands of files, intricate dependencies, and evolving architectures. **AI assistants like ChatGPT and Claude are brilliant... but they're flying blind.** Without deep understanding of your codebase's structure, relationships, and patterns, they can only see the trees, never the forest.

## 💡 The Solution

**Axon.MCP.Server** transforms your entire codebase into an intelligent, queryable knowledge base using the **Model Context Protocol (MCP)**. Think of it as giving your AI assistant X-ray vision into your code—understanding not just syntax, but semantics, architecture, and relationships.

### Why Axon Stands Out

- **🧠 Semantic Understanding**: Goes beyond grep to understand what code *means*, not just what it says
- **🔗 Relationship Mapping**: Automatically builds call graphs, inheritance trees, and dependency networks
- **🤖 AI-Native Integration**: Built specifically for ChatGPT, Claude, Cursor IDE, and other MCP-enabled tools
- **📊 Multi-Language Mastery**: Deep analysis for C# (Roslyn), Python, JavaScript, TypeScript
- **🔍 Vector-Powered Search**: Find code by meaning using semantic embeddings
- **🏗️ Architecture Intelligence**: Auto-detects services, APIs, Entity Framework mappings, design patterns
- **⚡ Production-Ready Performance**: <500ms p95 latency, handles 10,000+ files with ease
- **🔐 Enterprise Security**: JWT auth, RBAC, audit logging, rate limiting—not a toy project

---

## � See It In Action

<div align="center">

### 🤖 AI IDE Integration - The Main Use Case

**Axon MCP Server seamlessly integrates with leading AI-powered IDEs to supercharge your development workflow**

#### Google AntiGravity - Best AI IDE for Vibe Coders
![AntiGravity Integration](assets/screenshots/AntiGravity.png)
*Axon MCP providing deep code context to Google AntiGravity for intelligent code assistance*

#### Cursor IDE - AI-First Code Editor
![Cursor Integration](assets/screenshots/Cursor.png)
*Real-time code intelligence powered by Axon's semantic understanding in Cursor*

---


### 🏛️ Management Dashboard
![Axon Dashboard](assets/screenshots/dashboard.png)
*Real-time monitoring of code analysis and synchronization*

### 🛠️ Architecture Visualization
![Architecture Map](assets/architecture-diagram.jpg)
*Auto-generated service dependency diagrams*



</div>

---

## 🏗️ Architecture Overview

### 10-Service Microarchitecture

```
┌─────────────────────────────────────────────────────────────┐
│  Client Layer: AI Assistants, IDEs, React UI, REST Clients  │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
┌───────────▼────┐  ┌──────▼──────┐  ┌────▼──────┐
│  MCP Server    │  │  REST API   │  │  React UI │
│    :8001       │  │    :8080    │  │    :80    │
└───────┬────────┘  └──────┬──────┘  └───────────┘
        │                  │
        │         ┌────────┼────────┐
        │         │        │        │
        │    ┌────▼───┐ ┌─▼────┐ ┌─▼─────────┐
        │    │ Worker │ │ Beat │ │ Enrichment│
        │    │ (Sync) │ │ Sched│ │  Worker   │
        │    └────┬───┘ └──────┘ └─────┬─────┘
        │         │                     │
    ┌───▼─────────▼─────────────────────▼──────┐
    │  Analysis: Tree-sitter + Roslyn + EF     │
    └───────────────────┬──────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼──────┐  ┌────▼────┐  ┌──────▼────────┐
│ PostgreSQL   │  │  Redis  │  │ Prometheus +  │
│ + pgvector   │  │ Cache   │  │   Grafana     │
└──────────────┘  └─────────┘  └───────────────┘
```

### Technology Stack

**Backend**: FastAPI, Celery, SQLAlchemy 2.0 (async), Python 3.11+  
**Parsing**: Tree-sitter (multi-lang), Roslyn (C# semantic analysis)  
**Database**: PostgreSQL 15 + pgvector, Redis  
**AI/ML**: OpenAI/OpenRouter (LLM), sentence-transformers (embeddings)  
**Frontend**: React + TypeScript, Vite  
**Infrastructure**: Docker Compose, Prometheus, Grafana  

---

## 🔌 MCP Tools for AI Assistants

The server exposes **12 powerful tools** to AI assistants via the Model Context Protocol:

| Tool | Description | Use Case |
|------|-------------|----------|
| `search` | Semantic + full-text code search | "Find all authentication controllers" |
| `get_call_graph` | Function call relationships | "Who calls UserService.CreateUser?" |
| `get_inheritance_hierarchy` | Class inheritance tree | "Show me all BaseController implementations" |
| `get_api_endpoints` | List REST API routes | "What endpoints modify the User table?" |
| `get_ef_entities` | Entity Framework mappings | "Show database schema for Orders" |
| `get_module_summary` | AI-generated code summaries | "Explain what PaymentService does" |
| `explore_service` | Navigate service architecture | "Show me the API service structure" |
| `find_implementations` | Interface implementations | "Find all IRepository implementations" |
| `get_system_architecture_map` | Generate architecture diagrams | "Visualize system dependencies" |
| `get_symbol_details` | Detailed symbol info | "Show UserController.Login signature" |
| `get_file_symbols` | List symbols in a file | "What's in AuthService.cs?" |
| `get_repository_structure` | Project/solution organization | "Show .NET solution structure" |

---

## ✨ Key Features

### 🔬 1. Hybrid Python/C# Analysis Engine
- **Tree-sitter**: Lightning-fast syntactic parsing for Python, JavaScript, TypeScript, and C#
- **Roslyn Subprocess**: Compiler-grade semantic analysis for C# (type resolution, cross-file references, metadata)
- **EF Core Analyzer**: Extracts Entity Framework entities, table mappings, and relationships automatically

### 🗂️ 2. Intelligent Code Indexing
- 🔄 Automatically discovers repositories from GitLab/Azure DevOps
- 🏷️ Extracts symbols (classes, functions, variables) with rich metadata (docstrings, parameters, return types)
- 📞 Builds call graphs, inheritance hierarchies, and import dependency maps
- 🏗️ Detects services, APIs, workers, and libraries with auto-classification
- 🧮 Generates vector embeddings for semantic search powered by pgvector

### 🤖 3. AI-Powered Enrichment
- 📝 LLM-generated summaries for symbols and modules (using OpenRouter/OpenAI)
- ⚡ Parallel processing with 8-worker Celery pipeline for blazing speed
- 💾 Smart caching to avoid re-generation and reduce API costs

### 📊 4. Production-Grade Observability
- 📈 Pre-configured Prometheus metrics (API latency, sync status, search performance, cache hit rates)
- 📉 Beautiful Grafana dashboards for real-time monitoring
- 📄 Structured JSON logging with `structlog` for easy parsing
- 📡 Real-time sync progress via Redis Pub/Sub for responsive UI updates

### 🔐 5. Enterprise Security
- 🔑 JWT authentication + API keys for flexible auth strategies
- 👥 Role-based access control (admin, readonly) for granular permissions
- 🍪 HTTP-only cookies with CSRF protection
- ⏱️ Rate limiting and comprehensive audit logging

---

## 📊 Data Model Highlights

The system maintains a rich relational model:

- **Repositories**: Source control repos (GitLab/Azure DevOps)
- **Files**: Source code files with content hashes
- **Symbols**: Functions, classes, variables with AI enrichment
- **Relations**: Inherits, implements, calls, references, imports
- **Services**: Detected APIs, workers, libraries
- **EfEntities**: Entity Framework → database table mappings
- **Embeddings**: pgvector embeddings for semantic search
- **Chunks**: Code chunks (function/class level) for RAG

**Total Tables**: 14 with optimized indexes, cascading deletes, unique constraints

---

## 🚀 Quick Start

Get up and running in **5 minutes** with Docker Compose.

### Prerequisites

- 🐳 Docker & Docker Compose installed
- 🐍 Python 3.11+ (for local development)
- 🔑 GitLab or Azure DevOps access token

### Step 1: Clone & Configure

```bash
# Clone the repository
git clone https://github.com/ali-kamali/Axon.MCP.Server.git
cd axon.mcp.server

# Copy environment template
cp .env.example .env
```

**Edit `.env` with your credentials:**

```bash
# Source control (choose one)
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
# OR
AZUREDEVOPS_PASSWORD=your-azure-devops-pat

# Security (generate strong keys)
ADMIN_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
ADMIN_PASSWORD=your-secure-password

# Optional: AI enrichment (for LLM-generated code summaries)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
```

### Step 2: Launch Services

```bash

# Start all services (PostgreSQL, Redis, API, Workers, UI, Monitoring)
make docker-up

# Run database migrations
make migrate

# Verify health
curl http://localhost:8080/api/v1/health
# ✅ Expected: {"status":"ok"}
```

### Step 3: Access Your Platform

| 🎯 Service | 🌐 URL | 🔐 Credentials |
|------------|--------|----------------|
| **React Dashboard** | [http://localhost:80](http://localhost:80) | Login with `ADMIN_PASSWORD` |
| **REST API Docs** | [http://localhost:8080/api/docs](http://localhost:8080/api/docs) | `X-API-Key: ADMIN_API_KEY` |
| **MCP Server** | `http://localhost:8001` | For AI assistants (see [MCP Tools](docs/api/mcp_tools.md)) |
| **Grafana** | [http://localhost:3000](http://localhost:3000) | `admin / admin` |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | No auth |

### 🎉 You're Ready!

**Next Steps:**
1. 📊 View the React Dashboard and add your first repository
2. 🔍 Try a semantic search: "Find all authentication controllers"
3. 🤖 Connect an AI assistant using the MCP server
4. 📈 Monitor performance in Grafana dashboards

> **💡 Pro Tip:** Check out the [Development Guide](docs/guides/development.md) for local development setup and testing.

---

## 🎯 Use Cases

### 🚀 Primary: AI IDE Integration (Cursor, AntiGravity, VS Code)

**The main purpose of Axon MCP Server is to provide deep code intelligence to AI-powered IDEs:**
#### Cursor IDE
1. **Contextual Code Completion**: AI understands your entire codebase structure
2. **Intelligent Chat**: Ask questions about architecture, dependencies, and implementation details
3. **Semantic Code Search**: Find code by what it does, not just what it's called
4. **Refactoring Assistance**: AI knows all usages across your entire codebase

#### Google AntiGravity
1. **Vibe Coding Intelligence**: Deep understanding of code patterns and architecture
2. **Cross-Repository Context**: Work with multiple projects seamlessly
3. **Smart Code Generation**: AI suggestions based on your actual codebase patterns
4. **Real-Time Documentation**: Instant explanations of complex code sections

#### Other MCP-Enabled Tools
- **Claude Desktop**: Ask natural language questions about your codebase
- **ChatGPT with MCP**: Deep code analysis and architectural insights
- **Custom MCP Clients**: Build your own AI-powered dev tools

### 📊 For Development Teams
1. **Onboarding**: New developers can ask "How does authentication work?" and get comprehensive answers
2. **Code Review**: AI-assisted review with full context of dependencies and impacts
3. **Documentation**: Auto-generated explanations for complex modules
4. **Impact Analysis**: "What breaks if I change this API?" with complete dependency traces

### 🔍 For Software Architects
1. **Architecture Visualization**: Auto-generated service dependency diagrams
2. **Design Pattern Detection**: Identify patterns and anti-patterns across the codebase
3. **Technical Debt Analysis**: Find complex, tightly-coupled code sections
4. **Migration Planning**: Understand all dependencies before major refactors

---

## 📚 Documentation

### 🏗 Architecture
- [Overview](https://ali-kamali.github.io/Axon.MCP.Server/architecture/overview/) - System architecture and core components
- [Data Models](https://ali-kamali.github.io/Axon.MCP.Server/architecture/data_models/) - Database schema and relationships
- [Infrastructure](https://ali-kamali.github.io/Axon.MCP.Server/architecture/infrastructure/) - Deployment and scaling

### 📖 Guides
- [Setup Guide](https://ali-kamali.github.io/Axon.MCP.Server/guides/setup/) - Prerequisites and installation
- [Development Guide](https://ali-kamali.github.io/Axon.MCP.Server/guides/development/) - Dev environment setup and testing
- [Deployment Guide](https://ali-kamali.github.io/Axon.MCP.Server/guides/deployment/) - Docker and Kubernetes deployment
- [Security Guide](https://ali-kamali.github.io/Axon.MCP.Server/guides/security/) - Security features and best practices

### 🔌 API & Tools
- [REST API Reference](https://ali-kamali.github.io/Axon.MCP.Server/api/rest_api/) - API endpoints and usage
- [MCP Tools Reference](https://ali-kamali.github.io/Axon.MCP.Server/api/mcp_tools/) - MCP tools for AI assistants

### ⚙️ Reference
- [Configuration](docs/reference/configuration.md) - Environment variables
- [Troubleshooting](docs/reference/troubleshooting.md) - Common issues and solutions

---

## 🔧 Development

```bash
# Install dependencies
make dev-install

# Run tests
make test

# Start API (dev mode with hot reload)
make api-dev

# Start MCP server
make mcp-dev

# Start UI
make ui-dev

# Lint and format
make lint
make format
```

---

## 🌟 What Makes This Special?

1. **Hybrid Intelligence**: Syntactic (Tree-sitter) + Semantic (Roslyn) analysis
2. **AI-First Design**: Built specifically to feed AI assistants with code context
3. **Production-Grade**: Real auth, monitoring, distributed processing, caching
4. **Multi-Source**: Supports GitLab and Azure DevOps
5. **Deep C# Support**: Compiler-grade analysis via Roslyn
6. **Semantic Search**: Vector embeddings enable "find similar code" queries
7. **Architectural Awareness**: Detects services, APIs, entities—not just functions

---

## 🗺️ Roadmap

This project is **actively maintained** and continuously evolving. Here's what's on our horizon:

### ✅ Completed (v3.2 - Current)
- [x] **API Authentication**: JWT tokens + API keys for hybrid auth scenarios
- [x] **Hybrid Authentication**: UI login with cookies + programmatic API key access
- [x] **Memory Optimization**: Keyset pagination for efficient large dataset handling
- [x] **Vector Search**: Semantic code search powered by pgvector embeddings
- [x] **Multi-Language Support**: Python, JavaScript, TypeScript, C# (via Roslyn)

### 🚧 In Progress (v3.2 → v3.3)
- [ ] **Roslyn Process Manager Refactor**: Improved stability and resource management
- [ ] **Pipeline Pattern Refactor**: More modular and testable processing architecture

### 🎯 Next Release (v3.3 - Q1 2026)
- [ ] **RAG Pipeline**: Ask natural language questions about your codebase ("How does auth work?")
- [ ] **Architecture Visualization**: Auto-generate Mermaid/PlantUML diagrams from code structure
- [ ] **Impact Analysis Tool**: See what breaks before you change it ("What depends on UserService?")
- [ ] **Conversation Memory**: Multi-turn AI conversations with context retention

### 🚀 Future Enhancements (v4.0+)
- [ ] **AI Test Generation**: Automatically generate unit tests for your code
- [ ] **Code Review Assistant**: AI-powered PR reviews with security and quality checks
- [ ] **Complexity Heatmaps**: Visual complexity analysis to identify refactoring candidates
- [ ] **Dependency Audit**: Track and visualize package dependencies and vulnerabilities
- [ ] **Language Expansion**: Java, Go, Rust, Ruby, PHP support
- [ ] **IDE Plugins**: Native plugins for VS Code, JetBrains IDEs
- [ ] **Collaboration Features**: Team annotations, shared searches, codebase bookmarks

> **💡 Have a feature idea?** Open an issue on our GitLab repository!

---

## 📄 License & Commercial Use

**Axon.MCP.Server** is dual-licensed to ensure sustainability and rapid development.

### 1. Open Source (AGPLv3)

This project is free software under the **GNU Affero General Public License v3.0 (AGPLv3)**.

* **Best for:** Open-source projects, hobbyists, researchers, and educational use.
* **The Rule:** If you modify this code or use it in a service accessible over a network, you **must** open-source your own project under the same AGPLv3 license.
* **Details:** See the [LICENSE](LICENSE) file for complete terms.

### 2. Commercial License (Enterprise)

Want to integrate Axon into a proprietary/closed-source product?

* **Best for:** Startups, Enterprises, and SaaS products who cannot open-source their code.
* **Benefits:**
  * Release your product under your own proprietary license
  * No requirement to share your source code
  * Priority support and direct access to the maintainer
  * Legal indemnification options
  * Custom features and integrations

📩 **[Contact us](mailto:your-email@example.com)** to acquire a commercial license.

---

### Why Dual Licensing?

We believe in open source **and** sustainability. The AGPLv3 ensures the community benefits from improvements, while commercial licenses fund continued development, comprehensive testing, and enterprise features that benefit everyone.

---

## 🤝 Contributing

We welcome contributions from the community! Whether it's bug fixes, new features, or documentation improvements, your help makes this project better.

### 1. The "Reality" Check: CLA
**Since this project is dual-licensed, we must ensure we have the legal right to distribute contributions.**

Before merging any PR, we ask contributors to reply to a comment saying:
> *"I hereby assign copyright of this contribution to the project maintainers and agree to the terms of the Contributor License Agreement."*

### 2. Getting Started
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### 3. Guidelines
* 📘 [Development Guide](docs/guides/development.md) - Setup, coding standards, and best practices
* ✅ **Code Quality**: We use Black, mypy, and pylint for code quality
* 🧪 **Testing**: Maintain >80% test coverage for all new code
* 🔄 **Pull Requests**: Follow our PR template and ensure CI passes

---

## 📞 Support & Community

Need help or want to discuss features?

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/ali-kamali/Axon.MCP.Server/issues)
- 📖 **Documentation**: Browse the [`docs/`](docs/) directory
- 💬 **Community**: Join us on `#axon-mcp-server` (internal Slack)
- ❓ **Questions**: Open a discussion or issue on GitHub

---

<div align="center">

**Built with ❤️ by the Axon DevOps Team**

*Empowering developers with AI-driven code intelligence*

[![Star on GitHub](https://img.shields.io/badge/⭐-Star%20Us%20on%20GitHub-orange)](https://github.com/ali-kamali/Axon.MCP.Server)

</div>
