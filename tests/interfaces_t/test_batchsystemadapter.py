from tardis.interfaces.batchsystemadapter import BatchSystemAdapter

from unittest import TestCase
from unittest.mock import patch

import asyncio


class TestBatchSystemAdapter(TestCase):
    @patch.multiple(BatchSystemAdapter, __abstractmethods__=set())
    def setUp(self) -> None:
        self.batch_system_adapter = BatchSystemAdapter()

    def test_disintegrate_machine(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.batch_system_adapter.disintegrate_machine("test-123"))

    def test_drain_machine(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.batch_system_adapter.drain_machine("test-123"))

    def test_integrate_machine(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.batch_system_adapter.integrate_machine("test-123"))

    def test_get_allocation(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.batch_system_adapter.get_allocation("test-123"))

    def test_get_machine_status(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.batch_system_adapter.get_machine_status("test-123"))

    def test_get_utilisation(self):
        with self.assertRaises(NotImplementedError):
            asyncio.run(self.batch_system_adapter.get_utilisation("test-123"))

    def test_machine_meta_data_translation_mapping(self):
        with self.assertRaises(NotImplementedError):
            self.batch_system_adapter.machine_meta_data_translation_mapping
