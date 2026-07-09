from tardis.rest.app import crud
from tardis.plugins.sqliteregistry import SqliteRegistry

from unittest import TestCase
from unittest.mock import MagicMock

import asyncio


class TestCRUD(TestCase):
    def setUp(self) -> None:
        self.sql_registry_mock = MagicMock(spec=SqliteRegistry)

    def test_get_resource_state(self):
        async def mocked_async_execute(sql_query: str, bind_parameters: dict):
            return_values = {
                "test-available-01234567ab": [
                    {"drone_uuid": "test-01234567ab", "state": "AvailableState"}
                ],
                "test-noexists-01234567ab": [],
            }

            return return_values[bind_parameters["drone_uuid"]]

        self.sql_registry_mock.async_execute.side_effect = mocked_async_execute

        self.assertEqual(
            [],
            asyncio.run(
                crud.get_resource_state(
                    sql_registry=self.sql_registry_mock,
                    drone_uuid="test-noexists-01234567ab",
                )
            ),
        )

        self.sql_registry_mock.async_execute.assert_called_with(
            """
    SELECT R.drone_uuid, RS.state
    FROM Resources R
    JOIN ResourceStates RS ON R.state_id = RS.state_id
    WHERE R.drone_uuid = :drone_uuid""",
            {"drone_uuid": "test-noexists-01234567ab"},
        )

        self.sql_registry_mock.reset_mock()

        self.assertEqual(
            [{"drone_uuid": "test-01234567ab", "state": "AvailableState"}],
            asyncio.run(
                crud.get_resource_state(
                    sql_registry=self.sql_registry_mock,
                    drone_uuid="test-available-01234567ab",
                )
            ),
        )

        self.sql_registry_mock.async_execute.assert_called_with(
            """
    SELECT R.drone_uuid, RS.state
    FROM Resources R
    JOIN ResourceStates RS ON R.state_id = RS.state_id
    WHERE R.drone_uuid = :drone_uuid""",
            {"drone_uuid": "test-available-01234567ab"},
        )

    def test_get_resources(self):
        full_expected_resources = [
            {
                "remote_resource_uuid": "14fa5640a7c146e482e8be41ec5dffea",
                "state": "AvailableState",
                "drone_uuid": "test-0125bc9fd8",
                "site_name": "Test",
                "machine_type": "m1.test",
                "created": "2021-10-08T12:42:16.354400",
                "updated": "2021-10-08T12:42:28.382025",
            },
            {
                "remote_resource_uuid": "b3efcc5bc8b741af9222987e0434ca61",
                "state": "AvailableState",
                "drone_uuid": "test-6af3cfef14",
                "site_name": "Test",
                "machine_type": "m1.test",
                "created": "2021-10-08T12:42:16.373454",
                "updated": "2021-10-08T12:42:30.648325",
            },
        ]

        async def mocked_async_execute(sql_query: str, bind_parameters: dict):
            return full_expected_resources

        self.sql_registry_mock.async_execute.side_effect = mocked_async_execute

        self.assertEqual(
            full_expected_resources,
            asyncio.run(
                crud.get_resources(
                    sql_registry=self.sql_registry_mock,
                ),
            ),
        )

        self.sql_registry_mock.async_execute.assert_called_with(
            """
    SELECT R.remote_resource_uuid , RS.state, R.drone_uuid, S.site_name,
    MT.machine_type, R.created, R.updated
    FROM Resources R
    JOIN ResourceStates RS ON R.state_id = RS.state_id
    JOIN Sites S ON R.site_id = S.site_id
    JOIN MachineTypes MT ON R.machine_type_id = MT.machine_type_id""",
            {},
        )
