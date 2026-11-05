"""Recover a pending DBOS workflow from its journal, then compact its memory snapshot.

The interruption is in-process, following the other DBOS recovery tests. A deterministic
model exposes the requests after recovery; no provider request or process restart is involved.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from anyio import fail_after

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextContent,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai_harness.compaction import SlidingWindowCompaction
from pydantic_ai_harness.memory import InMemoryStore, Memory, MemoryFile
from tests.conftest import detach_dbos_logging, try_import

with try_import() as imports_successful:
    from dbos import DBOS, DBOSConfig, SetWorkflowID

if TYPE_CHECKING or imports_successful():
    from pydantic_ai.durable_exec.dbos import DBOSDurability

pytestmark = [
    pytest.mark.xdist_group(name='harness-dbos'),
    pytest.mark.skipif(not imports_successful(), reason='dbos not installed'),
    pytest.mark.moves_cache_prefix(reason='SlidingWindowCompaction intentionally removes old history'),
]


class _Crash(BaseException):
    """Leave the workflow pending after the first model response has been journaled."""


@pytest.fixture(scope='module')
def dbos(tmp_path_factory: pytest.TempPathFactory) -> Generator[DBOS, None, None]:
    database: Path = tmp_path_factory.mktemp('memory-dbos') / 'dbos.sqlite'
    config: DBOSConfig = {
        'name': 'memory_recovery',
        'system_database_url': f'sqlite:///{database}',
        'enable_otlp': False,
    }
    instance = DBOS(config=config)
    try:
        DBOS.launch()
        yield instance
    finally:
        try:
            DBOS.destroy()
        finally:
            detach_dbos_logging()


def _snapshots(messages: list[ModelMessage]) -> list[str]:
    return [
        item.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and not isinstance(part.content, str)
        for item in part.content
        if isinstance(item, TextContent)
        and item.metadata is not None
        and item.metadata.get('origin') == 'pydantic-ai-harness.memory.v1'
    ]


class TestMemoryDBOSRecovery:
    async def test_recovery_restores_snapshot_after_compaction(self, dbos: DBOS) -> None:
        reads: list[str] = []
        sent: list[list[str]] = []
        compacted: list[tuple[list[str], list[str]]] = []
        interrupted = False

        class CountingStore(InMemoryStore):
            async def read(self, path: str, *, max_chars: int) -> MemoryFile | None:
                reads.append(path)
                return await super().read(path, max_chars=max_chars)

        class InterruptThenCompact(SlidingWindowCompaction[object]):
            async def before_model_request(
                self, ctx: RunContext[object], request_context: ModelRequestContext
            ) -> ModelRequestContext:
                nonlocal interrupted
                if ctx.run_step == 2 and not interrupted:
                    interrupted = True
                    raise _Crash
                return await super().before_model_request(ctx, request_context)

            async def compact(self, messages: list[ModelMessage], ctx: RunContext[object]) -> list[ModelMessage]:
                before = _snapshots(messages)
                result = await super().compact(messages, ctx)
                compacted.append((before, _snapshots(result)))
                return result

        store = CountingStore({'main/MEMORY.md': '- version A'})
        original = await store.read('main/MEMORY.md', max_chars=100)
        assert original is not None
        reads.clear()

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            sent.append(_snapshots(messages))
            if len(sent) < 5:
                return ModelResponse(parts=[ToolCallPart('lookup', {}, tool_call_id=f'call-{len(sent)}')])
            return ModelResponse(parts=[TextPart('done')])

        def lookup() -> str:
            return 'found'

        agent = Agent(
            FunctionModel(model),
            name='memory_recovery',
            tools=[lookup],
            capabilities=[
                InterruptThenCompact(max_messages=4, keep_messages=2, preserve_first_user_message=False),
                Memory(store=store),
                DBOSDurability(),
            ],
        )

        @DBOS.workflow(name='memory_recovery')
        async def workflow() -> str:
            return (await agent.run('what do I like?')).output

        workflow_id = uuid4().hex
        with SetWorkflowID(workflow_id), pytest.raises(_Crash):
            await workflow()

        assert len(sent) == 1
        assert reads == ['main/MEMORY.md']
        assert compacted == []
        status = await DBOS.get_workflow_status_async(workflow_id)
        assert status is not None and status.status == 'PENDING'
        initial_steps = await DBOS.list_workflow_steps_async(workflow_id)
        await store.write('main/MEMORY.md', '- version B', expected_version=original.version)

        with fail_after(10):
            handle = await DBOS.resume_workflow_async(workflow_id)
            assert await handle.get_result() == 'done'
        [snapshot] = sent[0]
        assert '- version A' in snapshot
        assert sent == [[snapshot]] * 5
        assert compacted == [([snapshot], [])] * 3
        assert reads == ['main/MEMORY.md']
        steps = await DBOS.list_workflow_steps_async(workflow_id)
        assert steps[: len(initial_steps)] == initial_steps
        [loaded] = [
            step for step in steps if step['function_name'] == 'memory_recovery__capability__memory.load_snapshot'
        ]
        assert loaded['error'] is None and loaded['output'] is not None
        assert loaded['output'].value == (original, [], False, None)
        status = await DBOS.get_workflow_status_async(workflow_id)
        assert status is not None and status.status == 'SUCCESS'
