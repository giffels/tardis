from tardis.exceptions.tardisexceptions import TardisAuthError
from tardis.exceptions.tardisexceptions import TardisDroneCrashed
from tardis.exceptions.tardisexceptions import TardisTimeout
from tardis.exceptions.tardisexceptions import TardisQuotaExceeded
from tardis.exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from tardis.exceptions.tardisexceptions import TardisUnknownStateTransition
from tardis.interfaces.batchsystemadapter import MachineStatus
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.resources.dronestates import check_minimum_lifetime
from tardis.resources.dronestates import RequestState
from tardis.resources.dronestates import BootingState
from tardis.resources.dronestates import IntegrateState
from tardis.resources.dronestates import IntegratingState
from tardis.resources.dronestates import AvailableState
from tardis.resources.dronestates import DrainState
from tardis.resources.dronestates import DrainingState
from tardis.resources.dronestates import DisintegrateState
from tardis.resources.dronestates import ShutDownState
from tardis.resources.dronestates import ShuttingDownState
from tardis.resources.dronestates import CleanupState
from tardis.resources.dronestates import DownState
from tardis.utilities.attributedict import AttributeDict

from functools import partial
from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import patch, AsyncMock

import asyncio
import logging


class TestDroneStates(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_drone_patcher = patch("tardis.resources.drone.Drone")
        cls.mock_drone = cls.mock_drone_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_drone_patcher.stop()

    def setUp(self):
        async def mock_set_state(drone, state):
            drone.state = state
            f = asyncio.Future()
            f.set_result(None)
            return f

        self.drone = self.mock_drone.return_value
        self.drone.resource_attributes = AttributeDict(
            drone_uuid="test-923ABF",
            remote_resource_uuid="0815",
            updated=datetime.now() - timedelta(minutes=10),
        )
        self.drone.demand = 8.0
        self.drone._supply = 8.0
        self.drone.minimum_lifetime = 3600
        self.drone.set_state.side_effect = partial(mock_set_state, self.drone)
        self.drone.site_agent.deploy_resource = AsyncMock(return_value=AttributeDict())
        self.drone.site_agent.resource_status = AsyncMock(return_value=AttributeDict())
        self.drone.site_agent.stop_resource = AsyncMock(return_value=AttributeDict())
        self.drone.site_agent.terminate_resource = AsyncMock(
            return_value=AttributeDict()
        )
        self.drone.batch_system_agent.integrate_machine = AsyncMock(return_value=None)
        self.drone.batch_system_agent.disintegrate_machine = AsyncMock(
            return_value=None
        )
        self.drone.batch_system_agent.drain_machine = AsyncMock(return_value=None)
        self.drone.batch_system_agent.get_machine_status = AsyncMock(return_value=None)
        self.drone.batch_system_agent.get_allocation = AsyncMock(return_value=None)
        self.drone.batch_system_agent.get_utilisation = AsyncMock(return_value=None)

    def run_the_matrix(self, matrix, initial_state):
        for resource_status, machine_status, new_state in matrix:
            self.drone.site_agent.resource_status = AsyncMock(
                return_value=AttributeDict(resource_status=resource_status)
            )
            self.drone.batch_system_agent.get_machine_status = AsyncMock(
                return_value=machine_status
            )
            self.drone.state.return_value = initial_state
            with self.assertLogs(None, level="DEBUG"):
                asyncio.run(self.drone.state.return_value.run(self.drone))
            self.assertIsInstance(self.drone.state, new_state)

    def run_side_effects(
        self, initial_state, api_call_to_test, exceptions, final_state
    ):
        for exception in exceptions:
            self.drone.state.return_value = initial_state
            api_call_to_test.side_effect = exception()
            asyncio.run(self.drone.state.return_value.run(self.drone))
            self.assertIsInstance(self.drone.state, final_state)

        api_call_to_test.side_effect = None

    def test_request_state(self):
        self.drone.state.return_value = RequestState()
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, BootingState)

        self.run_side_effects(
            RequestState(),
            self.drone.site_agent.deploy_resource,
            (
                TardisAuthError,
                TardisTimeout,
                TardisQuotaExceeded,
                TardisResourceStatusUpdateFailed,
            ),
            DownState,
        )

        self.run_side_effects(
            RequestState(),
            self.drone.site_agent.deploy_resource,
            (TardisDroneCrashed,),
            CleanupState,
        )

    def test_booting_state(self):
        matrix = [
            (ResourceStatus.Booting, None, BootingState),
            (ResourceStatus.Running, None, IntegrateState),
            (ResourceStatus.Deleted, None, DownState),
            (ResourceStatus.Stopped, None, CleanupState),
            (ResourceStatus.Error, None, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=BootingState)

        self.run_side_effects(
            BootingState(),
            self.drone.site_agent.resource_status,
            (TardisAuthError, TardisTimeout, TardisResourceStatusUpdateFailed),
            BootingState,
        )

        self.run_side_effects(
            BootingState(),
            self.drone.site_agent.resource_status,
            (TardisDroneCrashed,),
            CleanupState,
        )

        # Test draining procedure if cobald sets drone demand to zero
        self.drone.demand = 0.0
        self.drone.state.return_value = BootingState()
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, CleanupState)
        self.assertEqual(self.drone._supply, 0.0)

    def test_integrate_state(self):
        self.drone.state.return_value = IntegrateState
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, IntegratingState)
        self.drone.batch_system_agent.integrate_machine.assert_called_with(
            drone_uuid="test-923ABF"
        )

    def test_integrating_state(self):
        matrix = [
            (ResourceStatus.Running, MachineStatus.NotAvailable, IntegratingState),
            (ResourceStatus.Running, MachineStatus.Available, AvailableState),
            (ResourceStatus.Running, MachineStatus.Draining, DrainingState),
            (ResourceStatus.Running, MachineStatus.Drained, DisintegrateState),
            (ResourceStatus.Booting, MachineStatus.NotAvailable, BootingState),
            (ResourceStatus.Booting, MachineStatus.Available, BootingState),
            (ResourceStatus.Booting, MachineStatus.Drained, BootingState),
            (ResourceStatus.Booting, MachineStatus.Draining, BootingState),
            (ResourceStatus.Deleted, MachineStatus.NotAvailable, DownState),
            (ResourceStatus.Stopped, MachineStatus.NotAvailable, CleanupState),
            (ResourceStatus.Error, MachineStatus.Available, CleanupState),
            (ResourceStatus.Error, MachineStatus.NotAvailable, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=IntegratingState)

    def test_available_state(self):
        self.drone.database_state = AsyncMock()

        matrix = [
            (ResourceStatus.Running, MachineStatus.Available, AvailableState),
            (ResourceStatus.Running, MachineStatus.NotAvailable, ShutDownState),
            (ResourceStatus.Running, MachineStatus.Draining, DrainingState),
            (ResourceStatus.Running, MachineStatus.Drained, DisintegrateState),
            (ResourceStatus.Booting, MachineStatus.NotAvailable, BootingState),
            (ResourceStatus.Deleted, MachineStatus.NotAvailable, DownState),
            (ResourceStatus.Stopped, MachineStatus.NotAvailable, CleanupState),
            (ResourceStatus.Error, MachineStatus.NotAvailable, CleanupState),
            (ResourceStatus.Error, MachineStatus.Available, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=AvailableState)

        # Test draining procedure if cobald sets drone demand to zero
        self.drone.demand = 0.0
        self.drone.state.return_value = AvailableState()
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, DrainState)
        self.assertEqual(self.drone._supply, 0.0)

        # Test draining procedure due to exceeding life time of the drone
        self.drone.demand = 8.0
        self.drone.minimum_lifetime = 1
        self.drone.state.return_value = AvailableState()
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, DrainState)

        # Test remote draining procedure via REST service and database
        self.drone.database_state = AsyncMock(return_value=DrainState)
        self.drone.state.return_value = AvailableState()
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, DrainState)

    def test_drain_state(self):
        self.drone.state.return_value = DrainState
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, DrainingState)
        self.drone.batch_system_agent.drain_machine.assert_called_with(
            drone_uuid="test-923ABF"
        )

    def test_draining_state(self):
        matrix = [
            (ResourceStatus.Running, MachineStatus.Draining, DrainingState),
            (ResourceStatus.Running, MachineStatus.Available, DrainState),
            (ResourceStatus.Running, MachineStatus.Drained, DisintegrateState),
            (ResourceStatus.Running, MachineStatus.NotAvailable, ShutDownState),
            (ResourceStatus.Booting, MachineStatus.NotAvailable, CleanupState),
            (ResourceStatus.Deleted, MachineStatus.NotAvailable, DownState),
            (ResourceStatus.Stopped, MachineStatus.NotAvailable, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=DrainingState)

    def test_disintegrate_state(self):
        self.drone.state.return_value = DisintegrateState
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertIsInstance(self.drone.state, ShutDownState)
        self.drone.batch_system_agent.disintegrate_machine.assert_called_with(
            drone_uuid="test-923ABF"
        )

    def test_shutdown_state(self):
        matrix = [
            (ResourceStatus.Booting, None, CleanupState),
            (ResourceStatus.Running, None, ShuttingDownState),
            (ResourceStatus.Stopped, None, CleanupState),
            (ResourceStatus.Deleted, None, DownState),
            (ResourceStatus.Error, None, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=ShutDownState)

        self.run_side_effects(
            ShutDownState,
            self.drone.site_agent.resource_status,
            (TardisAuthError, TardisTimeout, TardisResourceStatusUpdateFailed),
            ShutDownState,
        )

        self.run_side_effects(
            ShutDownState,
            self.drone.site_agent.resource_status,
            (TardisDroneCrashed,),
            CleanupState,
        )

        self.mock_drone.reset()
        self.drone.site_agent.resource_status = AsyncMock(
            return_value=AttributeDict(resource_status=ResourceStatus.Running)
        )
        with self.assertLogs(level=logging.WARNING):
            self.run_side_effects(
                ShutDownState,
                self.drone.site_agent.stop_resource,
                (TardisResourceStatusUpdateFailed,),
                ShutDownState,
            )
        self.drone.site_agent.stop_resource.assert_called_with(
            self.drone.resource_attributes
        )

    def test_shutting_down_state(self):
        matrix = [
            (ResourceStatus.Booting, None, CleanupState),
            (ResourceStatus.Running, None, ShuttingDownState),
            (ResourceStatus.Stopped, None, CleanupState),
            (ResourceStatus.Deleted, None, DownState),
            (ResourceStatus.Error, None, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=ShuttingDownState)

    def test_cleanup_state(self):
        matrix = [
            (ResourceStatus.Booting, None, CleanupState),
            (ResourceStatus.Running, None, DrainState),
            (ResourceStatus.Stopped, None, CleanupState),
            (ResourceStatus.Deleted, None, DownState),
            (ResourceStatus.Error, None, CleanupState),
        ]

        self.run_the_matrix(matrix, initial_state=CleanupState)

        log_channel = "cobald.runtime.tardis.resources.dronestates"

        with self.assertLogs(level=logging.WARNING) as msg:
            self.run_side_effects(
                CleanupState(),
                self.drone.site_agent.terminate_resource,
                (TardisDroneCrashed,),
                DownState,
            )
            self.assertEqual(
                msg.output,
                [
                    f"WARNING:{log_channel}:Calling terminate_resource failed for"
                    " drone test-923ABF. Drone crashed!"
                ],
            )

        with self.assertLogs(level=logging.WARNING) as msg:
            self.run_side_effects(
                CleanupState(),
                self.drone.site_agent.terminate_resource,
                (TardisResourceStatusUpdateFailed,),
                CleanupState,
            )
            self.assertEqual(
                msg.output,
                [
                    f"WARNING:{log_channel}:Calling terminate_resource failed for"
                    " drone test-923ABF. Will retry later!"
                ],
            )

        self.drone.site_agent.terminate_resource.side_effect = None

    def test_down_state(self):
        self.drone.state.return_value = DownState()
        asyncio.run(self.drone.state.return_value.run(self.drone))
        self.assertEqual(self.drone.demand, 0.0)

    def test_transition_logic_raises_exception_on_unknown_transition(self):
        test_cases = [
            (BootingState, (0.5, None)),
            (IntegratingState, (None, None)),
            (AvailableState, (False, 1.0, False, None, None)),
            (DrainingState, (None, None)),
            (ShutDownState, (None,)),
            (ShuttingDownState, (None,)),
            (CleanupState, (None,)),
        ]

        for state_class, pipeline_results in test_cases:
            with self.assertRaises(TardisUnknownStateTransition) as ctx:
                asyncio.run(state_class.transition_logic(*pipeline_results))
            self.assertIn(
                f"Unknown state transition in {state_class.__name__}",
                str(ctx.exception),
            )

    def test_check_minimum_lifetime(self):
        self.drone.minimum_lifetime = None
        self.drone.resource_attributes.updated = datetime.now()
        result = asyncio.run(check_minimum_lifetime(self.drone))
        self.assertFalse(result)

        self.drone.minimum_lifetime = 0
        self.drone.resource_attributes.updated = datetime.now()
        result = asyncio.run(check_minimum_lifetime(self.drone))
        self.assertFalse(result)

        self.drone.minimum_lifetime = 3600
        self.drone.resource_attributes.updated = datetime.now()
        result = asyncio.run(check_minimum_lifetime(self.drone))
        self.assertFalse(result)

        self.drone.minimum_lifetime = 3600
        self.drone.resource_attributes.updated = datetime.now() - timedelta(hours=2)
        result = asyncio.run(check_minimum_lifetime(self.drone))
        self.assertTrue(result)
