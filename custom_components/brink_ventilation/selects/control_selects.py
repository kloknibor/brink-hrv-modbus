"""Explicit, readback-backed Brink control selects."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from ..entity import BrinkEntity

MODBUS_CONTROL_OPTIONS = {
    "Auto / RF Control": 0,
    "Manual Switch": 1,
    "Direct Flow": 2,
}
BYPASS_OPTIONS = {"Automatic": 0, "Closed": 1, "Open": 2}


class ModbusControlModeSelect(BrinkEntity, SelectEntity):
    """Expose 8000, always displaying its actual Modbus readback."""

    _attr_name = "Modbus Control Mode"
    _attr_icon = "mdi:remote"
    _attr_should_poll = False
    _attr_options = list(MODBUS_CONTROL_OPTIONS)

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_modbus_control_mode"

    @property
    def current_option(self):
        return next(
            (
                name
                for name, value in MODBUS_CONTROL_OPTIONS.items()
                if value == self.coordinator.modbus_control_mode
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.set_modbus_control_mode(MODBUS_CONTROL_OPTIONS[option])


class BypassModeSelect(BrinkEntity, SelectEntity):
    """Expose documented bypass override 6100; automatic is the default."""

    _attr_name = "Bypass Mode"
    _attr_icon = "mdi:transit-connection-variant"
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(BYPASS_OPTIONS)

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_bypass_mode"

    @property
    def current_option(self):
        return next(
            (
                name
                for name, value in BYPASS_OPTIONS.items()
                if value == self.coordinator.bypass_mode
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.set_bypass_mode(BYPASS_OPTIONS[option])
