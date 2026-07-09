from tardis.adapters.sites.cloudstack import CloudStackAdapter
from tardis.utilities.attributedict import AttributeDict
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.exceptions.tardisexceptions import TardisTimeout
from tardis.exceptions.tardisexceptions import TardisError
from tardis.exceptions.tardisexceptions import TardisQuotaExceeded
from tardis.exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from CloudStackAIO.CloudStack import CloudStackClientException

from aiohttp import ClientConnectionError
from unittest import TestCase
from unittest.mock import patch, AsyncMock

import asyncio
import logging


class TestCloudStackAdapter(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_cloudstack_api_patcher = patch(
            "tardis.adapters.sites.cloudstack.CloudStack"
        )
        cls.mock_cloudstack_api = cls.mock_cloudstack_api_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_cloudstack_api_patcher.stop()

    def setUp(self):
        config = self.mock_config.return_value
        test_site_config = config.TestSite
        test_site_config.end_point = "https://test.cloudstack.local/compute"
        test_site_config.api_key = "1234567890abcdef"
        test_site_config.api_secret = "fedcba0987654321"
        test_site_config.MachineTypeConfiguration = AttributeDict(
            test2large=AttributeDict(
                templateid="1b0b9253-929e-4865-874b-7d2c3491987b",
                serviceofferingid="74bfaf4e-7d67-4adf-9322-12b9a36e84f7",
                zoneid="35eb7739-d19e-45f7-a581-4687c54d6d02",
                keypair="MG",
                rootdisksize=500,
            )
        )

        test_site_config.MachineMetaData = AttributeDict(
            test2large=AttributeDict(Cores=128)
        )

        cloudstack_api = self.mock_cloudstack_api.return_value
        self.deploy_return_value = AttributeDict(
            virtualmachine=AttributeDict(
                name="testsite-089123", id="123456", state="Present"
            )
        )
        cloudstack_api.deployVirtualMachine = AsyncMock(
            return_value=self.deploy_return_value
        )
        self.list_vm_return_value = AttributeDict(
            virtualmachine=[
                AttributeDict(name="testsite-089123", id="123456", state="Running")
            ]
        )
        cloudstack_api.listVirtualMachines = AsyncMock(
            return_value=self.list_vm_return_value
        )

        cloudstack_api.stopVirtualMachine = AsyncMock(return_value=None)

        cloudstack_api.destroyVirtualMachine = AsyncMock(return_value=None)

        self.cloudstack_adapter = CloudStackAdapter(
            machine_type="test2large", site_name="TestSite"
        )

    def tearDown(self):
        self.mock_cloudstack_api.reset_mock()

    def test_deploy_resource(self):
        self.assertEqual(
            asyncio.run(
                self.cloudstack_adapter.deploy_resource(
                    resource_attributes=AttributeDict(drone_uuid="testsite-089123"),
                )
            ),
            AttributeDict(
                drone_uuid="testsite-089123",
                remote_resource_uuid="123456",
                resource_status=ResourceStatus.Booting,
            ),
        )

        self.mock_cloudstack_api.return_value.deployVirtualMachine.assert_called_with(
            name="testsite-089123",
            templateid="1b0b9253-929e-4865-874b-7d2c3491987b",
            serviceofferingid="74bfaf4e-7d67-4adf-9322-12b9a36e84f7",
            zoneid="35eb7739-d19e-45f7-a581-4687c54d6d02",
            keypair="MG",
            rootdisksize=500,
        )

    def test_machine_meta_data(self):
        self.assertEqual(
            self.cloudstack_adapter.machine_meta_data, AttributeDict(Cores=128)
        )

    def test_machine_type(self):
        self.assertEqual(self.cloudstack_adapter.machine_type, "test2large")

    def test_site_name(self):
        self.assertEqual(self.cloudstack_adapter.site_name, "TestSite")

    def test_resource_status(self):
        self.assertEqual(
            asyncio.run(
                self.cloudstack_adapter.resource_status(
                    resource_attributes=AttributeDict(remote_resource_uuid="123456")
                ),
            ),
            AttributeDict(
                drone_uuid="testsite-089123",
                remote_resource_uuid="123456",
                resource_status=ResourceStatus.Running,
            ),
        )
        self.mock_cloudstack_api.return_value.listVirtualMachines.assert_called_with(
            id="123456"
        )

    def test_stop_resource(self):
        asyncio.run(
            self.cloudstack_adapter.stop_resource(
                resource_attributes=AttributeDict(remote_resource_uuid="123456")
            ),
        )

        self.mock_cloudstack_api.return_value.stopVirtualMachine.assert_called_with(
            id="123456"
        )

    def test_terminate_resource(self):
        asyncio.run(
            self.cloudstack_adapter.terminate_resource(
                resource_attributes=AttributeDict(remote_resource_uuid="123456")
            ),
        )

        self.mock_cloudstack_api.return_value.destroyVirtualMachine.assert_called_with(
            id="123456"
        )

    def test_exception_handling(self):
        def test_exception_handling(to_raise, to_catch):
            with self.assertRaises(to_catch):
                with self.assertLogs(level=logging.WARNING):
                    with self.cloudstack_adapter.handle_exceptions():
                        raise to_raise

        matrix = [
            (
                CloudStackClientException(
                    message="Quota Exceeded",
                    error_code=535,
                    error_text="Quota Exceeded",
                ),
                TardisQuotaExceeded,
            ),
            (asyncio.TimeoutError(), TardisTimeout),
            (ClientConnectionError(), TardisResourceStatusUpdateFailed),
            (
                CloudStackClientException(
                    message="Timeout",
                    error_code=500,
                    response={"message": "timed out after 1000.0 ms"},
                ),
                TardisTimeout,
            ),
            (
                CloudStackClientException(
                    message="Timeout",
                    error_code=500,
                    response={"message": "connection was closed"},
                ),
                TardisResourceStatusUpdateFailed,
            ),
            (
                CloudStackClientException(
                    message="Something else",
                    error_code=500,
                    response={"message": "Something else"},
                ),
                TardisError,
            ),
            (
                CloudStackClientException(
                    message="Something Else",
                    error_code=666,
                    error_text="Something Else",
                ),
                TardisError,
            ),
        ]

        for to_raise, to_catch in matrix:
            test_exception_handling(to_raise, to_catch)
