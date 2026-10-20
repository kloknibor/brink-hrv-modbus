"""Firmware-optional Brink system-fault state."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory

from ..entity import BrinkEntity


class SystemFaultBinarySensor(BrinkEntity, BinarySensorEntity):
    """Expose warning/error readback 4800 when firmware supports it."""

    _attr_name = "System Fault"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_should_poll = False

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_system_fault"

    @property
    def available(self):
        return super().available and self.coordinator.system_error_status is not None

    @property
    def is_on(self):
        return self.coordinator.system_error_status in (1, 2, 3)
