from ..configuration.configuration import Configuration
from ..utilities.attributedict import AttributeDict
from ..utilities.utils import machine_meta_data_translation

from abc import ABCMeta, abstractmethod
from cobald.utility.primitives import infinity as inf
from enum import Enum
from functools import lru_cache
from pydantic import BaseModel, conint, validator
from typing import Optional

import logging

logger = logging.getLogger("cobald.runtime.tardis.interfaces.site")


class SiteConfigurationModel(BaseModel):
    """
    pydantic BaseModel for the input validation of the generic site configuration
    """

    name: str
    adapter: str
    quota: Optional[int] = inf
    drone_minimum_lifetime: Optional[conint(gt=0)] = None
    drone_heartbeat_interval: Optional[conint(ge=0)] = 60

    class Config:
        extra = "forbid"

    @validator("quota")
    def quota_validator(cls, quota: Optional[int]):  # noqa B902
        assert quota != 0, "Zero quota is not a reasonable value"
        return quota


class ResourceStatus(Enum):
    """
    Status of the resource at the resource provider (batch system, cloud provider, etc.)
    """

    Booting = 1
    Running = 2
    Stopped = 3
    Deleted = 4
    Error = 5


class SiteAdapter(metaclass=ABCMeta):
    """
    Abstract base class defining the interface for SiteAdapters which provide
    access to various Cloud APIs and batch systems in order to manage
    opportunistic resources.
    """

    @property
    def configuration(self) -> AttributeDict:
        """
        Property to provide access to SiteAdapter specific configuration.
        :return: returns the Site Adapter specific configuration
        """
        return getattr(Configuration(), self.site_name)

    @abstractmethod
    async def deploy_resource(
        self, resource_attributes: AttributeDict
    ) -> AttributeDict:
        """
        Abstract method to define the interface to deploy a new resource at a
        resource provider.
        :param resource_attributes: Contains describing attributes of the resource,
        defined in the :py:class:`~tardis.resources.drone.Drone` implementation!
        :return: Contains updated describing attributes of the resource.
        """
        raise NotImplementedError

    def drone_environment(
        self, drone_uuid: str, meta_data_translation_mapping: AttributeDict
    ) -> dict:
        """
        Method to get the drone environment to be exported to batch jobs
        providing the actual resources in the overlay batch system. It
        translates units of drone meta data into a format the overlay
        batch system is expecting. Also, the drone_uuid is added  for matching
        drones to actual resources provided in the overlay batch system.
        :param drone_uuid: The unique id which is assigned to every drone on creation
        :param meta_data_translation_mapping: Mapping used for the meta data translation
        :return: Translated
        """
        drone_environment = machine_meta_data_translation(
            self.machine_meta_data, meta_data_translation_mapping
        )
        drone_environment["Uuid"] = drone_uuid

        return drone_environment

    @property
    def drone_heartbeat_interval(self) -> int:
        """
        Property that returns the configuration parameter drone_heartbeat_interval.
        It describes the time between two consecutive updates of the drone status.
        :return: The heartbeat interval of the drone
        """
        return self.site_configuration.drone_heartbeat_interval

    @property
    def drone_minimum_lifetime(self) -> Optional[int]:
        """
        Property that returns the configuration parameter drone_minimum_lifetime.
        It describes the minimum lifetime before a drone is automatically going
        into draining mode.
        :return: The minimum lifetime of the drone
        """
        return self.site_configuration.drone_minimum_lifetime

    def drone_uuid(self, uuid: str) -> str:
        """
        Returns the drone uuid consisting of the lower case site name and the
        first 10 bytes of uuid4 due to constraints on length of a full DNS name
        (253 bytes).
        :param uuid: The first 10 bytes of a uuid4
        :return: The drone uuid consisting of the lower case site name and the
        first 10 bytes of uuid4.
        """
        return f"{self.site_name.lower()}-{uuid}"

    @abstractmethod
    def handle_exceptions(self) -> None:
        """
        Abstract method defining the interface to handle exception occurring
        during interacting with the resource provider.
        """
        raise NotImplementedError

    @staticmethod
    def handle_response(
        response: dict,
        key_translator: dict,
        translator_functions: dict,
        **additional_content,
    ) -> dict:
        """
        Method to handle the responses of the resource provider and translating
        it to a uniform format.
        :param response: A dictionary containing the response of the
        resource provider.
        :param key_translator: A dictionary containing the translation of keys
        of the original response of the provider in keys of the common format.
        :param translator_functions: A dictionary containing functions to
        transform value of the original response of the provider into values of
        the common format.
        :param additional_content: Additional content to be put into response,
        which is not part of the original response of the resource provider.
        :return: Translated response of the resource provider in a common format.
        """
        translated_response = AttributeDict()

        for translated_key, key in key_translator.items():
            try:
                translated_response[translated_key] = translator_functions.get(
                    key, lambda x: x
                )(response[key])
            except KeyError:
                continue

        for key, value in additional_content.items():
            translated_response[key] = value

        return translated_response

    @property
    def machine_meta_data(self) -> AttributeDict:
        """
        Property to access the machine_meta_data (like cores, memory and disk)
        of a resource.
        :return: The machine_meta_data of a resource.
        """
        return self.configuration.MachineMetaData[self.machine_type]

    @property
    def machine_type(self) -> str:
        """
        Property to access the machine_type (flavour) of a resource and ensuring
        that all sub-classes of the SiteAdapter have a _machine_type
        class variable.
        :return: The machine_type of a resource.
        """
        try:
            # noinspection PyUnresolvedReferences
            return self._machine_type
        except AttributeError as ae:
            raise AttributeError(
                f"Class {self.__class__.__name__} must have an '_machine_type' instance variable"  # noqa
            ) from ae

    @property
    def machine_type_configuration(self) -> AttributeDict:
        """
        Property to access the machine_type_configuration (arguments of the API
        calls to the provider) of a resource.
        :return: The machine_type_configuration of a resource.
        """
        return self.configuration.MachineTypeConfiguration[self.machine_type]

    @abstractmethod
    async def resource_status(
        self, resource_attributes: AttributeDict
    ) -> AttributeDict:
        """
        Abstract method to define the interface to check the status of resources
        at a resource provider.
        :param resource_attributes: Contains describing attributes of the resource,
        defined in the :py:class:`~tardis.resources.drone.Drone` implementation!
        :return: Contains updated describing attributes of the resource.
        """
        raise NotImplementedError

    @property
    @lru_cache(maxsize=16)
    def site_configuration(self) -> AttributeDict:
        """
        Property that returns the generic site configuration. This corresponds
        to the Sites section in the yaml configuration. For example:
        .. code-block::

            Sites:
              - name: MySiteName_1
                adapter: MyAdapter2Use
                quota: 123
                drone_minimum_lifetime: 3600

        :return: The generic site configuration
        """
        for site_configuration in Configuration().Sites:
            if site_configuration.name == self.site_name:
                return AttributeDict(
                    SiteConfigurationModel(**site_configuration).dict()
                )

    @property
    def site_name(self) -> str:
        """
        Property to access the site_name of a resource and ensuring
        that all sub-classes of the SiteAdapter have a _site_name
        class variable.
        :return: The site_name of a resource.
        """
        try:
            # noinspection PyUnresolvedReferences
            return self._site_name
        except AttributeError as ae:
            raise AttributeError(
                f"Class {self.__class__.__name__} must have an '_site_name' instance variable"  # noqa
            ) from ae

    @abstractmethod
    async def stop_resource(self, resource_attributes: AttributeDict) -> None:
        """
        Abstract method to define the interface to stop resources at a resource
        provider.
        :param resource_attributes: Contains describing attributes of the resource,
        defined in the :py:class:`~tardis.resources.drone.Drone` implementation!
        """
        raise NotImplementedError

    @abstractmethod
    async def terminate_resource(self, resource_attributes: AttributeDict) -> None:
        """
        Abstract method to define the interface to terminate resources at a
        resource provider.
        :param resource_attributes: Contains describing attributes of the resource,
        defined in the :py:class:`~tardis.resources.drone.Drone` implementation!
        """
        raise NotImplementedError
