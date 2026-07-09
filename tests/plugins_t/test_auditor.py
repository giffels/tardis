from tardis.plugins.auditor import Auditor
from tardis.utilities.attributedict import AttributeDict
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.resources.dronestates import (
    AvailableState,
    DownState,
    BootingState,
    CleanupState,
    ShutDownState,
    ShuttingDownState,
    DrainState,
    DrainingState,
    IntegrateState,
    DisintegrateState,
)

from datetime import datetime
from unittest import TestCase
from unittest.mock import patch

from unittest.mock import AsyncMock

import asyncio


class TestAuditor(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.plugins.auditor.Configuration")
        cls.mock_auditorclientbuilder_patcher = patch(
            "tardis.plugins.auditor.pyauditor.AuditorClientBuilder"
        )

        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_auditorclientbuilder = cls.mock_auditorclientbuilder_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_auditorclientbuilder_patcher.stop()

    def setUp(self):
        self.address = "127.0.0.1"
        self.port = 8000
        self.timeout = 20
        self.user = "user-1"
        self.group = "group-1"
        self.site = "testsite"
        self.cores = 12
        self.memory = 100
        self.drone_uuid = "test-drone"
        self.machine_type = "test_machine_type"
        self.use_tls = True
        self.ca_cert_path = "/path/to/ca.crt"
        self.client_cert_path = "/path/to/client.crt"
        self.client_key_path = "/path/to/client.key"
        config = self.mock_config.return_value
        config.Plugins.Auditor = AttributeDict(
            host=self.address,
            port=self.port,
            timeout=self.timeout,
            user=self.user,
            group=self.group,
            components=AttributeDict(
                test_machine_type=AttributeDict(
                    Cores=AttributeDict(HEPSPEC=1.2, BENCHMARK=3.0),
                    Memory=AttributeDict(BLUBB=1.4),
                )
            ),
            tls_config=AttributeDict(
                use_tls=self.use_tls,
                ca_cert_path=self.ca_cert_path,
                client_cert_path=self.client_cert_path,
                client_key_path=self.client_key_path,
            ),
        )
        config.Sites = [AttributeDict(name=self.site)]
        config.testsite.MachineTypes = [self.machine_type]
        config.testsite.MachineMetaData = AttributeDict(
            test_machine_type=AttributeDict(Cores=self.cores, Memory=self.memory)
        )

        self.test_param = AttributeDict(
            site_name=self.site,
            machine_type=self.machine_type,
            created=datetime.now(),
            updated=datetime.now(),
            resource_status=ResourceStatus.Booting,
            drone_uuid=self.drone_uuid,
        )

        self.mock_builder = self.mock_auditorclientbuilder.return_value
        self.mock_address = self.mock_builder.address.return_value
        self.mock_timeout = self.mock_address.timeout.return_value
        self.client = self.mock_timeout.build.return_value
        self.client.add = AsyncMock()
        self.client.update = AsyncMock()

        self.config = config
        self.plugin = Auditor()
        self.plugin._client = self.client

    def test_default_fields(self):
        # Potential future race condition ahead.
        # Since this is the only test modifying self.config, this is
        # fine. However, when adding further tests care must be taken
        # when config changes are involved.
        del self.config.Plugins.Auditor.user
        del self.config.Plugins.Auditor.group
        # Needed in order to reload config.
        plugin = Auditor()
        self.assertEqual(plugin._user, "tardis")
        self.assertEqual(plugin._group, "tardis")

    def test_tls_configuration(self):
        tls_config = self.config.Plugins.Auditor.tls_config

        self.assertTrue(tls_config.use_tls, "TLS should be enabled")

        self.assertIsNotNone(tls_config, "Client should be created")

    def test_missing_tls_config_raises_error(self):
        required_tls_paths = ("client_cert_path", "client_key_path", "ca_cert_path")

        self.config.Plugins.Auditor.tls_config.use_tls = True

        for path_key in required_tls_paths:
            original_value = getattr(self.config.Plugins.Auditor.tls_config, path_key)
            delattr(self.config.Plugins.Auditor.tls_config, path_key)

            with self.assertRaises(ValueError) as cm:
                Auditor()
            self.assertEqual(
                str(cm.exception), f"Missing TLS configuration: {path_key}"
            )

            setattr(self.config.Plugins.Auditor.tls_config, path_key, original_value)

    def test_client_build_without_tls(self):
        self.config.Plugins.Auditor.tls_config.use_tls = False

        self.mock_auditorclientbuilder.reset_mock()

        # Re-instantiate to set-up Auditor without TLS
        Auditor()

        # Check that with_tls was NEVER called
        self.mock_timeout.with_tls.assert_not_called()

        # Check that build was called directly w/o TLS
        self.mock_timeout.build.assert_called_once()

    @patch(
        "tardis.plugins.auditor.pyauditor.AuditorClientBuilder.build",
        new_callable=AsyncMock,
    )
    def test_notify(self, mock_build):
        self.mock_builder.address.assert_called_with(
            self.address,
            self.port,
        )
        self.mock_address.timeout.assert_called_with(
            self.timeout,
        )

        self.mock_timeout.with_tls.assert_called_with(
            self.client_cert_path, self.client_key_path, self.ca_cert_path
        )

        asyncio.run(
            self.plugin.notify(
                state=AvailableState(),
                resource_attributes=self.test_param,
            )
        )

        self.client.add.assert_called_once()
        self.client.update.assert_not_called()

        asyncio.run(
            self.plugin.notify(
                state=DownState(),
                resource_attributes=self.test_param,
            )
        )

        self.assertEqual(self.client.add.call_count, 1)
        self.assertEqual(self.client.update.call_count, 1)

        # test for no-op
        for state in [
            BootingState(),
            IntegrateState(),
            CleanupState(),
            ShutDownState(),
            ShuttingDownState(),
            DrainState(),
            DrainingState(),
            DisintegrateState(),
        ]:
            asyncio.run(
                self.plugin.notify(
                    state=state,
                    resource_attributes=self.test_param,
                )
            )
            self.assertEqual(self.client.add.call_count, 1)
            self.assertEqual(self.client.update.call_count, 1)

        # test exception handling
        self.client.update.side_effect = RuntimeError(
            "Reqwest Error: HTTP status client error (404 Not Found) "
            "for url (http://127.0.0.1:8000/update)"
        )
        asyncio.run(
            self.plugin.notify(
                state=DownState(),
                resource_attributes=self.test_param,
            )
        )

        self.client.update.side_effect = RuntimeError(
            "Reqwest Error: HTTP status client error (403 Forbidden) "
            "for url (http://127.0.0.1:8000/update)"
        )
        with self.assertRaises(RuntimeError):
            asyncio.run(
                self.plugin.notify(
                    state=DownState(),
                    resource_attributes=self.test_param,
                )
            )

        self.client.update.side_effect = RuntimeError("Does not match RegEx")
        with self.assertRaises(RuntimeError):
            asyncio.run(
                self.plugin.notify(
                    state=DownState(),
                    resource_attributes=self.test_param,
                )
            )

        self.client.update.side_effect = ValueError("Other exception")
        with self.assertRaises(ValueError):
            asyncio.run(
                self.plugin.notify(
                    state=DownState(),
                    resource_attributes=self.test_param,
                )
            )

        self.client.update.side_effect = None

    def test_construct_record(self):
        record = self.plugin.construct_record(resource_attributes=self.test_param)

        self.assertEqual(record.record_id, self.drone_uuid)
        self.assertEqual(record.meta.get("site_id"), [self.site])
        self.assertEqual(record.meta.get("user_id"), [self.user])
        self.assertEqual(record.meta.get("group_id"), [self.group])
        self.assertEqual(len(record.components), 2)
        self.assertEqual(record.components[0].name, "Cores")
        self.assertEqual(record.components[0].amount, 12)
        self.assertEqual(len(record.components[0].scores), 2)
        self.assertEqual(record.components[0].scores[0].name, "HEPSPEC")
        self.assertEqual(record.components[0].scores[0].value, 1.2)
        self.assertEqual(record.components[0].scores[1].name, "BENCHMARK")
        self.assertEqual(record.components[0].scores[1].value, 3.0)
        self.assertEqual(record.components[1].name, "Memory")
        self.assertEqual(record.components[1].amount, 100)
        self.assertEqual(len(record.components[1].scores), 1)
        self.assertEqual(record.components[1].scores[0].name, "BLUBB")
        self.assertEqual(record.components[1].scores[0].value, 1.4)

    def test_missing_components(self):
        del self.config.Plugins.Auditor.components
        plugin = Auditor()
        self.assertEqual(plugin._components, {"testsite": {"test_machine_type": {}}})
