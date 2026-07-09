from tardis.rest.app.security import get_user
from tardis.utilities.attributedict import AttributeDict

from httpx import AsyncClient, ASGITransport

from unittest import TestCase
from unittest.mock import patch

import asyncio


class TestCaseRouters(TestCase):
    mock_sqlite_registry_patcher = None
    mock_crud_patcher = None
    mock_config_patcher = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.mock_sqlite_registry_patcher = patch(
            "tardis.rest.app.database.SqliteRegistry"
        )
        cls.mock_types_patcher = patch("tardis.rest.app.routers.types.crud")
        cls.mock_crud_patcher = patch("tardis.rest.app.routers.resources.crud")
        cls.mock_config_patcher = patch("tardis.rest.app.security.Configuration")
        cls.mock_sqlite_registry = cls.mock_sqlite_registry_patcher.start()
        cls.mock_types = cls.mock_types_patcher.start()
        cls.mock_crud = cls.mock_crud_patcher.start()
        cls.mock_config = cls.mock_config_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.mock_sqlite_registry_patcher.stop()
        cls.mock_crud_patcher.stop()
        cls.mock_config_patcher.stop()

    def setUp(self) -> None:
        self.config = self.mock_config.return_value
        self.config.Services.restapi.get_user.return_value = AttributeDict(
            user_name="test",
            hashed_password="$2b$12$Gkl8KYNGRMhx4kB0bKJnyuRuzOrx3LZlWf1CReIsDk9HyWoUGBihG",  # noqa B509
            scopes=["resources:get", "user:get", "resources:patch"],
        )

        from tardis.rest.app.main import (
            app,
        )  # has to be imported after SqliteRegistry patch

        self.client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        self.test_user = {
            "user_name": "test1",
            "password": "test",
        }

    def set_scopes(self, scopes: list):
        self.config.Services.restapi.get_user.return_value.scopes = scopes

    def reset_scopes(self):
        self.set_scopes(["resources:get", "user:get", "resources:patch"])

    def get_scopes(self):
        return self.config.Services.restapi.get_user.return_value.scopes

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())

    def login(self, user: dict = None):
        self.clear_lru_cache()
        response = asyncio.run(
            self.client.post("/user/login", json=user or self.test_user)
        )
        self.assertEqual(response.status_code, 200)

    @staticmethod
    def clear_lru_cache():
        get_user.cache_clear()
