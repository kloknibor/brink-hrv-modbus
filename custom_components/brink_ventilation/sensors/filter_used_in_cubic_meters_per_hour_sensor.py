from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume

from ..entity import BrinkEntity


class FilterUsedInCubicMetersPerHourSensor(BrinkEntity, SensorEntity):
    """Accumulated air volume since the last filter reset (4116–4117)."""

    _attr_name = "Filter Used Volume"
    _attr_icon = "mdi:air-filter"
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False  # do not call update()

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_filter_used_in_cubic_meters_per_hour"

    @property
    def native_value(self):
        return self.coordinator.filter_used_in_cubic_meters_per_hour
