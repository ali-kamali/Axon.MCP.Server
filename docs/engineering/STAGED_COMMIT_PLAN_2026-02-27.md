# Staged Commit Plan (2026-02-27)

Prepared to support `AX-025` (safe curation/commit/push of stabilization tree).

## Proposed commit sequence

1. **Backend auth + validation hardening**
   - `src/api/auth.py`
   - `src/utils/data_validation.py`
   - `tests/unit/test_auth.py`
   - `tests/unit/test_data_validation.py`

2. **API route and worker reliability tests**
   - `src/api/routes/jobs.py`
   - `src/workers/tasks.py`
   - `tests/unit/test_jobs_routes.py`
   - `tests/unit/test_repository_statistics_workers_routes.py`
   - `tests/unit/test_mcp_routes.py`

3. **Symbol pipeline improvements**
   - `src/api/schemas/symbols.py`
   - `src/api/services/symbol_service.py`
   - `src/mcp_server/tools/symbols.py`
   - `tests/unit/test_symbol_service.py`
   - `tests/unit/test_symbols_routes.py`
   - `tests/integration/test_python_symbol_workflow.py`

4. **Worker/pipeline regression expansion (coverage sweep)**
   - `tests/unit/test_incremental_sync.py`
   - `tests/unit/test_pipeline_context_step.py`

5. **UI linting + route-level split changes**
   - `ui/src/App.tsx`
   - `ui/src/App.test.tsx`
   - `ui/package.json`
   - Remaining React component/page edits under `ui/src/**`

6. **Task board/docs updates**
   - `docs/engineering/AXON_TASK_LIST.md`
   - `docs/engineering/STAGED_COMMIT_PLAN_2026-02-27.md`

## Notes

- Keep commit boundaries narrow and test-backed.
- For each commit, run targeted tests/lint for impacted area before commit.
- Push only after local commit stack is validated.
