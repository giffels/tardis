import logging

from tardis.resources.dronestates import BootingState
from tardis.resources.dronestates import RequestState, DownState
from tardis.interfaces.state import State
from tardis.plugins.sqliteregistry import (
    SqliteRegistry,
    adapt_datetime,
    convert_datetime,
)
from tardis.utilities.attributedict import AttributeDict

from unittest import TestCase
from unittest.mock import patch
from unittest.mock import Mock

import asyncio
import datetime
import os
import sqlite3


class TestSqliteRegistry(TestCase):
    mock_config_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.test_site_name = "MyGreatTestSite"
        cls.other_test_site_name = "MyOtherTestSite"
        cls.test_machine_type = "MyGreatTestMachineType"
        cls.tables_in_db = {"MachineTypes", "Resources", "ResourceStates", "Sites"}
        cls.test_resource_attributes = {
            "remote_resource_uuid": None,
            "drone_uuid": f"{cls.test_site_name}-07af52405e",
            "site_name": cls.test_site_name,
            "machine_type": cls.test_machine_type,
            "created": datetime.datetime(2018, 11, 16, 15, 49, 58),
            "updated": datetime.datetime(2018, 11, 16, 15, 49, 58),
        }
        cls.test_updated_resource_attributes = {
            "remote_resource_uuid": "bf85022b-fdd6-42b1-932d-086c288d4755",
            "drone_uuid": f"{cls.test_site_name}-07af52405e",
            "site_name": cls.test_site_name,
            "machine_type": cls.test_machine_type,
            "created": datetime.datetime(2018, 11, 16, 15, 49, 58),
            "updated": datetime.datetime(2018, 11, 16, 15, 50, 58),
        }

        cls.test_get_resources_result = {
            "remote_resource_uuid": cls.test_resource_attributes[
                "remote_resource_uuid"
            ],
            "drone_uuid": cls.test_resource_attributes["drone_uuid"],
            "state": str(RequestState()),
            "created": cls.test_resource_attributes["created"],
            "updated": cls.test_resource_attributes["updated"],
        }

        cls.test_notify_result = (
            cls.test_resource_attributes["remote_resource_uuid"],
            cls.test_resource_attributes["drone_uuid"],
            str(RequestState()),
            cls.test_resource_attributes["site_name"],
            cls.test_resource_attributes["machine_type"],
            str(cls.test_resource_attributes["created"]),
            str(cls.test_resource_attributes["updated"]),
        )

        cls.test_updated_notify_result = (
            cls.test_updated_resource_attributes["remote_resource_uuid"],
            cls.test_updated_resource_attributes["drone_uuid"],
            str(BootingState()),
            cls.test_updated_resource_attributes["site_name"],
            cls.test_updated_resource_attributes["machine_type"],
            str(cls.test_updated_resource_attributes["created"]),
            str(cls.test_updated_resource_attributes["updated"]),
        )

        cls.mock_config_patcher = patch("tardis.plugins.sqliteregistry.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()

    def setUp(self):
        self.test_path = os.path.dirname(os.path.realpath(__file__))
        self.test_db = os.path.join(self.test_path, "test.db")
        try:
            os.remove(self.test_db)
        except FileNotFoundError:
            pass

        config = self.mock_config.return_value
        config.Plugins.SqliteRegistry.db_file = self.test_db
        config.Sites = [AttributeDict(name=self.test_site_name)]
        getattr(config, self.test_site_name).MachineTypes = [self.test_machine_type]

        self.registry = SqliteRegistry()

    def execute_db_query(self, sql_query):
        with sqlite3.connect(self.test_db) as connection:
            cursor = connection.cursor()
            cursor.execute(sql_query)

            return cursor.fetchall()

    def test_datetime_adapter_and_converter(self):
        """
        Tests that datetime objects are correctly adapted to strings (with space)
        and converted back to datetime objects
        """
        test_dt = datetime.datetime(2023, 5, 13, 12, 30, 45)

        # Test Adapter (Writing)
        adapted_value = adapt_datetime(test_dt)
        self.assertEqual(adapted_value, "2023-05-13 12:30:45")

        # 2. Test Converter (Reading)
        encoded_value = b"2023-05-13 12:30:45"
        converted_value = convert_datetime(encoded_value)
        self.assertEqual(converted_value, test_dt)
        self.assertIsInstance(converted_value, datetime.datetime)

    def test_add_machine_types(self):
        test_site_names = (self.test_site_name, self.other_test_site_name)

        for site_name in test_site_names:
            self.registry.add_site(site_name)
            self.registry.add_machine_types(site_name, self.test_machine_type)

        # Database content has to be checked several times
        # Define inline function to re-use code
        def check_db_content():
            machine_types = self.execute_db_query(
                sql_query="""SELECT MachineTypes.machine_type, Sites.site_name
                             FROM MachineTypes
                             JOIN Sites ON MachineTypes.site_id=Sites.site_id"""
            )

            self.assertEqual(
                len(test_site_names),
                len(machine_types),
                msg="Number of rows added to the database is different from the"
                " numbers of rows retrieved from the database!",
            )

            self.assertListEqual(
                [(self.test_machine_type, site_name) for site_name in test_site_names],
                machine_types,
            )

        check_db_content()

        with self.assertLogs(
            logger="cobald.runtime.tardis.plugins.sqliteregistry", level=logging.DEBUG
        ):
            self.registry.add_machine_types(self.test_site_name, self.test_machine_type)

        check_db_content()

    def test_add_site(self):
        test_site_names = (self.test_site_name, self.other_test_site_name)
        self.registry.add_site(test_site_names[0])

        # Database content has to be checked several times
        # Define inline function to re-use code
        def check_db_content():
            for row, site_name in zip(  # noqa B905
                self.execute_db_query("SELECT site_name FROM Sites"), test_site_names
            ):
                self.assertEqual(row[0], site_name)

        check_db_content()

        with self.assertLogs(
            logger="cobald.runtime.tardis.plugins.sqliteregistry", level=logging.DEBUG
        ):
            self.registry.add_site(test_site_names[0])

        check_db_content()

        self.registry.add_site(test_site_names[1])

        check_db_content()

    def test_connect(self):
        created_tables = {
            table_name[0]
            for table_name in self.execute_db_query(
                sql_query="SELECT name FROM sqlite_master WHERE type='table'"
            )
            if table_name[0] != "sqlite_sequence"
        }
        self.assertEqual(created_tables, self.tables_in_db)

    def test_double_schema_deployment(self):
        SqliteRegistry()
        SqliteRegistry()

    @patch("tardis.plugins.sqliteregistry.logging", Mock())
    def test_get_resource_state(self):
        self.registry.add_site(self.test_site_name)
        self.registry.add_machine_types(self.test_site_name, self.test_machine_type)
        asyncio.run(self.registry.notify(RequestState(), self.test_resource_attributes))

        self.assertEqual(
            asyncio.run(
                self.registry.get_resource_state(
                    drone_uuid=self.test_resource_attributes["drone_uuid"],
                )
            ),
            [{"state": "RequestState"}],
        )

        self.assertEqual(
            asyncio.run(
                self.registry.get_resource_state(
                    drone_uuid="does_not_exists",
                )
            ),
            [],
        )

    @patch("tardis.plugins.sqliteregistry.logging", Mock())
    def test_get_resources(self):
        self.registry.add_site(self.test_site_name)
        self.registry.add_machine_types(self.test_site_name, self.test_machine_type)
        asyncio.run(self.registry.notify(RequestState(), self.test_resource_attributes))

        self.assertListEqual(
            self.registry.get_resources(
                site_name=self.test_site_name, machine_type=self.test_machine_type
            ),
            [self.test_get_resources_result],
        )

    @patch("tardis.plugins.sqliteregistry.logging", Mock())
    def test_notify(self):
        # Database has to be queried multiple times
        # Define inline function to re-use code
        def fetch_all():
            return self.execute_db_query(
                sql_query="""SELECT R.remote_resource_uuid, R.drone_uuid, RS.state,
                S.site_name, MT.machine_type, R.created, R.updated
                FROM Resources R
                JOIN ResourceStates RS ON R.state_id = RS.state_id
                JOIN Sites S ON R.site_id = S.site_id
                JOIN MachineTypes MT ON R.machine_type_id = MT.machine_type_id"""
            )

        self.registry.add_site(self.test_site_name)
        self.registry.add_machine_types(self.test_site_name, self.test_machine_type)

        asyncio.run(self.registry.notify(RequestState(), self.test_resource_attributes))

        self.assertEqual([self.test_notify_result], fetch_all())

        with self.assertRaises(sqlite3.IntegrityError) as ie:
            asyncio.run(
                self.registry.notify(RequestState(), self.test_resource_attributes)
            )
        self.assertTrue("unique" in str(ie.exception).lower())

        asyncio.run(
            self.registry.notify(
                BootingState(),
                self.test_updated_resource_attributes,
            )
        )

        self.assertEqual([self.test_updated_notify_result], fetch_all())

        asyncio.run(
            self.registry.notify(DownState(), self.test_updated_resource_attributes)
        )

        self.assertListEqual([], fetch_all())

    def test_insert_resources(self):
        # Database has to be queried multiple times
        # Define inline function to re-use code
        def fetch_all():
            return self.execute_db_query(
                sql_query="""SELECT R.remote_resource_uuid, R.drone_uuid, RS.state,
                S.site_name, MT.machine_type, R.created, R.updated
                FROM Resources R
                JOIN ResourceStates RS ON R.state_id = RS.state_id
                JOIN Sites S ON R.site_id = S.site_id
                JOIN MachineTypes MT ON R.machine_type_id = MT.machine_type_id"""
            )

        test_site_names = (self.test_site_name, self.other_test_site_name)
        for site_name in test_site_names:
            self.registry.add_site(site_name)
            self.registry.add_machine_types(site_name, self.test_machine_type)

        bind_parameters = {"state": "RequestState"}
        bind_parameters.update(self.test_resource_attributes)

        asyncio.run(self.registry.insert_resource(bind_parameters))

        self.assertListEqual([self.test_notify_result], fetch_all())

        with self.assertRaises(sqlite3.IntegrityError) as ie:
            asyncio.run(self.registry.insert_resource(bind_parameters))
        self.assertTrue("unique" in str(ie.exception).lower())

        self.assertListEqual([self.test_notify_result], fetch_all())

        # Test same remote_resource_uuids on different sites
        bind_parameters = {"state": "BootingState"}
        bind_parameters.update(self.test_resource_attributes)
        bind_parameters["drone_uuid"] = f"{self.other_test_site_name}-045285abef1"
        bind_parameters["site_name"] = self.other_test_site_name

        asyncio.run(self.registry.insert_resource(bind_parameters))

        other_test_notify_result = (
            self.test_resource_attributes["remote_resource_uuid"],
            f"{self.other_test_site_name}-045285abef1",
            str(BootingState()),
            self.other_test_site_name,
            self.test_resource_attributes["machine_type"],
            str(self.test_resource_attributes["created"]),
            str(self.test_resource_attributes["updated"]),
        )

        self.assertListEqual(
            [self.test_notify_result, other_test_notify_result], fetch_all()
        )

    def test_resource_status(self):
        status = {
            row[0]
            for row in self.execute_db_query(
                sql_query="SELECT state FROM ResourceStates"
            )
        }

        self.assertEqual(status, {state for state in State.get_all_states()})
