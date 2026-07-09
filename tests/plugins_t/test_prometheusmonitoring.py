from tardis.plugins.prometheusmonitoring import PrometheusMonitoring
from tardis.resources.dronestates import RequestState
from tardis.utilities.attributedict import AttributeDict
from tardis.interfaces.siteadapter import ResourceStatus

from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

from tests.utilities.utilities import get_free_port

import asyncio


class TestPrometheusMonitoring(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch(
            "tardis.plugins.prometheusmonitoring.Configuration"
        )
        cls.mock_config = cls.mock_config_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()

    @patch("tardis.plugins.prometheusmonitoring.logging", Mock())
    def setUp(self):
        ip = "127.0.0.1"
        self.config = self.mock_config.return_value
        self.config.Plugins.PrometheusMonitoring.addr = ip
        self.config.Plugins.PrometheusMonitoring.port = get_free_port(ip)

        self.plugin = PrometheusMonitoring()

    @patch("tardis.plugins.prometheusmonitoring.logging", Mock())
    def test_notify(self):
        test_state = RequestState()

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("6", ResourceStatus.Booting))
        )
        self.assert_gauges([1, 0, 0, 0, 0])

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("6", ResourceStatus.Running))
        )
        self.assert_gauges([0, 1, 0, 0, 0])

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("6", ResourceStatus.Stopped))
        )
        self.assert_gauges([0, 0, 1, 0, 0])

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("6", ResourceStatus.Deleted))
        )
        self.assert_gauges([0, 0, 0, 1, 0])

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("7", ResourceStatus.Error))
        )
        self.assert_gauges([0, 0, 0, 1, 1])

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("9", ResourceStatus.Booting))
        )
        self.assert_gauges([1, 0, 0, 1, 1])

        asyncio.run(
            self.plugin.notify(test_state, get_test_param("8", ResourceStatus.Error))
        )
        self.assert_gauges([1, 0, 0, 1, 2])

    def assert_gauges(self, values):
        assert all(
            [
                gauge.get({}) == result
                for (gauge, result) in zip(  # noqa B905
                    self.plugin._gauges.values(), values
                )
            ]
        )


def get_test_param(drone_uuid, resource_status):
    return AttributeDict(
        site_name="test-site",
        machine_type="test_machine_type",
        created=datetime.now(),
        updated=datetime.now(),
        drone_uuid=drone_uuid,
        resource_status=resource_status,
    )
