from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional
import logging
from .context import PipelineContext

logger = logging.getLogger(__name__)

class StepCriticality(Enum):
    REQUIRED = "required"      # Failure aborts pipeline
    IMPORTANT = "important"    # Logged as warning, continue
    OPTIONAL = "optional"      # Logged as info, continue

class PipelineStep(ABC):
    """
    Base class for all pipeline steps.
    Each step encapsulates a distinct unit of work in the sync process.
    """
    
    # Dependencies (Finding 3.1)
    depends_on: List[str] = []
    produces: List[str] = []
    
    # Criticality Policy (Finding 3.2)
    criticality: StepCriticality = StepCriticality.REQUIRED
    
    # Checkpoint support (Finding 2.2)
    creates_checkpoint: bool = False

    # Fix 3.1: Strict validation of required context fields
    requires_fields: List[str] = []

    
    @property
    def name(self) -> str:
        """Return the name of the step (defaults to class name)."""
        return self.__class__.__name__

    async def run(self, context: PipelineContext) -> None:
        """
        Execute the step with validation, error handling, and state tracking.
        This is the entry point called by the orchestrator.
        """
        self.log_start()
        
        # Runtime dependency check
        for dependency in self.depends_on:
            if dependency not in context.completed_steps:
                logger.warning(
                    f"Step {self.name} requirement {dependency} missing from completed_steps. "
                    f"Proceeding, but this may fail."
                )

        try:
            # Fix 3.1: Strict Pre-condition Validation
            for field_name in self.requires_fields:
                value = getattr(context, field_name, None)
                if value is None:
                    raise ValueError(
                        f"Pre-condition violation: Step {self.name} requires context.{field_name}, "
                        f"but it is None. Ensure prerequisite steps have run successfully."
                    )

            # Call the actual implementation
            await self.execute(context)
            
            # Mark as completed
            context.completed_steps.add(self.name)
            for output in self.produces:
                context.available_data.add(output)
                
        except Exception as e:
            # Fix 4.1: Preserve full error context using structured error object
            from .context import PipelineError
            import traceback
            
            error_info = PipelineError(
                step_name=self.name,
                exception_type=type(e).__name__,
                error_message=str(e),
                traceback_str=traceback.format_exc(),
                context={"execution_id": context.execution_id}
            )
            context.errors.append(error_info)

            if self.criticality == StepCriticality.REQUIRED:
                logger.error(f"Critical step {self.name} failed: {e}")
                raise
            elif self.criticality == StepCriticality.IMPORTANT:
                logger.warning(f"Important step {self.name} failed but continuing: {e}")
            else:
                logger.info(f"Optional step {self.name} failed: {e}")


    @abstractmethod
    async def execute(self, context: PipelineContext) -> None:
        """
        Execute the step logic.
        Must be implemented by concrete steps.
        
        Args:
            context: The shared pipeline context.
            
        Raises:
            Exception: If the step fails critically.
        """
        pass
    
    async def can_skip(self, context: PipelineContext) -> bool:
        """
        Determine if this step can be skipped based on current context.
        """
        return False
        
    def log_start(self):
        logger.info(f"Starting step: {self.name}")
        
    def log_completion(self, duration: float):
        logger.info(f"Completed step: {self.name} in {duration:.2f}s")
