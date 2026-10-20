"""Buttons for safe, temporary ventilation boost."""

from homeassistant.components.button import ButtonEntity

from ..entity import BrinkEntity


class StartBoostButton(BrinkEntity, ButtonEntity):
    """Start a tracked high-speed temporary Modbus override."""

    _attr_name = "Start Boost"
    _attr_icon = "mdi:shower-head"
    _attr_should_poll = False

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_start_boost"

    async def async_press(self) -> None:
        await self.coordinator.async_start_boost()


class StopBoostButton(BrinkEntity, ButtonEntity):
    """Release a tracked boost and return authority to RF/CO₂ control."""

    _attr_name = "Stop Boost / Return to Auto"
    _attr_icon = "mdi:backup-restore"
    _attr_should_poll = False

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_stop_boost_return_to_auto"

    async def async_press(self) -> None:
        await self.coordinator.async_stop_boost()
