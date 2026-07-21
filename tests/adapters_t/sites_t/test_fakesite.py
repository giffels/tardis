from tardis.adapters.sites.fakesite import FakeSiteAdapter
from tardis.exceptions.tardisexceptions import TardisError
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.utilities.attributedict import AttributeDict

from datetime import datetime
from datetime import timedelta
from unittest.mock import patch
from unittest import TestCase

import asyncio


class TestFakeSiteAdapter(TestCase):
    mock_config_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()

    def setUp(self):
        config = self.mock_config.return_value
        test_site_config = config.TestSite
        test_site_config.MachineMetaData = self.machine_meta_data
        test_site_config.MachineTypeConfiguration = self.machine_type_configuration
        test_site_config.api_response_delay = AttributeDict(get_value=lambda: 0)
        test_site_config.resource_boot_time = AttributeDict(get_value=lambda: 100)

        self.adapter = FakeSiteAdapter(machine_type="test2large", site_name="TestSite")

    @property
    def machine_meta_data(self):
        return AttributeDict(test2large=AttributeDict(Cores=8, Memory=32))

    @property
    def machine_type_configuration(self):
        return AttributeDict(test2large=AttributeDict(jdl="submit.jdl"))

    def test_deploy_resource(self):
        response = asyncio.run(self.adapter.deploy_resource(AttributeDict()))
        self.assertEqual(response.resource_status, ResourceStatus.Booting)

    def test_machine_meta_data(self):
        self.assertEqual(
            self.adapter.machine_meta_data, self.machine_meta_data.test2large
        )

    def test_machine_type(self):
        self.assertEqual(self.adapter.machine_type, "test2large")

    def test_site_name(self):
        self.assertEqual(self.adapter.site_name, "TestSite")

    def test_resource_status(self):
        # Booting resource, where boot time is not yet over
        resource_attributes = AttributeDict(
            created=datetime.now(),
            resource_status=ResourceStatus.Booting,
            drone_uuid="test-123",
        )
        self.assertEqual(
            AttributeDict(),  # no update require, resource still in Booting state
            asyncio.run(
                self.adapter.resource_status(
                    resource_attributes,
                )
            ),
        )

        # Booting resource, where boot time is already over
        created_timestamp = datetime.now() - timedelta(seconds=100)
        resource_attributes.update(AttributeDict(created=created_timestamp))

        self.assertDictEqual(
            AttributeDict(resource_status=ResourceStatus.Running),
            asyncio.run(self.adapter.resource_status(resource_attributes)),
        )

        # test resource status of stop resources
        resource_attributes.update(
            AttributeDict(resource_status=ResourceStatus.Stopped)
        )
        self.assertEqual(
            AttributeDict(),
            asyncio.run(self.adapter.resource_status(resource_attributes)),
        )
        self.assertDictEqual(
            AttributeDict(
                created=created_timestamp,
                resource_status=ResourceStatus.Stopped,
                drone_uuid="test-123",
            ),
            resource_attributes,
        )

        # test resource status of terminated resources
        resource_attributes.update(
            AttributeDict(resource_status=ResourceStatus.Deleted)
        )
        self.assertEqual(
            AttributeDict(),
            asyncio.run(self.adapter.resource_status(resource_attributes)),
        )
        self.assertDictEqual(
            AttributeDict(
                created=created_timestamp,
                resource_status=ResourceStatus.Deleted,
                drone_uuid="test-123",
            ),
            resource_attributes,
        )

    def test_stop_resource(self):
        resource_attributes = AttributeDict(
            drone_uuid="test-123",
            created=datetime.now(),
            resource_status=ResourceStatus.Running,
        )
        asyncio.run(self.adapter.stop_resource(resource_attributes))
        self.assertEqual(resource_attributes.resource_status, ResourceStatus.Stopped)

    def test_terminate_resource(self):
        resource_attributes = AttributeDict(
            drone_uuid="test-123",
            created=datetime.now(),
            resource_status=ResourceStatus.Running,
        )
        asyncio.run(self.adapter.terminate_resource(resource_attributes))
        self.assertEqual(resource_attributes.resource_status, ResourceStatus.Deleted)

    def test_exception_handling(self):
        def test_exception_handling(raise_it, catch_it):
            with self.assertRaises(catch_it):
                with self.adapter.handle_exceptions():
                    raise raise_it

        matrix = [(Exception, TardisError)]

        for to_raise, to_catch in matrix:
            test_exception_handling(to_raise, to_catch)
