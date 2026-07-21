from datetime import datetime
from typing import TYPE_CHECKING
from typing import Type
import asyncio
import logging

from ..exceptions.tardisexceptions import TardisAuthError
from ..exceptions.tardisexceptions import TardisDroneCrashed
from ..exceptions.tardisexceptions import TardisTimeout
from ..exceptions.tardisexceptions import TardisQuotaExceeded
from ..exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from ..interfaces.batchsystemadapter import MachineStatus
from ..interfaces.state import State
from ..interfaces.siteadapter import ResourceStatus

if TYPE_CHECKING:
    from tardis.resources.drone import Drone

logger = logging.getLogger("cobald.runtime.tardis.resources.dronestates")


async def batchsystem_machine_status(drone: "Drone"):
    machine_status = await drone.batch_system_agent.get_machine_status(
        drone_uuid=drone.resource_attributes["drone_uuid"]
    )
    return machine_status


async def check_remote_draining(drone: "Drone") -> bool:
    database_state = await drone.database_state()
    return database_state is DrainState


async def check_demand(drone: "Drone"):
    if not drone.demand:
        drone._supply = 0.0
    return drone.demand


async def check_minimum_lifetime(drone: "Drone") -> bool:
    if not drone.minimum_lifetime:
        return False
    return (
        datetime.now() - drone.resource_attributes.updated
    ).total_seconds() > drone.minimum_lifetime


async def resource_status(drone: "Drone"):
    drone.resource_attributes.update(
        await drone.site_agent.resource_status(drone.resource_attributes)
    )
    logger.debug(f"Resource attributes: {drone.resource_attributes}")
    return drone.resource_attributes.resource_status


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
    task_pipeline = [check_demand, resource_status]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type[State]:
        demand, resource_status = pipeline_results
        match (demand, resource_status):
            case (0.0, _):
                return CleanupState
            case (_, ResourceStatus.Booting):
                return BootingState
            case (_, ResourceStatus.Running):
                return IntegrateState
            case (_, ResourceStatus.Deleted):
                return DownState
            case (_, ResourceStatus.Error | ResourceStatus.Stopped):
                return CleanupState
            case _:
                raise Exception(
                    f"Unknown state transition: {demand}, {resource_status}"
                )


class IntegrateState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in IntegrateState")
        await drone.batch_system_agent.integrate_machine(
            drone_uuid=drone.resource_attributes["drone_uuid"]
        )
        await drone.set_state(IntegratingState())  # static state transition


class IntegratingState(State):
    task_pipeline = [resource_status, batchsystem_machine_status]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type["State"]:
        resource_status, batchsystem_machine_status = pipeline_results

        match (resource_status, batchsystem_machine_status):
            case (ResourceStatus.Running, MachineStatus.Available):
                return AvailableState
            case (ResourceStatus.Running, MachineStatus.NotAvailable):
                return IntegratingState
            case (ResourceStatus.Running, MachineStatus.Draining):
                return DrainingState
            case (ResourceStatus.Running, MachineStatus.Drained):
                return DisintegrateState
            case (ResourceStatus.Booting, _):
                return BootingState
            case (ResourceStatus.Deleted, _):
                return DownState
            case (ResourceStatus.Stopped, _):
                return CleanupState
            case (ResourceStatus.Error, _):
                return CleanupState
            case _:
                raise Exception(
                    f"Unknown state transition: {resource_status}, {batchsystem_machine_status}"  # noqa B950
                )


class AvailableState(State):
    task_pipeline = [
        check_remote_draining,
        check_demand,
        check_minimum_lifetime,
        resource_status,
        batchsystem_machine_status,
    ]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type["State"]:
        remote_draining, demand, lifetime_exceeded, resource_status, batch_status = (
            pipeline_results
        )

        if remote_draining or demand == 0.0 or lifetime_exceeded:
            return DrainState

        match (resource_status, batch_status):
            case (ResourceStatus.Running, MachineStatus.Available):
                return AvailableState
            case (ResourceStatus.Running, MachineStatus.NotAvailable):
                return ShutDownState
            case (ResourceStatus.Running, MachineStatus.Draining):
                return DrainingState
            case (ResourceStatus.Running, MachineStatus.Drained):
                return DisintegrateState
            case (ResourceStatus.Booting, _):
                return BootingState
            case (ResourceStatus.Deleted, _):
                return DownState
            case (ResourceStatus.Stopped, _):
                return CleanupState
            case (ResourceStatus.Error, _):
                return CleanupState
            case _:
                raise Exception(
                    f"Unknown state transition: {resource_status}, {batch_status}"
                )


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
    task_pipeline = [resource_status, batchsystem_machine_status]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type["State"]:
        resource_status, batchsystem_machine_status = pipeline_results
        match (resource_status, batchsystem_machine_status):
            case (ResourceStatus.Running, MachineStatus.Draining):
                return DrainingState
            case (ResourceStatus.Running, MachineStatus.Available):
                return DrainState
            case (ResourceStatus.Running, MachineStatus.Drained):
                return DisintegrateState
            case (ResourceStatus.Running, MachineStatus.NotAvailable):
                return ShutDownState
            case (ResourceStatus.Booting, _):
                return CleanupState
            case (ResourceStatus.Deleted, _):
                return DownState
            case (ResourceStatus.Stopped, _):
                return CleanupState
            case (ResourceStatus.Error, _):
                return CleanupState
            case _:
                raise Exception(
                    f"Unknown state transition: {resource_status}, "
                    f"{batchsystem_machine_status}"
                )


class DisintegrateState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in DisintegrateState")
        await drone.batch_system_agent.disintegrate_machine(
            drone_uuid=drone.resource_attributes["drone_uuid"]
        )
        await drone.set_state(ShutDownState())  # static state transition


class ShutDownState(State):
    task_pipeline = [resource_status]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type["State"]:
        (resource_status,) = pipeline_results
        match (resource_status):
            case ResourceStatus.Booting:
                return CleanupState
            case ResourceStatus.Running:
                return ShuttingDownState
            case ResourceStatus.Stopped:
                return CleanupState
            case ResourceStatus.Deleted:
                return DownState
            case ResourceStatus.Error:
                return CleanupState
            case _:
                raise Exception(f"Unknown state transition: {resource_status}")

    @classmethod
    async def on_leave(
        cls, drone: "Drone", target_state: Type["State"]
    ) -> Type["State"]:
        if target_state is ShuttingDownState:
            try:
                logger.debug(
                    f"Stopping VM with ID {drone.resource_attributes.remote_resource_uuid}"  # noqa B950
                )
                await drone.site_agent.stop_resource(drone.resource_attributes)
            except TardisResourceStatusUpdateFailed:
                logger.warning(
                    f"Calling stop_resource failed for drone "
                    f"{drone.resource_attributes.drone_uuid}"
                )
                return ShutDownState
        return target_state


class ShuttingDownState(State):
    task_pipeline = [resource_status]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type[State]:
        (resource_status,) = pipeline_results
        match (resource_status):
            case ResourceStatus.Booting | ResourceStatus.Stopped | ResourceStatus.Error:
                return CleanupState
            case ResourceStatus.Running:
                return ShuttingDownState
            case ResourceStatus.Deleted:
                return DownState
            case _:
                raise Exception(f"Unknown state transition: {resource_status}")


class CleanupState(State):
    task_pipeline = [resource_status]

    @classmethod
    async def transition_logic(cls, *pipeline_results) -> Type["State"]:
        (resource_status,) = pipeline_results
        match (resource_status):
            case ResourceStatus.Booting:
                return CleanupState
            case ResourceStatus.Running:
                return DrainState
            case ResourceStatus.Stopped:
                return CleanupState
            case ResourceStatus.Deleted:
                return DownState
            case ResourceStatus.Error:
                return CleanupState
            case _:
                raise Exception(f"Unknown state transition: {resource_status}")

    @classmethod
    async def on_leave(
        cls, drone: "Drone", target_state: Type["State"]
    ) -> Type["State"]:
        if target_state is CleanupState:
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
                return DownState
            except TardisResourceStatusUpdateFailed:
                logger.warning(
                    f"Calling terminate_resource failed for drone "
                    f"{drone.resource_attributes.drone_uuid}. Will retry later!"
                )
        return target_state


class DownState(State):
    @classmethod
    async def run(cls, drone: "Drone"):
        logger.info(f"Drone {drone.resource_attributes} in DownState")
        drone.demand = 0
