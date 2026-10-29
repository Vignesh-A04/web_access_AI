"""Unit tests for AgentTaskState machine transitions."""

import pytest
from app.agent.state import AgentTaskState, TaskStateEnum, InvalidStateTransitionError


def test_valid_state_transitions():
    state = AgentTaskState(task_id="t-1", url="https://example.com", instruction="test")
    assert state.status == TaskStateEnum.QUEUED

    # QUEUED -> RUNNING
    state.transition_to(TaskStateEnum.RUNNING)
    assert state.status == TaskStateEnum.RUNNING

    # RUNNING -> WAITING_FOR_APPROVAL
    state.transition_to(TaskStateEnum.WAITING_FOR_APPROVAL)
    assert state.status == TaskStateEnum.WAITING_FOR_APPROVAL

    # WAITING_FOR_APPROVAL -> RUNNING
    state.transition_to(TaskStateEnum.RUNNING)
    assert state.status == TaskStateEnum.RUNNING

    # RUNNING -> COMPLETED
    state.transition_to(TaskStateEnum.COMPLETED)
    assert state.status == TaskStateEnum.COMPLETED
    assert state.completed_at is not None
    assert state.is_terminal() is True


def test_illegal_transition_from_terminal_state():
    state = AgentTaskState(task_id="t-2", url="https://example.com", instruction="test")
    state.transition_to(TaskStateEnum.RUNNING)
    state.transition_to(TaskStateEnum.COMPLETED)

    # Attempting to move from COMPLETED back to RUNNING should raise error
    with pytest.raises(InvalidStateTransitionError):
        state.transition_to(TaskStateEnum.RUNNING)
