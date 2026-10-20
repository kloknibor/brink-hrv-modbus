from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_NAME, DOMAIN


class BrinkEntity(CoordinatorEntity):
    """Base entity for integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._unique_device_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_device_id)},
            name=DEVICE_NAME,
            manufacturer="Brink",
            model="Heat Recovery Ventilation",
        )
