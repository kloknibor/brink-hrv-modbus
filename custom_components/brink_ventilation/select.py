"""Platform for select integration."""

from __future__ import annotations

from .selects.control_selects import BypassModeSelect, ModbusControlModeSelect
from .selects.signal_output_select import BrinkSignalOutputSelect


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BrinkSignalOutputSelect(coordinator, entry.entry_id),
            ModbusControlModeSelect(coordinator, entry.entry_id),
            BypassModeSelect(coordinator, entry.entry_id),
        ]
    )
