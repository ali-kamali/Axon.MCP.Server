# Product Vision & Goals

> **"To empower AI agents with the deep, semantic context they need to understand, navigate, and evolve complex software systems autonomously."**

## 1. The Problem
In modern software development, codebases are large, distributed (microservices), and complex. AI agents (like ChatGPT, Claude, or IDE assistants) often struggle because they:
- **Lack Context**: They only see the file currently open or a small window of code.
- **Miss the Big Picture**: They don't understand how the frontend interacts with the backend or how microservices communicate.
- **Hallucinate**: Without ground truth, they guess implementation details.

## 2. The Solution: Axon MCP Server
The Axon MCP Server acts as the **"Cortex"** for AI agents. It is a specialized Model Context Protocol (MCP) server that indexes the entire codebase, understands its structure, and provides tools for agents to query that knowledge.

It bridges the gap between **Static Code** and **AI Understanding**.

### Key Capabilities
- **Holistic Understanding**: Indexes everything—frontend (React/Vue), backend (C#/Python), databases (SQL), and infrastructure (Docker/K8s).
- **Semantic Navigation**: Allows agents to "jump to definition," "find usages," and "trace requests" across repository boundaries.
- **Architectural Awareness**: Understands that `AuthService` in the backend is called by `LoginForm` in the frontend.

## 3. Definition of Done (DoD)
We consider this project successful when an AI agent, connected to this server, can autonomously perform the following without human guidance:

1.  **Onboarding**: "Explain the architecture of this project and how the payment flow works." -> *Agent retrieves architecture docs, traces the payment endpoint, and generates a correct summary.*
2.  **Feature Implementation**: "Add a new field to the User profile." -> *Agent identifies the Database Model, the API DTOs, the Backend Service, and the Frontend Component that need changing.*
3.  **Bug Fixing**: "The login page is throwing a 500 error." -> *Agent searches logs, finds the relevant API endpoint, checks the recent commits, and identifies the breaking change.*

## 4. Strategic Pillars

### A. Universal Context
The system must support multiple languages (C#, Python, TypeScript) and platforms (GitLab, Azure DevOps) to provide a unified view of the "World".

### B. Agent-First Design
The API and Tools are designed for **Agents**, not humans.
- **Inputs**: Flexible, forgiving (fuzzy search).
- **Outputs**: Structured, concise, and token-efficient (Markdown/JSON).

### C. Zero-Config Intelligence
The system should auto-discover project structures, frameworks, and patterns without requiring extensive manual configuration.

## 5. User Stories (Examples)

- **As a Product Manager**, I want the agent to generate a feature spec based on the existing code so that I know what is currently implemented.
- **As a Developer**, I want the agent to refactor a service and automatically update all consumers in the frontend.
- **As a QA Engineer**, I want the agent to generate test cases for all edge cases in the `OrderProcessing` module.

## 6. Future Roadmap: The "Microservices Context Engine"

To achieve "whole system" awareness, we are evolving from a **Single-Repo Code Analyzer** into a **Microservices Ecosystem Context Engine**.

### Phase 1: Backend Language Expansion (Foundation)
**Goal:** Enable parsing of Node.js and other microservices.
- [ ] Implement `JavaScriptBackendParser` to detect Express.js/NestJS routes.
- [ ] Expand C# support for minimal APIs and other patterns.

### Phase 2: Communication Intelligence (Inter-Service & Client Calls)
**Goal:** Extract "Who calls what?" - Map all communication patterns across the system.

#### Frontend → Backend API Calls
- [ ] Update `JavaScriptParser` to visit AST nodes for `CallExpression`.
- [ ] Detect common HTTP clients: `fetch`, `axios`, `angular/http`, Vue `$http`.
- [ ] Extract URL strings from frontend code.

#### Backend → Backend API Calls (Microservice Communication)
- [x] Detect C# HTTP calls: `HttpClient.GetAsync()`, `HttpClient.PostAsync()`, Refit interfaces, RestSharp.
- [x] Detect C# gRPC calls: `GrpcChannel.ForAddress()`, generated gRPC clients.
- [x] Detect C# GraphQL calls: `GraphQLHttpClient`, StrawberryShake `ExecuteAsync`.
- [x] Detect C# SignalR connections: `HubConnectionBuilder.WithUrl()`, `InvokeAsync`, `On` handlers.
- [x] Detect C# WebSocket connections: `ClientWebSocket`, `ConnectAsync`.
- [ ] Detect Node.js HTTP calls: `axios`, `node-fetch`, `http.request()`, `got`, `superagent`.
- [ ] Extract service URLs and endpoints being called.
- [ ] Support custom HTTP wrapper classes (fallback to generic `HttpClient`/`fetch` pattern detection).

#### Event Publishing & Message Queue Patterns
- [ ] Detect event publishers:
  - **C#**: MassTransit (`IBus.Publish()`, `IPublishEndpoint.Publish()`), NServiceBus, Azure Service Bus, AWS SNS/SQS, RabbitMQ.Client
- [ ] Detect event subscribers/consumers (handlers, listeners).
- [ ] Extract event types, message contracts, topics, queue names, and exchange bindings.
- [ ] Store in new `OutgoingApiCall`, `PublishedEvent`, and `EventSubscription` tables.

### Phase 3: The Linker (The "Context" Layer) ✅
**Goal:** Connect the graph.
- [x] Create the `link_microservices` Celery task.
- [x] Implement fuzzy matching logic: Match Frontend `/api/users` to Backend `[Route("api/users")]`.
- [x] Update MCP tool `get_symbol_context` to return connected endpoints.
    - *Example Output:* "This React button calls `POST /api/orders`, which maps to `OrderController.CreateOrder` in the `OrderService` repo."

#### Phase 3 Implementation Details
The Linker is now fully implemented with the following components:

1. **LinkService** (`src/services/link_service.py`):
   - `parse_all_gateway_configs()`: Parses Ocelot and Nginx gateway configurations
   - `link_api_calls_to_endpoints()`: Links frontend API calls to backend endpoints
   - `link_events()`: Links event publishers to subscribers
   - `get_connected_endpoints()`: Retrieves cross-service connections for a symbol
   - Fuzzy URL matching with configurable confidence thresholds (default 70%)

2. **Celery Tasks** (`src/workers/tasks.py`):
   - `link_microservices`: Global linking task for all/selected repositories
   - `link_repository`: Single repository linking task

3. **API Endpoints** (`src/api/routes/jobs.py`):
   - `POST /jobs/link-microservices`: Trigger global linking
   - `POST /jobs/link-repository/{id}`: Trigger single repo linking

4. **MCP Tool Enhancement** (`src/mcp_server/server.py`):
   - `get_symbol_context` now includes `connected_endpoints` with:
     - Outgoing API calls and their linked backend endpoints
     - Incoming API calls from other services
     - Published events and their subscribers
     - Subscribed events and their publishers

### Phase 4: Infrastructure & Service Discovery
**Goal:** Understand the "Glue" between services (Gateways, Proxies, Orchestration).
> 📘 **[See Technical Specification](architecture/infrastructure_analysis.md)**
- [ ] **Docker Compose**: Parse `docker-compose.yml` to map service names (e.g., `http://auth-service:8080`) to repositories.
- [ ] **API Gateways**: Parse `*ocelot*.json` to understand upstream/downstream routing and aggregation.
- [ ] **Reverse Proxies**: Parse `*.conf` (Nginx) to extract routing rules and service locations.
- [ ] **Config Resolution**: Resolve environment variables and config placeholders to link services dynamically.
