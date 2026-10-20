"""Platform for button integration."""

from __future__ import annotations

from .buttons.boost_buttons import StartBoostButton, StopBoostButton
from .buttons.reset_filter_warning_button import ResetFilterWarningButton


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ResetFilterWarningButton(coordinator, entry.entry_id),
            StartBoostButton(coordinator, entry.entry_id),
            StopBoostButton(coordinator, entry.entry_id),
        ]
    )
