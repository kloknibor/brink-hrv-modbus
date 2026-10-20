"""Temporary Modbus boost ownership indicator."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from ..entity import BrinkEntity


class BoostActiveBinarySensor(BrinkEntity, BinarySensorEntity):
    """Report only a boost override that this integration initiated."""

    _attr_name = "Boost Active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_should_poll = False

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_boost_active"

    @property
    def is_on(self):
        return self.coordinator.boost_active
