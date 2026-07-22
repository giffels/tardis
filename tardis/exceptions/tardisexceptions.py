from typing import TYPE_CHECKING
from typing import Type

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


class TardisUnknownStateTransition(Exception):
    """
    Raised when no state transition is defined for the given combination of
    task_pipeline results.
    """

    def __init__(self, current_state: "Type[State]", **task_pipeline_results):
        super().__init__(
            f"Unknown state transition in {current_state.__name__}: "
            + ", ".join(
                f"{name}={value!r}" for name, value in task_pipeline_results.items()
            )
        )
