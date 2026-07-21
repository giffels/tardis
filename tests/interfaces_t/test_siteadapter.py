from tardis.interfaces.siteadapter import SiteAdapter
from tardis.utilities.attributedict import AttributeDict

from cobald.utility.primitives import infinity as inf
from unittest import TestCase
from unittest.mock import patch
from pydantic.error_wrappers import ValidationError

import asyncio
import logging


class TestSiteAdapter(TestCase):
    mock_config_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()

    @patch.multiple(SiteAdapter, __abstractmethods__=set())
    def setUp(self) -> None:
        self.config = self.mock_config.return_value
        self.config.Sites = [
            AttributeDict(name="TestSite", adapter="TestSite", quota=1)
        ]
        self.config.TestSite = AttributeDict(
            MachineTypes=["TestMachineType"],
            MachineMetaData=AttributeDict(
                TestMachineType=AttributeDict(Cores=128, Memory=512, Disk=100)
            ),
            MachineTypeConfiguration=AttributeDict(
                TestMachineType=AttributeDict(test_id="abc123")
            ),
        )
        self.site_adapter = SiteAdapter()
        self.site_adapter._site_name = "TestSite"
        self.site_adapter._machine_type = "TestMachineType"

    def test_configuration(self):
        self.assertEqual(self.site_adapter.configuration, self.config.TestSite)

    def test_deploy_resource(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.site_adapter.deploy_resource(dict()))

    def test_drone_environment(self):
        self.site_adapter._machine_type = "TestMachineType"

        self.assertEqual(
            AttributeDict(Cores=128, Memory=524288, Disk=104857600, Uuid="test-123"),
            self.site_adapter.drone_environment(
                drone_uuid="test-123",
                meta_data_translation_mapping=AttributeDict(
                    Cores=1,
                    Memory=1024,
                    Disk=1024 * 1024,
                ),
            ),
        )

        with (
            self.assertLogs(
                logger="cobald.runtime.tardis.utilities.utils", level=logging.CRITICAL
            ),
            self.assertRaises(KeyError),
        ):
            self.site_adapter.drone_environment(
                drone_uuid="test-123",
                meta_data_translation_mapping=AttributeDict(
                    Memory=1024,
                    Disk=1024 * 1024,
                ),
            )

    def test_drone_heartbeat_interval(self):
        self.assertEqual(self.site_adapter.drone_heartbeat_interval, 60)

        # lru_cache needs to be cleared before manipulating site configuration
        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        self.config.Sites[0]["drone_heartbeat_interval"] = 10
        self.assertEqual(self.site_adapter.drone_heartbeat_interval, 10)

        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        self.config.Sites[0]["drone_heartbeat_interval"] = -1
        with self.assertRaises(ValidationError):
            # noinspection PyStatementEffect
            self.site_adapter.drone_heartbeat_interval

    def test_drone_minimum_lifetime(self):
        self.assertEqual(self.site_adapter.drone_minimum_lifetime, None)

        # lru_cache needs to be cleared before manipulating site configuration
        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        self.config.Sites[0]["drone_minimum_lifetime"] = 10
        self.assertEqual(self.site_adapter.drone_minimum_lifetime, 10)

        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        self.config.Sites[0]["drone_minimum_lifetime"] = -1
        with self.assertRaises(ValidationError):
            # noinspection PyStatementEffect
            self.site_adapter.drone_minimum_lifetime

    def test_drone_uuid(self):
        self.assertEqual(
            "testsite-test123", self.site_adapter.drone_uuid(uuid="test123")
        )

    def test_handle_exception(self):
        with self.assertRaises(NotImplementedError):
            self.site_adapter.handle_exceptions()

    def test_handle_response_matching(self):
        test_response = {"test": 123}
        test_key_translator = {"new_test": "test"}
        test_translator_functions = {"test": str}

        self.assertEqual(
            self.site_adapter.handle_response(
                test_response, test_key_translator, test_translator_functions
            ),
            AttributeDict(new_test="123"),
        )

        self.assertEqual(
            self.site_adapter.handle_response(
                test_response,
                test_key_translator,
                test_translator_functions,
                additional="test123",
            ),
            AttributeDict(new_test="123", additional="test123"),
        )

    def test_handle_response_non_matching(self):
        test_response = {"other_test": 123}
        test_key_translator = {"new_test": "test"}
        test_translator_functions = {"test": str}

        self.assertEqual(
            self.site_adapter.handle_response(
                test_response, test_key_translator, test_translator_functions
            ),
            AttributeDict(),
        )

        self.assertEqual(
            self.site_adapter.handle_response(
                test_response,
                test_key_translator,
                test_translator_functions,
                additional="test123",
            ),
            AttributeDict(additional="test123"),
        )

    def test_machine_meta_data(self):
        self.assertEqual(
            self.site_adapter.machine_meta_data,
            AttributeDict(Cores=128, Memory=512, Disk=100),
        )

        # noinspection PyUnresolvedReferences
        del self.site_adapter._machine_type

        with self.assertRaises(AttributeError):
            # noinspection PyStatementEffect
            self.site_adapter.machine_meta_data

    def test_machine_type(self):
        self.assertEqual(self.site_adapter.machine_type, "TestMachineType")

        # noinspection PyUnresolvedReferences
        del self.site_adapter._machine_type

        with self.assertRaises(AttributeError):
            # noinspection PyStatementEffect
            self.site_adapter.machine_type

    def test_machine_type_configuration(self):
        self.assertEqual(
            self.site_adapter.machine_type_configuration,
            AttributeDict(test_id="abc123"),
        )

        # noinspection PyUnresolvedReferences
        del self.site_adapter._machine_type

        with self.assertRaises(AttributeError):
            # noinspection PyStatementEffect
            self.site_adapter.machine_type_configuration

    def test_resource_status(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.site_adapter.resource_status(dict()))

    def test_site_configuration(self):
        self.assertEqual(
            self.site_adapter.site_configuration,
            AttributeDict(
                name="TestSite",
                adapter="TestSite",
                quota=1,
                drone_minimum_lifetime=None,
                drone_heartbeat_interval=60,
            ),
        )

        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        del self.config.Sites[0]["quota"]

        self.assertEqual(
            self.site_adapter.site_configuration,
            AttributeDict(
                name="TestSite",
                adapter="TestSite",
                quota=inf,
                drone_minimum_lifetime=None,
                drone_heartbeat_interval=60,
            ),
        )

        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        self.config.Sites[0]["extra"] = "Should fail!"

        with self.assertRaises(ValidationError):
            self.assertEqual(
                self.site_adapter.site_configuration,
                AttributeDict(
                    name="TestSite",
                    adapter="TestSite",
                    quota=inf,
                    drone_minimum_lifetime=None,
                    drone_heartbeat_interval=60,
                ),
            )

        # noinspection PyUnresolvedReferences
        SiteAdapter.site_configuration.fget.cache_clear()

        self.config.Sites[0]["quota"] = 0

        with self.assertRaises(ValidationError):
            # noinspection PyStatementEffect
            self.site_adapter.site_configuration

    def test_site_name(self):
        self.assertEqual(self.site_adapter.site_name, "TestSite")
        del self.site_adapter._site_name

        with self.assertRaises(AttributeError):
            # noinspection PyStatementEffect
            self.site_adapter.site_name

    def test_stop_resource(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.site_adapter.stop_resource(dict()))

    def test_terminate_resource(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.site_adapter.terminate_resource(dict()))
