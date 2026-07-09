from tardis.adapters.sites.openstack import OpenStackAdapter
from tardis.exceptions.tardisexceptions import TardisAuthError
from tardis.exceptions.tardisexceptions import TardisDroneCrashed
from tardis.exceptions.tardisexceptions import TardisError
from tardis.exceptions.tardisexceptions import TardisTimeout
from tardis.exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from tardis.utilities.attributedict import AttributeDict
from tardis.interfaces.siteadapter import ResourceStatus

from aiohttp import ClientConnectionError
from aiohttp import ContentTypeError
from simple_rest_client.exceptions import AuthError
from simple_rest_client.exceptions import ClientError

from unittest import TestCase
from unittest.mock import patch, AsyncMock

import asyncio
import logging


class TestOpenStackAdapter(TestCase):
    mock_config_patcher = None
    mock_openstack_api_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_openstack_api_patcher = patch(
            "tardis.adapters.sites.openstack.NovaClient"
        )
        cls.mock_openstack_api = cls.mock_openstack_api_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_openstack_api_patcher.stop()

    def setUp(self):
        self.config = self.mock_config.return_value
        self.config.TestSite = AttributeDict(
            auth_url="https://test.nova.client.local",
            username="TestUser",
            password="test123",
            project_name="TestProject",
            user_domain_name="TestDomain",
            project_domain_name="TestProjectDomain",
            MachineTypes=["test2large"],
            MachineTypeConfiguration=AttributeDict(
                test2large=AttributeDict(
                    imageRef="bc613271-6a54-48ca-9222-47e009dc0c29"
                )
            ),
            MachineMetaData=AttributeDict(
                test2large=AttributeDict(Cores=128, Memory=256, Disk=1000)
            ),
        )

        openstack_api = self.mock_openstack_api.return_value
        openstack_api.init_api = AsyncMock(return_value=None)

        self.create_return_value = AttributeDict(
            server=AttributeDict(name="testsite-089123")
        )
        openstack_api.servers.create = AsyncMock(return_value=self.create_return_value)

        self.get_return_value = AttributeDict(
            server=AttributeDict(
                name="testsite-089123",
                id="029312-1231-123123",
                status="ACTIVE",
                created="2023-07-31T12:46:24Z",
                updated="2023-07-31T12:46:50Z",
            )
        )
        openstack_api.servers.get = AsyncMock(return_value=self.get_return_value)

        openstack_api.servers.run_action = AsyncMock(return_value=None)

        openstack_api.servers.force_delete = AsyncMock(return_value=None)

        self.mock_openstack_api.return_value.init_api = AsyncMock(return_value=True)
        self.openstack_adapter = OpenStackAdapter(
            machine_type="test2large", site_name="TestSite"
        )

    def tearDown(self):
        self.mock_openstack_api.reset_mock()

    def test_auth_setup(self):
        # test auth with username, password, etc.
        OpenStackAdapter(machine_type="test2large", site_name="TestSite")

        for key in (
            "username",
            "password",
            "project_name",
            "user_domain_name",
            "project_domain_name",
        ):
            delattr(self.config.TestSite, key)

        self.config.TestSite["application_credential_id"] = "TestAppId"
        self.config.TestSite["application_credential_secret"] = "TestAppSecret"
        # test auth with application credentials
        OpenStackAdapter(machine_type="test2large", site_name="TestSite")

    def test_deploy_resource(self):
        self.assertEqual(
            asyncio.run(
                self.openstack_adapter.deploy_resource(
                    resource_attributes=AttributeDict(drone_uuid="testsite-089123"),
                )
            ),
            AttributeDict(drone_uuid="testsite-089123"),
        )

        self.mock_openstack_api.return_value.init_api.assert_called_with(timeout=60)

        self.mock_openstack_api.return_value.servers.create.assert_called_with(
            server={
                "imageRef": "bc613271-6a54-48ca-9222-47e009dc0c29",
                "name": "testsite-089123",
            }
        )

    def test_machine_meta_data(self):
        self.assertEqual(
            self.openstack_adapter.machine_meta_data,
            AttributeDict(Cores=128, Disk=1000, Memory=256),
        )

    def test_machine_type(self):
        self.assertEqual(self.openstack_adapter.machine_type, "test2large")

    def test_site_name(self):
        self.assertEqual(self.openstack_adapter.site_name, "TestSite")

    def test_resource_status(self):
        self.assertEqual(
            asyncio.run(
                self.openstack_adapter.resource_status(
                    resource_attributes=AttributeDict(
                        drone_uuid="testsite-089123",
                        remote_resource_uuid="029312-1231-123123",
                        resource_status=ResourceStatus.Booting,
                    )
                ),
            ),
            AttributeDict(
                drone_uuid="testsite-089123",
                remote_resource_uuid="029312-1231-123123",
                resource_status=ResourceStatus.Running,
            ),
        )
        self.mock_openstack_api.return_value.init_api.assert_called_with(timeout=60)
        self.mock_openstack_api.return_value.servers.get.assert_called_with(
            "029312-1231-123123"
        )

    def test_stop_resource(self):
        asyncio.run(
            self.openstack_adapter.stop_resource(
                resource_attributes=AttributeDict(
                    remote_resource_uuid="029312-1231-123123"
                )
            )
        )
        params = {"os-stop": None}
        self.mock_openstack_api.return_value.init_api.assert_called_with(timeout=60)
        self.mock_openstack_api.return_value.servers.run_action.assert_called_with(
            "029312-1231-123123", **params
        )

    def test_terminate_resource(self):
        asyncio.run(
            self.openstack_adapter.terminate_resource(
                resource_attributes=AttributeDict(
                    remote_resource_uuid="029312-1231-123123"
                )
            )
        )

        self.mock_openstack_api.return_value.init_api.assert_called_with(timeout=60)
        self.mock_openstack_api.return_value.servers.force_delete.assert_called_with(
            "029312-1231-123123"
        )

    def test_exception_handling(self):
        def test_exception_handling(to_raise, to_catch):
            with self.assertRaises(to_catch):
                with self.assertLogs(level=logging.WARNING):
                    with self.openstack_adapter.handle_exceptions():
                        raise to_raise

        matrix = [
            (asyncio.TimeoutError(), TardisTimeout),
            (AuthError(message="Test_Error", response="Not Allowed"), TardisAuthError),
            (
                ContentTypeError(
                    request_info=AttributeDict(real_url="Test"), history="Test"
                ),
                TardisResourceStatusUpdateFailed,
            ),
            (
                ClientError(message="Test_Error", response="Internal Server Error"),
                TardisDroneCrashed,
            ),
            (ClientConnectionError(), TardisResourceStatusUpdateFailed),
            (Exception, TardisError),
        ]

        for to_raise, to_catch in matrix:
            test_exception_handling(to_raise, to_catch)
