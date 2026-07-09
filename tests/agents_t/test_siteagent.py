from tardis.agents.siteagent import SiteAgent
from tardis.interfaces.siteadapter import SiteAdapter

from unittest import TestCase
from unittest.mock import create_autospec, PropertyMock, AsyncMock

import asyncio


class TestSiteAgent(TestCase):
    def setUp(self):
        self.site_adapter = create_autospec(SiteAdapter)
        self.site_agent = SiteAgent(self.site_adapter)

    def test_deploy_resource(self):
        self.site_adapter.deploy_resource = AsyncMock()
        asyncio.run(self.site_agent.deploy_resource(resource_attributes="test"))
        self.site_adapter.deploy_resource.assert_called_with(resource_attributes="test")

    def test_drone_uuid(self):
        self.site_adapter.drone_uuid.return_value = None
        self.site_agent.drone_uuid(uuid="test")
        self.site_adapter.drone_uuid.assert_called_with(uuid="test")

    def test_drone_heartbeat_interval(self):
        self.site_adapter.drone_heartbeat_interval.return_value = 60
        self.assertEqual(self.site_agent.drone_heartbeat_interval(), 60)
        self.site_adapter.drone_heartbeat_interval.assert_called_with()

    def test_drone_minimum_lifetime(self):
        self.site_adapter.drone_minimum_lifetime.return_value = None
        self.assertIsNone(self.site_agent.drone_minimum_lifetime())
        self.site_adapter.drone_minimum_lifetime.assert_called_with()

    def test_handle_exceptions(self):
        self.site_adapter.handle_exceptions.return_value = None
        self.site_agent.handle_exceptions()
        self.site_adapter.handle_exceptions.assert_called_with()

    def test_handle_response(self):
        self.assertEqual(
            self.site_agent.handle_response("Test", {"test": 1}, {"test": 2}),
            NotImplemented,
        )

    def test_machine_meta_data(self):
        type(self.site_adapter).machine_meta_data = PropertyMock(return_value="Test123")
        self.assertEqual(self.site_agent.machine_meta_data, "Test123")

    def test_machine_type(self):
        type(self.site_adapter).machine_type = PropertyMock(return_value="Test123")
        self.assertEqual(self.site_agent.machine_type, "Test123")

    def test_resource_status(self):
        self.site_adapter.resource_status = AsyncMock()
        asyncio.run(self.site_agent.resource_status(resource_attributes="test"))
        self.site_adapter.resource_status.assert_called_with(resource_attributes="test")

    def test_site_name(self):
        type(self.site_adapter).site_name = PropertyMock(return_value="Test123")
        self.assertEqual(self.site_agent.site_name, "Test123")

    def test_stop_resource(self):
        self.site_adapter.stop_resource = AsyncMock()
        asyncio.run(self.site_agent.stop_resource(resource_attributes="test"))
        self.site_adapter.stop_resource.assert_called_with(resource_attributes="test")

    def test_terminate_resource(self):
        self.site_adapter.terminate_resource = AsyncMock()
        asyncio.run(self.site_agent.terminate_resource(resource_attributes="test"))
        self.site_adapter.terminate_resource.assert_called_with(
            resource_attributes="test"
        )
