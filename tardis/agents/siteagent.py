from ..interfaces.siteadapter import SiteAdapter
from ..utilities.attributedict import AttributeDict
from ..utilities.attributedict import convert_to_attribute_dict


class SiteAgent(SiteAdapter):
    def __init__(self, site_adapter: SiteAdapter):
        self._site_adapter = site_adapter

    async def deploy_resource(
        self, resource_attributes: AttributeDict
    ) -> AttributeDict:
        with self.handle_exceptions():
            response = await self._site_adapter.deploy_resource(
                resource_attributes=resource_attributes
            )
            return convert_to_attribute_dict(response)

    def drone_uuid(self, uuid) -> str:
        return self._site_adapter.drone_uuid(uuid=uuid)

    def handle_exceptions(self):
        return self._site_adapter.handle_exceptions()

    def handle_response(
        self,
        response,
        key_translator: dict,
        translator_functions: dict,
        **additional_content,
    ):
        return NotImplemented

    @property
    def drone_heartbeat_interval(self) -> int:
        return self._site_adapter.drone_heartbeat_interval

    @property
    def drone_minimum_lifetime(self) -> int:
        return self._site_adapter.drone_minimum_lifetime

    @property
    def machine_meta_data(self) -> AttributeDict:
        return self._site_adapter.machine_meta_data

    @property
    def machine_type(self) -> str:
        return self._site_adapter.machine_type

    async def resource_status(
        self, resource_attributes: AttributeDict
    ) -> AttributeDict:
        with self._site_adapter.handle_exceptions():
            return await self._site_adapter.resource_status(
                resource_attributes=resource_attributes
            )

    @property
    def site_name(self) -> str:
        return self._site_adapter.site_name

    async def stop_resource(self, resource_attributes: AttributeDict):
        with self._site_adapter.handle_exceptions():
            return await self._site_adapter.stop_resource(
                resource_attributes=resource_attributes
            )

    async def terminate_resource(self, resource_attributes: AttributeDict):
        with self._site_adapter.handle_exceptions():
            return await self._site_adapter.terminate_resource(
                resource_attributes=resource_attributes
            )
