from collections import defaultdict
from datetime import datetime
import asyncio
import logging

from typing import TYPE_CHECKING
from typing import Type

from ..exceptions.tardisexceptions import TardisAuthError
from ..exceptions.tardisexceptions import TardisDroneCrashed
from ..exceptions.tardisexceptions import TardisTimeout
from ..exceptions.tardisexceptions import TardisQuotaExceeded
from ..exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from ..interfaces.batchsystemadapter import MachineStatus
from ..interfaces.state import State
from ..interfaces.siteadapter import ResourceStatus
from ..utilities.pipeline import StopProcessing

if TYPE_CHECKING:
    from tardis.resources.drone import Drone

logger = logging.getLogger("cobald.runtime.tardis.resources.dronestates")


async def batchsystem_machine_status(
    state_transition, drone: "Drone", current_state: Type[State]
):
    machine_status = await drone.batch_system_agent.get_machine_status(
        drone_uuid=drone.resource_attributes["drone_uuid"]
    )
    return state_transition[machine_status]()


async def check_remote_draining(
    state_transition, drone: "Drone", current_state: Type[State]
):
    database_state = await drone.database_state()

    if database_state is DrainState and database_state is not current_state:
        raise StopProcessing(last_result=database_state())
    return state_transition


async def check_demand(state_transition, drone: "Drone", current_state: Type[State]):
    if not drone.demand:
        drone._supply = 0.0
        if current_state in (BootingState,):
            raise StopProcessing(last_result=CleanupState())  # static state transition
        else:
            raise StopProcessing(last_result=DrainState())  # static state transition
    return state_transition


async def check_minimum_lifetime(
    state_transition, drone: "Drone", current_state: Type[State]
):
    if (
        drone.minimum_lifetime
        and (datetime.now() - drone.resource_attributes.updated).total_seconds()
        > drone.minimum_lifetime
    ):
        raise StopProcessing(last_result=DrainState())
    return state_transition


async def resource_status(state_transition, drone: "Drone", current_state: Type[State]):
    try:
        drone.resource_attributes.update(
            await drone.site_agent.resource_status(drone.resource_attributes)
        )
        logger.debug(f"Resource attributes: {drone.resource_attributes}")
    except (TardisAuthError, TardisTimeout, TardisResourceStatusUpdateFailed) as err:
        #  Retry to get current state of the resource
        raise StopProcessing(last_result=current_state()) from err
    except TardisDroneCrashed as tdc:
        #  Try to cleanup crashed resources
        raise StopProcessing(last_result=CleanupState()) from tdc
    else:
        return state_transition[drone.resource_attributes.resource_status]()


class RequestState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in RequestState")
        try:
            drone.resource_attributes.update(
                await drone.site_agent.deploy_resource(drone.resource_attributes)
            )
        except (
            TardisAuthError,
            TardisTimeout,
            TardisQuotaExceeded,
            TardisResourceStatusUpdateFailed,
        ):
            await drone.set_state(DownState())
        except TardisDroneCrashed:
            await drone.set_state(CleanupState())
        else:
            await drone.set_state(BootingState())


class BootingState(State):
    transition = {
        ResourceStatus.Booting: lambda: BootingState(),
        ResourceStatus.Running: lambda: IntegrateState(),
        ResourceStatus.Deleted: lambda: DownState(),
        ResourceStatus.Stopped: lambda: CleanupState(),
        ResourceStatus.Error: lambda: CleanupState(),
    }

    processing_pipeline = [check_demand, resource_status]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in BootingState")
        await drone.set_state(await cls.run_processing_pipeline(drone))


class IntegrateState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in IntegrateState")
        await drone.batch_system_agent.integrate_machine(
            drone_uuid=drone.resource_attributes["drone_uuid"]
        )
        await drone.set_state(IntegratingState())  # static state transition


class IntegratingState(State):
    transition = {
        ResourceStatus.Running: lambda: {
            MachineStatus.NotAvailable: lambda: IntegratingState(),
            MachineStatus.Available: lambda: AvailableState(),
            MachineStatus.Draining: lambda: DrainingState(),
            MachineStatus.Drained: lambda: DisintegrateState(),
        },
        ResourceStatus.Booting: lambda: defaultdict(lambda: BootingState),
        ResourceStatus.Deleted: lambda: defaultdict(lambda: DownState),
        ResourceStatus.Stopped: lambda: defaultdict(lambda: CleanupState),
        ResourceStatus.Error: lambda: defaultdict(lambda: CleanupState),
    }

    processing_pipeline = [resource_status, batchsystem_machine_status]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in IntegratingState")
        await drone.set_state(await cls.run_processing_pipeline(drone))


class AvailableState(State):
    transition = {
        ResourceStatus.Running: lambda: {
            MachineStatus.Available: lambda: AvailableState(),
            MachineStatus.NotAvailable: lambda: ShutDownState(),
            MachineStatus.Draining: lambda: DrainingState(),
            MachineStatus.Drained: lambda: DisintegrateState(),
        },
        ResourceStatus.Booting: lambda: defaultdict(lambda: BootingState),
        ResourceStatus.Deleted: lambda: defaultdict(lambda: DownState),
        ResourceStatus.Stopped: lambda: defaultdict(lambda: CleanupState),
        ResourceStatus.Error: lambda: defaultdict(lambda: CleanupState),
    }

    processing_pipeline = [
        check_remote_draining,
        check_demand,
        check_minimum_lifetime,
        resource_status,
        batchsystem_machine_status,
    ]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in AvailableState")

        new_state = await cls.run_processing_pipeline(drone)

        await drone.set_state(new_state)


class DrainState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in DrainState")
        await drone.batch_system_agent.drain_machine(
            drone_uuid=drone.resource_attributes["drone_uuid"]
        )
        await asyncio.sleep(0.5)
        await drone.set_state(DrainingState())  # static state transition


class DrainingState(State):
    transition = {
        ResourceStatus.Running: lambda: {
            MachineStatus.Draining: lambda: DrainingState(),
            MachineStatus.Available: lambda: DrainState(),
            MachineStatus.Drained: lambda: DisintegrateState(),
            MachineStatus.NotAvailable: lambda: ShutDownState(),
        },
        # In case the job is retried by HTCondor, resources can transition to
        # BootingState again. In this case the job should be removed.
        ResourceStatus.Booting: lambda: defaultdict(lambda: CleanupState),
        ResourceStatus.Deleted: lambda: defaultdict(lambda: DownState),
        ResourceStatus.Stopped: lambda: defaultdict(lambda: CleanupState),
        ResourceStatus.Error: lambda: defaultdict(lambda: CleanupState),
    }
    processing_pipeline = [resource_status, batchsystem_machine_status]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in DrainingState")
        await drone.set_state(await cls.run_processing_pipeline(drone))


class DisintegrateState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in DisintegrateState")
        await drone.batch_system_agent.disintegrate_machine(
            drone_uuid=drone.resource_attributes["drone_uuid"]
        )
        await drone.set_state(ShutDownState())  # static state transition


class ShutDownState(State):
    transition = {
        # In case the job is retried by HTCondor, resources can transition to
        # BootingState again. In this case the job should be removed.
        ResourceStatus.Booting: lambda: CleanupState(),
        ResourceStatus.Running: lambda: ShuttingDownState(),
        ResourceStatus.Stopped: lambda: CleanupState(),
        ResourceStatus.Deleted: lambda: DownState(),
        ResourceStatus.Error: lambda: CleanupState(),
    }

    processing_pipeline = [resource_status]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in ShutDownState")
        logger.debug(
            f"Stopping VM with ID {drone.resource_attributes.remote_resource_uuid}"
        )

        new_state = await cls.run_processing_pipeline(drone)
        if isinstance(new_state, ShuttingDownState):
            try:
                await drone.site_agent.stop_resource(drone.resource_attributes)
            except TardisResourceStatusUpdateFailed:
                logger.warning(
                    f"Calling stop_resource failed for drone "
                    f"{drone.resource_attributes.drone_uuid}"
                )
                new_state = ShutDownState()
        await drone.set_state(new_state)


class ShuttingDownState(State):
    transition = {
        # In case the job is retried by HTCondor, resources can transition to
        # BootingState again. In this case the job should be removed.
        ResourceStatus.Booting: lambda: CleanupState(),
        ResourceStatus.Running: lambda: ShuttingDownState(),
        ResourceStatus.Stopped: lambda: CleanupState(),
        ResourceStatus.Deleted: lambda: DownState(),
        ResourceStatus.Error: lambda: CleanupState(),
    }
    processing_pipeline = [resource_status]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in ShuttingDownState")
        logger.debug(
            f"Checking Status of drone with ID "
            f"{drone.resource_attributes.remote_resource_uuid}"
        )
        await drone.set_state(await cls.run_processing_pipeline(drone))


class CleanupState(State):
    transition = {
        ResourceStatus.Booting: lambda: CleanupState(),
        ResourceStatus.Running: lambda: DrainState(),
        ResourceStatus.Stopped: lambda: CleanupState(),
        ResourceStatus.Deleted: lambda: DownState(),
        ResourceStatus.Error: lambda: CleanupState(),
    }
    processing_pipeline = [resource_status]

    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in CleanupState")

        new_state = await cls.run_processing_pipeline(drone)

        if isinstance(new_state, CleanupState):
            try:
                logger.debug(
                    f"Destroying VM with ID "
                    f"{drone.resource_attributes.remote_resource_uuid}"
                )
                await drone.site_agent.terminate_resource(drone.resource_attributes)
            except TardisDroneCrashed:
                logger.warning(
                    f"Calling terminate_resource failed for drone "
                    f"{drone.resource_attributes.drone_uuid}. Drone crashed!"
                )
                new_state = DownState()
            except TardisResourceStatusUpdateFailed:
                logger.warning(
                    f"Calling terminate_resource failed for drone "
                    f"{drone.resource_attributes.drone_uuid}. Will retry later!"
                )

        await drone.set_state(new_state)  # static state transition


class DownState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in DownState")
        drone.demand = 0
