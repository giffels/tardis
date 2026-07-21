from tests.rest_t.routers_t.base_test_case_routers import TestCaseRouters

from unittest.mock import AsyncMock

import asyncio


def is_list_str(resp):
    return isinstance(resp, list) and all(isinstance(x, str) for x in resp)


class TestTypes(TestCaseRouters):
    def setUp(self) -> None:
        super().setUp()
        self.reset_scopes()
        self.login()

    def test_types(self):
        self.clear_lru_cache()
        self.mock_types.get_available_states = AsyncMock(
            return_value=[{"state": "state"}, {"state": "state2"}]
        )
        self.mock_types.get_available_sites = AsyncMock(
            return_value=[{"site": "site"}, {"site": "site2"}]
        )
        self.mock_types.get_available_machine_types = AsyncMock(
            return_value=[{"machine_type": "type"}, {"machine_type": "type2"}]
        )

        self.clear_lru_cache()
        response = asyncio.run(self.client.get("/types/states"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["state", "state2"])

        self.clear_lru_cache()
        response = asyncio.run(self.client.get("/types/sites"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["site", "site2"])

        self.clear_lru_cache()
        response = asyncio.run(self.client.get("/types/machine_types"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["type", "type2"])

        # Invalid scope
        self.clear_lru_cache()
        self.set_scopes(["resources:patch"])
        self.login()
        response = asyncio.run(self.client.get("/types/states"))
        self.assertEqual(response.status_code, 403)
