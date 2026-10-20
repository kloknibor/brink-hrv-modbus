from .binary_sensors.boost_active_binary_sensor import BoostActiveBinarySensor
from .binary_sensors.filter_status_binary_sensor import FilterStatusBinarySensor
from .binary_sensors.system_fault_binary_sensor import SystemFaultBinarySensor


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data

    async_add_entities(
        [
            FilterStatusBinarySensor(coordinator, entry.entry_id),
            BoostActiveBinarySensor(coordinator, entry.entry_id),
            SystemFaultBinarySensor(coordinator, entry.entry_id),
        ]
    )
