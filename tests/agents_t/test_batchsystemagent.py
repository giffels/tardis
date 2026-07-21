from tardis.agents.batchsystemagent import BatchSystemAgent
from tardis.interfaces.batchsystemadapter import BatchSystemAdapter
from tardis.utilities.attributedict import AttributeDict

from unittest import TestCase
from unittest.mock import create_autospec, AsyncMock, PropertyMock

import asyncio


class TestBatchSystemAgent(TestCase):
    def setUp(self):
        self.batch_system_adapter = create_autospec(BatchSystemAdapter)
        self.batch_system_agent = BatchSystemAgent(self.batch_system_adapter)

    def test_disintegrate_machine(self):
        self.batch_system_adapter.disintegrate_machine = AsyncMock()
        asyncio.run(self.batch_system_agent.disintegrate_machine(drone_uuid="test"))
        self.batch_system_adapter.disintegrate_machine.assert_called_with("test")

    def test_drain_machine(self):
        self.batch_system_adapter.drain_machine = AsyncMock()
        asyncio.run(self.batch_system_agent.drain_machine(drone_uuid="test"))
        self.batch_system_adapter.drain_machine.assert_called_with("test")

    def test_integrate_machine(self):
        self.batch_system_adapter.integrate_machine = AsyncMock()
        asyncio.run(self.batch_system_agent.integrate_machine(drone_uuid="test"))
        self.batch_system_adapter.integrate_machine.assert_called_with("test")

    def test_get_allocation(self):
        self.batch_system_adapter.get_allocation = AsyncMock()
        asyncio.run(self.batch_system_agent.get_allocation(drone_uuid="test"))
        self.batch_system_adapter.get_allocation.assert_called_with("test")

    def test_get_machine_status(self):
        self.batch_system_adapter.get_machine_status = AsyncMock()
        asyncio.run(self.batch_system_agent.get_machine_status(drone_uuid="test"))
        self.batch_system_adapter.get_machine_status.assert_called_with("test")

    def test_get_utilisation(self):
        self.batch_system_adapter.get_utilisation = AsyncMock()
        asyncio.run(self.batch_system_agent.get_utilisation(drone_uuid="test"))
        self.batch_system_adapter.get_utilisation.assert_called_with("test")

    def test_machine_meta_data_translation_mapping(self):
        machine_meta_data_translation_mock = PropertyMock(
            return_value=AttributeDict(Cores=1, Memory=1024, Disk=1024)
        )

        type(self.batch_system_adapter).machine_meta_data_translation_mapping = (
            machine_meta_data_translation_mock
        )

        self.assertEqual(
            AttributeDict(Cores=1, Memory=1024, Disk=1024),
            self.batch_system_agent.machine_meta_data_translation_mapping,
        )

        machine_meta_data_translation_mock.assert_called_once_with()
