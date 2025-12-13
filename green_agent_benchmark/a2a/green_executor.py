# -*- coding: utf-8 -*-
"""
Base Green Agent executor for A2A protocol.

Based on the official AgentBeats tutorial pattern:
https://github.com/agentbeats/tutorial
"""

from abc import abstractmethod
from pydantic import ValidationError

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InvalidParamsError,
    Task,
    TaskState,
    UnsupportedOperationError,
    InternalError,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError

from .models import EvalRequest


class GreenAgent:
    """
    Abstract base class for green agent implementations.
    
    Green agents orchestrate evaluations and produce assessment results.
    Subclasses must implement:
    - run_eval: Execute the assessment and produce results
    - validate_request: Validate the incoming EvalRequest
    """

    @abstractmethod
    async def run_eval(self, request: EvalRequest, updater: TaskUpdater) -> None:
        """
        Run the evaluation/assessment.
        
        Args:
            request: The evaluation request with participants and config
            updater: TaskUpdater for sending progress updates and artifacts
        """
        pass

    @abstractmethod
    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        """
        Validate the evaluation request.
        
        Args:
            request: The evaluation request to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass


class GreenExecutor(AgentExecutor):
    """
    A2A AgentExecutor that wraps a GreenAgent implementation.
    
    Handles the A2A protocol details and delegates actual evaluation
    to the wrapped GreenAgent.
    """

    def __init__(self, green_agent: GreenAgent):
        self.agent = green_agent

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle incoming A2A task execution."""
        request_text = context.get_user_input()
        
        # Parse and validate the request
        try:
            req: EvalRequest = EvalRequest.model_validate_json(request_text)
            ok, msg = self.agent.validate_request(req)
            if not ok:
                raise ServerError(error=InvalidParamsError(message=msg))
        except ValidationError as e:
            raise ServerError(error=InvalidParamsError(message=e.json()))

        # Create task
        msg = context.message
        if msg:
            task = new_task(msg)
            await event_queue.enqueue_event(task)
        else:
            raise ServerError(error=InvalidParamsError(message="Missing message."))

        # Create updater for progress reporting
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(
            TaskState.working,
            new_agent_text_message(
                f"Starting assessment.\n{req.model_dump_json()}", 
                context_id=context.context_id
            )
        )

        # Run the evaluation
        try:
            await self.agent.run_eval(req, updater)
            await updater.complete()
        except Exception as e:
            print(f"Agent error: {e}")
            await updater.failed(
                new_agent_text_message(
                    f"Agent error: {e}", 
                    context_id=context.context_id
                )
            )
            raise ServerError(error=InternalError(message=str(e)))

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """Cancel is not supported for green agents."""
        raise ServerError(error=UnsupportedOperationError())
