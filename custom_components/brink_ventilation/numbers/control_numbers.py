"""Numbers used for explicit direct-flow and temporary-boost control."""

from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTime, UnitOfVolumeFlowRate
from homeassistant.helpers.entity import EntityCategory

from ..entity import BrinkEntity


class DirectAirflowNumber(BrinkEntity, NumberEntity):
    """Requested flow written to 8002; it does not enable override itself."""

    _attr_name = "Requested Direct Airflow"
    _attr_icon = "mdi:air-filter"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR
    _attr_native_min_value = 50
    _attr_native_step = 1
    _attr_should_poll = False

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_requested_direct_airflow"

    @property
    def native_max_value(self):
        return self.coordinator.direct_flow_maximum

    @property
    def native_value(self):
        return self.coordinator.direct_flow

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.set_direct_flow(int(value))


class BoostMaximumDurationNumber(BrinkEntity, NumberEntity):
    """Safety maximum for a tracked temporary boost."""

    _attr_name = "Boost Maximum Duration"
    _attr_icon = "mdi:timer-sand"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 5
    _attr_native_max_value = 180
    _attr_native_step = 1
    _attr_should_poll = False

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_boost_maximum_duration"

    @property
    def native_value(self):
        return self.coordinator.boost_maximum_minutes

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.boost_maximum_minutes = int(value)
        await self.coordinator._save_boost_state()
        self.coordinator.async_update_listeners()
