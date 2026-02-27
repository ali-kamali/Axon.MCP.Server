# Axon Task List (Running Board)

**Path:** `/home/marcellus/.openclaw/workspace/repos/Axon.MCP.Server/docs/engineering/AXON_TASK_LIST.md`  
**Scope:** Ongoing implementation, hardening, and validation tasks for Axon.MCP.Server.  
**Last Updated (UTC):** 2026-02-27T05:10:02Z

## How to Use (for humans + coding agents)

1. **Single source of truth:** Use this file for active/planned/blocked Axon tasks.
2. **State transitions:** Move tasks between state sections only (don’t duplicate).
3. **Ordering rules:**
   - `INCOMPLETE`, `IN_PROGRESS`, and `BLOCKED` must stay sorted by **priority** (`P0` highest → `P3` lowest).
   - If same priority, sort by task ID.
4. **Done timestamps:** When moving a task to `DONE`, add `completed_at=<ISO-8601 UTC>`.
5. **Priority discipline:**
   - `P0` = urgent/release or correctness risk
   - `P1` = important near-term hardening
   - `P2` = medium-value improvements
   - `P3` = low urgency / cleanup
6. **Task format (required fields):**
   - `id`, `priority`, `owner`, `summary`, `next_step`
   - Optional: `blocked_reason`, `depends_on`, `links`

## Task Entry Template

- [ ] `AX-XXX` | `P#` | owner=`<agent-or-human>` | summary=`<what>` | next_step=`<immediate next action>`
  - depends_on=`<optional>`
  - links=`<optional>`

---

## IN_PROGRESS (sorted by priority)


## INCOMPLETE (sorted by priority)

- [ ] `AX-037` | `P1` | owner=`main+cron` | summary=`Retire or isolate legacy src/mcp_server/server_old.py from active runtime/test path.` | next_step=`Confirm no runtime references, move to archival location or guarded legacy module, and validate import/test behavior.`

- [ ] `AX-028` | `P2` | owner=`cron` | summary=`Reduce remaining project-controlled UTC/deprecation warning sources.` | next_step=`Continue sweeping project modules for residual datetime.utcnow() usage; auth token path now migrated to timezone-aware UTC.`

- [ ] `AX-038` | `P2` | owner=`main+cron` | summary=`Refactor oversized hotspots into smaller composable modules (parser/extractor/service layers).` | next_step=`Start with highest-maintenance modules (csharp_parser, javascript_parser, link_service, knowledge_extractor) and split by concern with regression safety nets.`

- [ ] `AX-039` | `P2` | owner=`main+cron` | summary=`Close tracked functional TODOs in critical analysis paths.` | next_step=`Implement TODOs for call-graph signature matching, sync progress Redis persistence, and chunk-context import persistence.`

- [ ] `AX-041` | `P3` | owner=`main+cron` | summary=`Create and execute staged dependency modernization plan (backend + UI).` | next_step=`Upgrade in controlled tranches with compatibility matrix and CI gate at each tranche.`


## BLOCKED (sorted by priority)

- [ ] `AX-030` | `P1` | owner=`main+cron` | summary=`Eliminate Celery internal datetime.utcnow() deprecation warnings in runtime output.` | next_step=`Track pinned Celery version and upgrade path.`
  - blocked_reason=`Warnings originate from dependency internals, not only project-owned code; full removal requires upstream/library upgrade.`

- [ ] `AX-031` | `P2` | owner=`main+cron` | summary=`Remove Starlette/python_multipart deprecation warning path fully.` | next_step=`Upgrade dependency chain and validate import path changes end-to-end.`
  - blocked_reason=`Warning originates from external dependency import path behavior.`

- [ ] `AX-032` | `P2` | owner=`main` | summary=`Automate 1Password `.env` sync for unattended agent sessions.` | next_step=`Adopt service-account/token-based auth path for non-interactive gateway execution.`
  - blocked_reason=`Current OP session auth is shell-scoped and not reliably available to service/cron process context.`

## DONE (sorted by completion date, newest first)

- [x] `AX-025` | `P0` | owner=`main` | summary=`Curate, commit, and push the current stabilization working tree safely in logical commits.` | completed_at=`2026-02-27T05:10:02Z`
  - links=`docs/engineering/STAGED_COMMIT_PLAN_2026-02-27.md`

- [x] `AX-044` | `P2` | owner=`cron` | summary=`Harden React router tests for v7 forward-compatibility by opting into future flags and removing noisy warnings.` | completed_at=`2026-02-27T05:08:17Z`
  - links=`ui/src/App.test.tsx`

- [x] `AX-035` | `P0` | owner=`cron` | summary=`Raise coverage in high-risk low-coverage API routes and worker pipeline modules.` | completed_at=`2026-02-27T04:41:19Z`
  - links=`tests/unit/test_incremental_sync.py, tests/unit/test_pipeline_context_step.py, src/workers/incremental_sync.py, src/workers/pipeline/context.py, src/workers/pipeline/step.py`

- [x] `AX-043` | `P1` | owner=`cron` | summary=`Expand Python symbol end-to-end verification through ingestion and query surfaces.` | completed_at=`2026-02-27T04:39:02Z`
  - links=`tests/unit/test_symbols_routes.py, tests/unit/test_mcp_routes.py, src/api/routes/symbols.py, src/api/routes/mcp_test.py`

- [x] `AX-040` | `P2` | owner=`cron` | summary=`Implement React route-level code splitting to improve initial load performance.` | completed_at=`2026-02-27T04:39:02Z`
  - links=`ui/src/App.tsx, ui/src/App.test.tsx, ui/package.json`

- [x] `AX-042` | `P3` | owner=`cron` | summary=`Resolve remaining non-blocking UI lint warnings and keep lint baseline clean.` | completed_at=`2026-02-27T04:03:32Z`
  - links=`ui/src/services/api.ts`

- [x] `AX-036` | `P1` | owner=`main` | summary=`Reduce API startup/import overhead by deferring heavy MCP tool imports and avoiding eager MCP HTTP server coupling.` | completed_at=`2026-02-27T03:53:54Z`
  - links=`src/api/main.py, src/api/routes/mcp_test.py, src/api/routes/mcp_http.py`

- [x] `AX-034` | `P1` | owner=`subagent-91dbe2e2` | summary=`Harden JWT access-token expiry to timezone-aware UTC and add regression coverage for expiration semantics.` | completed_at=`2026-02-27T03:32:21Z`
  - links=`src/api/auth.py, tests/unit/test_auth.py`

- [x] `AX-029` | `P3` | owner=`cron` | summary=`Run dedicated React lint-hardening sweep across pre-existing UI lint debt.` | completed_at=`2026-02-27T03:09:10Z`
  - links=`ui/src/components/azuredevops_discovery/AzureDevOpsDiscoveryModal.tsx, ui/src/components/gitlab_discovery/GitLabDiscoveryModal.tsx, ui/src/pages/jobs/JobsPage.tsx, ui/src/pages/login/LoginPage.tsx, ui/src/pages/mcp_test/MCPTestPage.tsx, ui/src/pages/repository_detail/RepositoryDetailPage.tsx, ui/src/components/Repository/AnalysisResults.tsx, ui/src/pages/repositories/RepositoriesPage.tsx`

- [x] `AX-033` | `P1` | owner=`subagent-242a9ff2` | summary=`Stabilization pass: harden Python data validation and React modal runtime accessibility with regression coverage.` | completed_at=`2026-02-27T02:37:40Z`
  - links=`src/utils/data_validation.py, tests/unit/test_data_validation.py, ui/src/components/confirmation_modal/ConfirmationModal.tsx, ui/src/components/confirmation_modal/ConfirmationModal.module.css, ui/src/components/confirmation_modal/ConfirmationModal.test.tsx`

- [x] `AX-027` | `P1` | owner=`cron` | summary=`Add integration-level regression coverage specifically for Python symbol workflows (search/navigation/use-cases).` | completed_at=`2026-02-27T02:07:00Z`
  - links=`tests/integration/test_python_symbol_workflow.py, tests/unit/test_symbol_service.py, src/api/services/symbol_service.py`

- [x] `AX-026` | `P1` | owner=`subagent-97b27fde` | summary=`Increase coverage for low-coverage API routes and worker pipeline steps touched by stabilization.` | completed_at=`2026-02-27T01:06:56Z`
  - links=`src/api/routes/jobs.py, src/workers/tasks.py, tests/unit/test_jobs_routes.py`

- [x] `AX-024` | `P1` | owner=`cron` | summary=`Continue rolling stabilization/hardening across backend + React with regression coverage expansion.` | completed_at=`2026-02-27T00:03:14Z`
  - links=`docs/engineering/BUG_AUDIT_2026-02-26.md, src/config/settings.py, src/parsers/python_parser.py, src/parsers/python_dependency_parser.py, ui/src/components/metrics_panel/MetricsPanel.tsx`

- [x] `AX-023` | `P0` | owner=`main+cron` | summary=`Close remaining Python symbol gaps for annotated module assignments and __all__ augmentation with regression coverage.` | completed_at=`2026-02-26T23:35:45Z`
  - links=`src/parsers/python_parser.py, tests/unit/test_python_parser.py`

- [x] `AX-022` | `P0` | owner=`main` | summary=`Implement Python symbol parser + factory routing for `.py` files.` | completed_at=`2026-02-26T23:04:18Z`
  - links=`commit b6af290, src/parsers/python_parser.py, tests/unit/test_python_parser.py`

- [x] `AX-021` | `P1` | owner=`cron` | summary=`Harden Python dependency parsing and React metrics handling (+Inf/-Inf/NaN) with regression tests.` | completed_at=`2026-02-26T22:23:00Z`
  - links=`src/parsers/python_dependency_parser.py, ui/src/components/metrics_panel/MetricsPanel.tsx`

- [x] `AX-020` | `P1` | owner=`cron` | summary=`Complete baseline stabilization/hardening sweep (security defaults, async/process robustness, lifecycle migration) and verify backend/frontend test/build health.` | completed_at=`2026-02-26T22:07:00Z`
  - links=`docs/engineering/BUG_AUDIT_2026-02-26.md`
