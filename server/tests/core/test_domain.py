from datetime import UTC, datetime

import pytest

from app.agents.graph import build_graph, make_graph_state
from app.agents.run_states import InvalidRunTransition, transition_run
from app.core.config import Settings
from app.domain.models import Run
from app.infrastructure.providers import (
    DeterministicModelProvider,
    ModelProvider,
    ModelRequest,
    ModelRouter,
    StopEvent,
    TextDelta,
    ToolDefinition,
)


class TestModelProvider(ModelProvider):
    name = "test"

    def stream(self, request: ModelRequest):
        yield (
            f"I'm {request.bot_name}, your {request.role_title}. "
            f"Following my brief - {request.instructions} - ready."
        )

    def stream_structured(self, request: ModelRequest, tools: list[ToolDefinition]):
        yield TextDelta(
            text=(
                f"I'm {request.bot_name}, your {request.role_title}. "
                f"Following my brief - {request.instructions} - ready."
            )
        )
        yield StopEvent(stop_reason="end_turn", usage={"input_tokens": 10, "output_tokens": 20})


def test_provider_contract_is_role_neutral_and_instruction_aware() -> None:
    request = ModelRequest(
        bot_name="Mira",
        role_title="Garden planner",
        instructions="Always suggest drought-tolerant plants.",
        messages=[("user", "Help with the front bed")],
    )
    response = "".join(TestModelProvider().stream(request))
    assert "Mira" in response
    assert "Garden planner" in response
    assert "drought-tolerant" in response


def test_deterministic_provider_is_ci_only() -> None:
    with pytest.raises(ValueError):
        ModelRouter(Settings(model_provider="deterministic", environment="development"))
    router = ModelRouter(Settings(model_provider="deterministic", environment="test"))
    assert isinstance(router.route(), DeterministicModelProvider)


def test_generic_langgraph_reaches_answer_state() -> None:
    import uuid

    graph = build_graph(TestModelProvider())
    initial = make_graph_state(
        bot_id=str(uuid.uuid4()),
        bot_name="Atlas",
        role_title="Trip researcher",
        instructions="Be concise.",
        workspace_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        messages=[("user", "Plan a day")],
    )
    state = graph.invoke(initial)
    assert state["response"].startswith("I'm Atlas")


def test_run_state_machine_rejects_stale_terminal_overwrite() -> None:
    run = Run(status="cancelled")
    with pytest.raises(InvalidRunTransition):
        transition_run(run, "completed")


def test_run_state_machine_sets_terminal_timestamp() -> None:
    run = Run(status="running")
    now = datetime(2026, 9, 17, tzinfo=UTC)
    transition_run(run, "completed", now=now)
    assert run.status == "completed"
    assert run.completed_at == now
