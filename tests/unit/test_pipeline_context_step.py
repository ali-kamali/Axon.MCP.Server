import pytest
from types import SimpleNamespace

from src.workers.pipeline.context import PipelineContext, PipelineMetrics
from src.workers.pipeline.step import PipelineStep, StepCriticality


class _DummyStep(PipelineStep):
    async def execute(self, context: PipelineContext) -> None:
        context.metadata["ran"] = True


class _FailingStep(PipelineStep):
    def __init__(self, message: str = "boom"):
        self._message = message

    async def execute(self, context: PipelineContext) -> None:
        raise RuntimeError(self._message)


@pytest.mark.asyncio
async def test_pipeline_context_files_processed_legacy_property():
    ctx = PipelineContext(repository_id=123, session=SimpleNamespace())

    ctx.files_processed = 7

    assert ctx.metrics.files_processed == 7
    assert ctx.files_processed == 7


def test_pipeline_metrics_to_dict_includes_typed_fields():
    metrics = PipelineMetrics(files_processed=3, symbols_created=11)

    as_dict = metrics.to_dict()

    assert as_dict["files_processed"] == 3
    assert as_dict["symbols_created"] == 11
    assert "embeddings_generated" in as_dict


@pytest.mark.asyncio
async def test_pipeline_context_refresh_repository_rehydrates_from_session():
    expected_repo = SimpleNamespace(id=42, name="repo")

    class _Scalar:
        def scalar_one(self):
            return expected_repo

    class _Session:
        async def execute(self, _query):
            return _Scalar()

    ctx = PipelineContext(repository_id=42, session=_Session())

    repo = await ctx.refresh_repository()

    assert repo is expected_repo
    assert ctx.repository is expected_repo


@pytest.mark.asyncio
async def test_step_run_marks_completed_and_outputs_when_successful():
    step = _DummyStep()
    step.produces = ["parsed_files"]

    ctx = PipelineContext(repository_id=1, session=SimpleNamespace())

    await step.run(ctx)

    assert "_DummyStep" in ctx.completed_steps
    assert "parsed_files" in ctx.available_data
    assert ctx.metadata["ran"] is True


@pytest.mark.asyncio
async def test_step_run_requires_fields_validation_raises_for_required_step():
    step = _DummyStep()
    step.requires_fields = ["repository"]

    ctx = PipelineContext(repository_id=1, session=SimpleNamespace())

    with pytest.raises(ValueError):
        await step.run(ctx)

    assert len(ctx.errors) == 1
    assert ctx.errors[0].step_name == "_DummyStep"
    assert "requires context.repository" in ctx.errors[0].error_message


@pytest.mark.asyncio
async def test_step_run_non_required_failure_is_recorded_and_continues():
    step = _FailingStep("important failure")
    step.criticality = StepCriticality.IMPORTANT

    ctx = PipelineContext(repository_id=1, session=SimpleNamespace())

    await step.run(ctx)

    assert len(ctx.errors) == 1
    err = ctx.errors[0]
    assert err.step_name == "_FailingStep"
    assert err.exception_type == "RuntimeError"
    assert "important failure" in err.error_message
    assert "_FailingStep" not in ctx.completed_steps
