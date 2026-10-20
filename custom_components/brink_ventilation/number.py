"""Platform for number integration."""

from __future__ import annotations

from .numbers.control_numbers import BoostMaximumDurationNumber, DirectAirflowNumber
from .numbers.filter_warning_days_number import FilterWarningDaysNumber


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            FilterWarningDaysNumber(coordinator, entry.entry_id),
            DirectAirflowNumber(coordinator, entry.entry_id),
            BoostMaximumDurationNumber(coordinator, entry.entry_id),
        ]
    )
