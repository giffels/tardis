from tardis.plugins.elasticsearchmonitoring import ElasticsearchMonitoring
from tardis.utilities.attributedict import AttributeDict
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.resources.dronestates import CleanupState

from datetime import datetime
from unittest import TestCase
from unittest.mock import patch

import asyncio


class TestElasticsearchMonitoring(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch(
            "tardis.plugins.elasticsearchmonitoring.Configuration"
        )
        cls.mock_elasticsearch_patcher = patch(
            "tardis.plugins.elasticsearchmonitoring.Elasticsearch"
        )
        cls.mock_datetime_patcher = patch(
            "tardis.plugins.elasticsearchmonitoring.datetime"
        )
        cls.mock_time_patcher = patch("tardis.plugins.elasticsearchmonitoring.time")
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_elasticsearch = cls.mock_elasticsearch_patcher.start()
        cls.mock_datetime = cls.mock_datetime_patcher.start()
        cls.mock_time = cls.mock_time_patcher.start()
        cls.mock_datetime.now.return_value.strftime.return_value = "20200630"
        cls.mock_time.return_value = 2

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_elasticsearch_patcher.stop()
        cls.mock_datetime_patcher.stop()
        cls.mock_time_patcher.stop()

    def setUp(self):
        self.config = self.mock_config.return_value
        self.config.Plugins.ElasticsearchMonitoring._index = "index"
        self.config.Plugins.ElasticsearchMonitoring._meta = "meta"

        self.plugin = ElasticsearchMonitoring()

    def test_notify(self):
        test_param = AttributeDict(
            site_name="test-site",
            machine_type="test_machine_type",
            created=datetime.now(),
            updated=datetime.now(),
            resource_status=ResourceStatus.Booting,
            drone_uuid="test-drone",
        )

        test_param_ext = {
            **test_param,
            "state": str(CleanupState()),
            "meta": self.plugin._meta,
            "timestamp": int(self.mock_time.return_value * 1000),
            "resource_status": str(test_param.resource_status),
            "revision": 2,
        }

        self.mock_elasticsearch.return_value.search.return_value = {
            "hits": {"total": {"value": 2}}
        }

        asyncio.run(
            self.plugin.notify(state=CleanupState(), resource_attributes=test_param)
        )

        self.mock_elasticsearch.return_value.search.assert_called_with(
            index=f"{self.plugin._index}*",
            body={"query": {"term": {"drone_uuid.keyword": test_param.drone_uuid}}},
        )
        self.mock_elasticsearch.return_value.create.assert_called_with(
            body=test_param_ext,
            id=f"{test_param.drone_uuid}-2",
            index=f"{self.plugin._index}-{self.mock_datetime.now.return_value.strftime.return_value}",  # noqa: B950
        )

    def test_notify_resource_status_missing(self):
        test_param = AttributeDict(
            site_name="test-site",
            machine_type="test_machine_type",
            created=datetime.now(),
            updated=datetime.now(),
            drone_uuid="test-drone",
        )

        test_param_ext = {
            **test_param,
            "state": str(CleanupState()),
            "meta": self.plugin._meta,
            "timestamp": int(self.mock_time.return_value * 1000),
            "resource_status": "",
            "revision": 2,
        }

        self.mock_elasticsearch.return_value.search.return_value = {
            "hits": {"total": {"value": 2}}
        }

        asyncio.run(
            self.plugin.notify(state=CleanupState(), resource_attributes=test_param)
        )

        self.mock_elasticsearch.return_value.search.assert_called_with(
            index=f"{self.plugin._index}*",
            body={"query": {"term": {"drone_uuid.keyword": test_param.drone_uuid}}},
        )
        self.mock_elasticsearch.return_value.create.assert_called_with(
            body=test_param_ext,
            id=f"{test_param.drone_uuid}-2",
            index=f"{self.plugin._index}-{self.mock_datetime.now.return_value.strftime.return_value}",  # noqa: B950
        )
