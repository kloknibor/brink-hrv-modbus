"""The Brink HRV Modbus (kloknibor) integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from pymodbus.exceptions import ModbusException

from .const import CONF_HOST, CONF_INDOOR_TEMPERATURE_ENTITY, CONF_PORT, DOMAIN
from .coordinator import BrinkHrvModbusCoordinator

type BrinkConfigEntry = ConfigEntry[BrinkHrvModbusCoordinator]

_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.FAN,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
]
_SERVICE_START_BOOST = "start_boost"
_SERVICE_STOP_BOOST = "stop_boost"
_SERVICE_RETURN_TO_AUTO = "return_to_auto"
_SERVICE_ENTRY_ID = "entry_id"
_SERVICE_SCHEMA = vol.Schema({vol.Optional(_SERVICE_ENTRY_ID): str})


async def _async_get_coordinator(
    hass: HomeAssistant, call: ServiceCall
) -> BrinkHrvModbusCoordinator:
    coordinators: dict[str, BrinkHrvModbusCoordinator] = hass.data[DOMAIN][
        "coordinators"
    ]
    entry_id = call.data.get(_SERVICE_ENTRY_ID)
    if entry_id is not None:
        if entry_id not in coordinators:
            raise ValueError(f"Unknown Brink config entry {entry_id}")
        return coordinators[entry_id]
    if len(coordinators) != 1:
        raise ValueError(
            "Specify entry_id when more than one Brink appliance is configured"
        )
    return next(iter(coordinators.values()))


def _register_services(hass: HomeAssistant) -> None:
    """Register actions once, resolving the intended appliance at call time."""
    if hass.services.has_service(DOMAIN, _SERVICE_START_BOOST):
        return

    async def start_boost(call: ServiceCall) -> None:
        await (await _async_get_coordinator(hass, call)).async_start_boost()

    async def stop_boost(call: ServiceCall) -> None:
        await (await _async_get_coordinator(hass, call)).async_stop_boost()

    async def return_to_auto(call: ServiceCall) -> None:
        await (await _async_get_coordinator(hass, call)).set_modbus_control_mode(0)

    hass.services.async_register(
        DOMAIN, _SERVICE_START_BOOST, start_boost, schema=_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, _SERVICE_STOP_BOOST, stop_boost, schema=_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, _SERVICE_RETURN_TO_AUTO, return_to_auto, schema=_SERVICE_SCHEMA
    )


async def async_setup_entry(hass: HomeAssistant, entry: BrinkConfigEntry) -> bool:
    """Set up Brink HRA Modbus from a config entry."""
    try:
        coordinator = await BrinkHrvModbusCoordinator.initialize(
            hass,
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            entry.entry_id,
            entry.options.get(CONF_INDOOR_TEMPERATURE_ENTITY),
        )
    except ModbusException as err:
        raise ConfigEntryNotReady(
            f"Could not connect to {entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}"
        ) from err

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {}).setdefault("coordinators", {})[entry.entry_id] = (
        coordinator
    )
    _register_services(hass)
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BrinkConfigEntry) -> bool:
    """Unload platforms, retaining no socket or service routing state."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if not unloaded:
        return False
    await entry.runtime_data.async_close()
    coordinators = hass.data.get(DOMAIN, {}).get("coordinators", {})
    coordinators.pop(entry.entry_id, None)
    if not coordinators:
        for service in (
            _SERVICE_START_BOOST,
            _SERVICE_STOP_BOOST,
            _SERVICE_RETURN_TO_AUTO,
        ):
            hass.services.async_remove(DOMAIN, service)
    return True
