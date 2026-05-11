from typing import List, Union, Optional, Type

from tardis.agents.batchsystemagent import BatchSystemAgent
from tardis.agents.siteagent import SiteAgent
from tardis.interfaces.plugin import Plugin
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.interfaces.state import State
from tardis.resources.dronestates import AvailableState
from .dronestates import DownState, RequestState
from ..plugins.sqliteregistry import SqliteRegistry
from ..utilities.attributedict import AttributeDict
from ..utilities.utils import load_states
from cobald.daemon import service
from cobald.interfaces import Pool

from datetime import datetime
from functools import cached_property

import asyncio
import logging
import uuid

logger = logging.getLogger("cobald.runtime.tardis.resources.drone")


@service(flavour=asyncio)
class Drone(Pool):
    def __init__(
        self,
        site_agent: SiteAgent,
        batch_system_agent: BatchSystemAgent,
        plugins: Optional[List[Plugin]] = None,
        remote_resource_uuid=None,
        drone_uuid=None,
        state: Optional[State] = None,
        created: Optional[float] = None,
        updated: Optional[float] = None,
    ):
        self._site_agent = site_agent
        self._batch_system_agent = batch_system_agent
        self._plugins = plugins or []
        self._state = state

        self.resource_attributes = AttributeDict(
            site_name=self._site_agent.site_name,
            machine_type=self.site_agent.machine_type,
            obs_machine_meta_data_translation_mapping=self.batch_system_agent.machine_meta_data_translation_mapping,  # noqa B950
            remote_resource_uuid=remote_resource_uuid,
            created=created or datetime.now(),  # timestamp drone creation
            updated=updated or datetime.now(),  # timestamp last drone state update
            drone_uuid=drone_uuid or self.site_agent.drone_uuid(uuid.uuid4().hex[:10]),
        )

        self._allocation = 0.0
        self._demand = self.maximum_demand
        self._utilisation = 0.0
        self._supply = 0.0

    @property
    def allocation(self) -> float:
        return self._allocation

    @property
    def batch_system_agent(self) -> BatchSystemAgent:
        return self._batch_system_agent

    @cached_property
    def _database(self) -> Optional[SqliteRegistry]:
        for plugin in self._plugins:
            if isinstance(plugin, SqliteRegistry):
                return plugin

    async def database_state(self) -> Optional[Type[State]]:
        try:
            return load_states(
                await self._database.get_resource_state(
                    self.resource_attributes.drone_uuid
                )
            )[0]["state"]
        except (IndexError, AttributeError):
            return None

    @property
    def demand(self) -> float:
        return self._demand

    @demand.setter
    def demand(self, value: float):
        self._demand = value

    @property
    def heartbeat_interval(self) -> int:
        return self.site_agent.drone_heartbeat_interval

    @property
    def minimum_lifetime(self) -> [int, None]:
        return self.site_agent.drone_minimum_lifetime

    @property
    def maximum_demand(self) -> float:
        return self.site_agent.machine_meta_data["Cores"]

    @property
    def supply(self) -> float:
        return self._supply

    @property
    def utilisation(self) -> float:
        return self._utilisation

    @property
    def site_agent(self) -> SiteAgent:
        return self._site_agent

    async def run(self):
        if self.state is None:
            # The state of a newly created Drone is None, since the plugins need
            # to be notified on the first state change. As calling the
            # ``set_state`` coroutine is not possible in the constructor, we
            # initiate the first state change here
            #
            # In addition, all necessary attributes in `resource_attributes`
            # `AttributeDict` need to be present and have meaningful defaults.
            # `resource_status` should be set to `ResourceStatus.Booting` on
            # newly created drones by default.
            self.resource_attributes.resource_status = ResourceStatus.Booting
            await self.set_state(RequestState())
        while True:
            current_state = self.state
            await current_state.run(self)
            if isinstance(current_state, DownState):
                logger.debug(
                    f"Garbage Collect Drone: {self.resource_attributes.drone_uuid}"
                )
                self._demand = 0
                return
            await asyncio.sleep(self.heartbeat_interval)

    def register_plugins(self, observer: Union[List[Plugin], Plugin]) -> None:
        self._plugins.append(observer)

    def remove_plugins(self, observer: Union[List[Plugin], Plugin]) -> None:
        self._plugins.remove(observer)

    async def set_state(self, state: State) -> None:
        """Should be replaced by asynchronous state.setter property once available"""
        if state.__class__ != self.state.__class__:
            self.resource_attributes.updated = datetime.now()
            self._state = state
            await self.notify_plugins()
        else:
            self._state = state

        match state:
            case AvailableState():
                await self.refresh_drone_metrics()

    @property
    def state(self) -> Optional[State]:
        return self._state

    async def refresh_drone_metrics(self) -> None:
        """
        Synchronizes drone metrics with the overlay batch system and set supply.
        """
        self._allocation, self._utilisation = await asyncio.gather(
            self.batch_system_agent.get_allocation(
                drone_uuid=self.resource_attributes["drone_uuid"]
            ),
            self.batch_system_agent.get_utilisation(
                drone_uuid=self.resource_attributes["drone_uuid"]
            ),
        )
        self._supply = self.maximum_demand

    async def notify_plugins(self) -> None:
        for plugin in self._plugins:
            await plugin.notify(self.state, self.resource_attributes)
