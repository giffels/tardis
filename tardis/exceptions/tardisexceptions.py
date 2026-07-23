from typing import Any, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from tardis.interfaces.state import State


class TardisAuthError(Exception):
    pass


class TardisDroneCrashed(Exception):
    pass


class TardisError(Exception):
    pass


class TardisTimeout(Exception):
    pass


class TardisQuotaExceeded(Exception):
    pass


class TardisResourceStatusUpdateFailed(Exception):
    pass


class TardisInvalidStateTransition(Exception):
    """
    Raised when no state transition is defined for the given combination of
    task_pipeline results.
    """

    def __init__(
        self, current_state: "Type[State]", task_pipeline_results: dict[str, Any]
    ):
        super().__init__(
            current_state,
            task_pipeline_results,
        )
        self.current_state = current_state
        self.task_pipeline_results = task_pipeline_results

    def __str__(self):
        return f"Unknown state transition in {self.current_state.__name__}:" + " ".join(
            f"{name}={value!r}" for name, value in self.task_pipeline_results.items()
        )
