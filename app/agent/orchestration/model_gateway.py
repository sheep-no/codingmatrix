"""Budgeted, cancellation-aware model calls for Orchestrator Core."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.aicloud.llm_caller import call_llm

from .budget import ExecutionBudget
from .models import utc_now

logger = logging.getLogger(__name__)

RawModelResult = Union[Dict[str, Any], AsyncIterator[str]]
ModelCaller = Callable[..., Awaitable[RawModelResult]]


class ModelCallContext(BaseModel):
    """Correlation identifiers and an absolute wall-clock deadline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    file_path: Optional[str] = None
    call_id: str = Field(min_length=1)
    react_round: int = Field(default=0, ge=0)
    context_hash: Optional[str] = Field(default=None, min_length=64, max_length=64)
    started_at: datetime
    deadline_at: datetime

    @model_validator(mode="after")
    def validate_deadline(self) -> "ModelCallContext":
        if self.started_at.tzinfo is None or self.deadline_at.tzinfo is None:
            raise ValueError("model call timestamps must be timezone-aware")
        if self.deadline_at <= self.started_at:
            raise ValueError("deadline_at must be after started_at")
        return self

    @classmethod
    def from_budget(
        cls,
        budget: ExecutionBudget,
        *,
        task_id: str,
        stage_id: str,
        call_id: str,
        file_path: Optional[str] = None,
        react_round: int = 0,
        context_hash: Optional[str] = None,
        task_elapsed_seconds: float = 0.0,
        stage_elapsed_seconds: float = 0.0,
        file_elapsed_seconds: float = 0.0,
    ) -> "ModelCallContext":
        started_at = utc_now()
        return cls(
            task_id=task_id,
            stage_id=stage_id,
            file_path=file_path,
            call_id=call_id,
            react_round=react_round,
            context_hash=context_hash,
            started_at=started_at,
            deadline_at=budget.model_deadline(
                started_at=started_at,
                task_elapsed_seconds=task_elapsed_seconds,
                stage_elapsed_seconds=stage_elapsed_seconds,
                file_elapsed_seconds=file_elapsed_seconds,
            ),
        )


class ModelStreamDataKind(str, Enum):
    KEEPALIVE = "keepalive"
    MODEL_DATA = "model_data"
    STREAM_DATA = "stream_data"


class ModelCallActivity(BaseModel):
    """Latest stream activity timestamps for one correlated model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    last_stream_data_at: Optional[datetime] = None
    last_keepalive_at: Optional[datetime] = None
    last_model_data_at: Optional[datetime] = None


class ModelGatewayError(RuntimeError):
    """Structured model failure carrying correlation-safe diagnostics."""

    code = "model_error"

    def __init__(self, message: str, context: ModelCallContext) -> None:
        super().__init__(message)
        self.context = context

    @property
    def diagnostic(self) -> Dict[str, Any]:
        diagnostic = {
            "code": self.code,
            "message": str(self),
            "task_id": self.context.task_id,
            "stage_id": self.context.stage_id,
            "file_path": self.context.file_path,
            "call_id": self.context.call_id,
            "react_round": self.context.react_round,
        }
        if self.context.context_hash is not None:
            diagnostic["context_hash"] = self.context.context_hash
        return diagnostic


class ModelCallTimeout(ModelGatewayError):
    code = "model_timeout"


class ModelCallCancelled(ModelGatewayError):
    code = "model_cancelled"


class ModelGateway:
    """Run model acquisition and full stream consumption under one deadline."""

    def __init__(
        self,
        caller: ModelCaller = call_llm,
        *,
        activity_callback: Optional[
            Callable[[ModelCallContext, ModelStreamDataKind, datetime], None]
        ] = None,
    ) -> None:
        self._caller = caller
        self._activity_callback = activity_callback
        self._activity: Dict[str, ModelCallActivity] = {}

    def activity_for(self, call_id: str) -> ModelCallActivity:
        return self._activity.get(call_id, ModelCallActivity(call_id=call_id))

    async def call(
        self,
        context: ModelCallContext,
        *,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        try:
            result = await self._await_with_controls(
                self._caller(
                    **kwargs,
                    stream=False,
                    timeout=self._remaining_seconds(context),
                    cancel_event=cancel_event,
                ),
                context,
                cancel_event,
            )
        except TimeoutError as exc:
            raise ModelCallTimeout("model call wall-clock deadline exceeded", context) from exc

        if hasattr(result, "__aiter__"):
            await self._close_stream(result)
            raise ModelGatewayError("non-streaming model call returned a stream", context)
        return result

    async def stream(
        self,
        context: ModelCallContext,
        *,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        stream_result: Optional[AsyncIterator[str]] = None
        try:
            async with asyncio.timeout(self._remaining_seconds(context)):
                result = await self._await_with_cancel(
                    self._caller(
                        **kwargs,
                        stream=True,
                        timeout=self._remaining_seconds(context),
                        cancel_event=cancel_event,
                    ),
                    context,
                    cancel_event,
                )
                if not hasattr(result, "__aiter__"):
                    raise ModelGatewayError("streaming model call returned a non-stream result", context)
                stream_result = result
                iterator = result.__aiter__()
                while True:
                    try:
                        chunk = await self._await_with_cancel(
                            iterator.__anext__(), context, cancel_event
                        )
                    except StopAsyncIteration:
                        break
                    self._record_activity(context, chunk)
                    yield chunk
        except TimeoutError as exc:
            raise ModelCallTimeout("model stream wall-clock deadline exceeded", context) from exc
        finally:
            if stream_result is not None:
                await self._close_stream(stream_result)

    async def _await_with_controls(
        self,
        awaitable: Awaitable[RawModelResult],
        context: ModelCallContext,
        cancel_event: Optional[asyncio.Event],
    ) -> RawModelResult:
        async with asyncio.timeout(self._remaining_seconds(context)):
            return await self._await_with_cancel(awaitable, context, cancel_event)

    async def _await_with_cancel(
        self,
        awaitable: Awaitable[Any],
        context: ModelCallContext,
        cancel_event: Optional[asyncio.Event],
    ) -> Any:
        if cancel_event is None:
            return await awaitable
        if cancel_event.is_set():
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise ModelCallCancelled("model call was cancelled", context)

        operation = asyncio.ensure_future(awaitable)
        cancellation = asyncio.create_task(cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {operation, cancellation}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancellation in done:
                if operation.done() and not operation.cancelled():
                    result = operation.result()
                    if hasattr(result, "__aiter__"):
                        await self._close_stream(result)
                else:
                    operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
                raise ModelCallCancelled("model call was cancelled", context)
            return await operation
        except asyncio.CancelledError:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            raise
        finally:
            cancellation.cancel()
            await asyncio.gather(cancellation, return_exceptions=True)

    def _remaining_seconds(self, context: ModelCallContext) -> float:
        remaining = (context.deadline_at - utc_now()).total_seconds()
        if remaining <= 0:
            raise ModelCallTimeout("model call wall-clock deadline exceeded", context)
        return remaining

    def _record_activity(self, context: ModelCallContext, chunk: str) -> None:
        observed_at = utc_now()
        kind = self._classify_chunk(chunk)
        current = self.activity_for(context.call_id)
        updates: Dict[str, Any] = {"last_stream_data_at": observed_at}
        if kind is ModelStreamDataKind.KEEPALIVE:
            updates["last_keepalive_at"] = observed_at
        elif kind is ModelStreamDataKind.MODEL_DATA:
            updates["last_model_data_at"] = observed_at
        self._activity[context.call_id] = current.model_copy(update=updates)
        if self._activity_callback is not None:
            self._activity_callback(context, kind, observed_at)

    @staticmethod
    def _classify_chunk(chunk: str) -> ModelStreamDataKind:
        stripped = chunk.strip()
        if not stripped or stripped.startswith(":") or stripped.lower() in {
            "heartbeat",
            "keepalive",
            "[keepalive]",
        }:
            return ModelStreamDataKind.KEEPALIVE
        if stripped.startswith("data: "):
            stripped = stripped[6:]
        try:
            payload = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            return ModelStreamDataKind.MODEL_DATA
        for choice in payload.get("choices") or ():
            delta = choice.get("delta") or {}
            if delta.get("content") or delta.get("reasoning_content"):
                return ModelStreamDataKind.MODEL_DATA
        return ModelStreamDataKind.STREAM_DATA

    @staticmethod
    async def _close_stream(stream: Any) -> None:
        close = getattr(stream, "aclose", None)
        if close is None:
            return
        try:
            await close()
        except Exception as exc:
            logger.warning("关闭模型流失败: %s", exc)
