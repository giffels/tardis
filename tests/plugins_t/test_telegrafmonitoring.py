from tardis.plugins.telegrafmonitoring import TelegrafMonitoring
from tardis.resources.dronestates import RequestState
from tardis.utilities.attributedict import AttributeDict

from datetime import datetime
from unittest import TestCase
from unittest.mock import AsyncMock, Mock
from unittest.mock import patch

import asyncio
import platform


class TestTelegrafMonitoring(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch(
            "tardis.plugins.telegrafmonitoring.Configuration"
        )
        cls.mock_aiotelegraf_patcher = patch(
            "tardis.plugins.telegrafmonitoring.aiotelegraf"
        )
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_aiotelegraf = cls.mock_aiotelegraf_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_aiotelegraf_patcher.stop()

    @patch("tardis.plugins.telegrafmonitoring.logging", Mock())
    def setUp(self):
        self.config = self.mock_config.return_value
        self.config.Plugins.TelegrafMonitoring.host = "telegraf.test"
        self.config.Plugins.TelegrafMonitoring.port = 1234
        self.config.Plugins.TelegrafMonitoring.default_tags = {"test_tag": "test"}
        self.config.Plugins.TelegrafMonitoring.metric = "tardis_data"

        telegraf_client = self.mock_aiotelegraf.Client.return_value
        telegraf_client.connect = AsyncMock()
        telegraf_client.close = AsyncMock()

        self.plugin = TelegrafMonitoring()

    @patch("tardis.plugins.telegrafmonitoring.logging", Mock())
    def test_notify(self):
        test_param = AttributeDict(
            site_name="test-site",
            machine_type="test_machine_type",
            drone_uuid="test_drone_uuid",
            created=datetime.now(),
            updated=datetime.now(),
        )
        test_state = RequestState()
        test_result = dict(state=str(test_state))
        test_result.update(
            created=datetime.timestamp(test_param.created),
            updated=datetime.timestamp(test_param.updated),
        )
        test_tags = dict(
            site_name=test_param.site_name,
            machine_type=test_param.machine_type,
            drone_uuid=test_param.drone_uuid,
        )
        asyncio.run(self.plugin.notify(test_state, test_param))
        self.mock_aiotelegraf.Client.assert_called_with(
            host="telegraf.test",
            port=1234,
            tags={"tardis_machine_name": platform.node(), "test_tag": "test"},
        )
        self.mock_aiotelegraf.Client.return_value.connect.assert_called_with()
        self.mock_aiotelegraf.Client.return_value.metric.assert_called_with(
            "tardis_data", test_result, tags=test_tags
        )
        self.mock_aiotelegraf.Client.return_value.close.assert_called_with()

        self.mock_aiotelegraf.reset()

        # Test to overwrite tardis_node_name in plugin configuration
        self.config.Plugins.TelegrafMonitoring.default_tags = {
            "test_tag": "test",
            "tardis_machine_name": "my_test_node",
        }
        self.plugin = TelegrafMonitoring()
        asyncio.run(self.plugin.notify(test_state, test_param))

        self.mock_aiotelegraf.Client.assert_called_with(
            host="telegraf.test",
            port=1234,
            tags={"tardis_machine_name": "my_test_node", "test_tag": "test"},
        )
        self.mock_aiotelegraf.Client.return_value.connect.assert_called_with()
        self.mock_aiotelegraf.Client.return_value.metric.assert_called_with(
            "tardis_data", test_result, tags=test_tags
        )
        self.mock_aiotelegraf.Client.return_value.close.assert_called_with()
