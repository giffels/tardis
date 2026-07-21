from tardis.rest.service import RestService

from unittest import TestCase
from unittest.mock import patch, AsyncMock

import asyncio


class TestRestService(TestCase):
    def setUp(self) -> None:
        self.rest_service = RestService()

    @patch("tardis.rest.service.Server")
    def test_run(self, mocked_server):
        mocked_server().serve = AsyncMock()

        mocked_server.reset_mock()

        # Mocking the server means that all its attributes are set, including
        # the "I got killed by SIGINT" flag, which triggers its shutdown heuristic.
        with self.assertRaises(KeyboardInterrupt):
            asyncio.run(self.rest_service.run())
        mocked_server.assert_called_with(config=self.rest_service._config)

    def test_get_user(self):
        self.assertIsNone(self.rest_service.get_user(user_name="test"))

        user = {
            "user_name": "test",
            "hashed_password": "1234abcd",
            "scopes": ["resources:get"],
        }

        rest_service = RestService(
            users=[user],
        )

        self.assertEqual(rest_service.get_user(user_name="test"), user)

        self.assertIsNone(rest_service.get_user(user_name="NotExists"))
