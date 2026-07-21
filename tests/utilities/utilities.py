from tardis.utilities.attributedict import AttributeDict

from unittest.mock import AsyncMock
from typing import Union
import socket


def get_free_port(ip: str):  # from https://gist.github.com/dbrgn/3979133
    s = socket.socket()
    s.bind((ip, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def mock_executor_run_command(
    mock_call_side_effects: list[Union[AttributeDict, Exception]],
):
    def decorator(func):
        def wrapper(self):
            executor = self.mock_executor.return_value
            executor.run_command = AsyncMock(side_effect=mock_call_side_effects)
            func(self)
            executor.run_command = AsyncMock()

        return wrapper

    return decorator
