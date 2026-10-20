"""Coordinator, calculated telemetry, and safe temporary boost ownership."""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from datetime import datetime, timedelta
from statistics import fmean
from typing import Any

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pymodbus.exceptions import ModbusException

from .lib.brink import Brink, BrinkModbusError

_LOGGER = logging.getLogger(__name__)
_POLL_INTERVAL = timedelta(seconds=10)
_SLOW_INTERVAL = timedelta(seconds=60)
_DEFAULT_BOOST_MAXIMUM_MINUTES = 60
_DIRECT_FLOW_MINIMUM = 50
_DIRECT_FLOW_MAXIMUM_FLAIR_400 = 400


def absolute_humidity(
    temperature: float | None, humidity: float | None
) -> float | None:
    """Return absolute humidity in g/m³ from a matched temperature/RH pair."""
    if temperature is None or humidity is None or not 0 <= humidity <= 100:
        return None
    # Magnus formula; appropriate for normal ventilation temperatures.
    saturation_hpa = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5))
    return round(216.7 * (humidity / 100 * saturation_hpa) / (273.15 + temperature), 2)


def dew_point(temperature: float | None, humidity: float | None) -> float | None:
    """Return dew point in °C from a matched temperature/RH pair."""
    if temperature is None or humidity is None or not 0 < humidity <= 100:
        return None
    gamma = math.log(humidity / 100) + (17.67 * temperature) / (243.5 + temperature)
    return round((243.5 * gamma) / (17.67 - gamma), 2)


class BrinkHrvModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate one appliance, ensuring poll and writes never collide."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str | None = None,
        indoor_temperature_entity: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Brink HRV Modbus Coordinator",
            update_interval=_POLL_INTERVAL,
        )
        self._brink: Brink
        self._entry_id = entry_id or "legacy"
        self._indoor_temperature_entity = indoor_temperature_entity
        self._control_lock = asyncio.Lock()
        self._last_slow_refresh: datetime | None = None
        self._slow_data: dict[str, Any] = self._default_slow_data()
        self._humidity_history: deque[tuple[datetime, float]] = deque(maxlen=360)
        self._boost_store = Store[dict[str, Any]](
            hass, 1, f"brink_ventilation.boost.{self._entry_id}"
        )
        self.boost_active = False
        self.boost_reason = "Idle"
        self.boost_started: datetime | None = None
        self.boost_maximum_minutes = _DEFAULT_BOOST_MAXIMUM_MINUTES
        self.boost_conflict = False
        self._set_compatibility_defaults()

    def _set_compatibility_defaults(self) -> None:
        """Retain attributes consumed by existing entity modules and users."""
        defaults: dict[str, Any] = {
            "supply_temperature": None,
            "supply_humidity": None,
            "exhaust_temperature": None,
            "exhaust_humidity": None,
            "fan_state": 0,
            "last_fan_position": 1,
            "bypass_status": 0,
            "preheater_status": 0,
            "preheater_capacity": 0,
            "frost_status": 0,
            "frost_heater_power": 0,
            "frost_fan_reduction": 0,
            "filter_dirty": False,
            "modbus_control_mode": 0,
            "modbus_contol_mode": 0,
            "standby_mode": 0,
            "signal_output": 0,
            "operating_hours": 0,
            "filter_used_in_hours": 0,
            "filter_used_volume": 0,
            "filter_used_in_cubic_meters_per_hour": 0,
            "filter_warning_days": 0,
            "supply_flow_setpoint": 0,
            "supply_flow": 0,
            "exhaust_flow_setpoint": 0,
            "exhaust_flow": 0,
            "active_function": 0,
            "direct_flow": 0,
        }
        for number in range(1, 5):
            defaults[f"CO2_sensor_{number}_status"] = 0
            defaults[f"CO2_sensor_{number}"] = None
            defaults[f"co2_sensor_{number}_status"] = 0
            defaults[f"co2_sensor_{number}"] = None
        for name, value in defaults.items():
            setattr(self, name, value)

    @staticmethod
    def _default_slow_data() -> dict[str, Any]:
        return {
            "filter_dirty": False,
            "operating_hours": None,
            "filter_used_in_hours": None,
            "filter_used_volume": None,
            "lifetime_air_volume": None,
            "flow_preset_0": None,
            "flow_preset_1": None,
            "flow_preset_2": None,
            "flow_preset_3": None,
            "bypass_mode": None,
            "filter_warning_days": None,
            "rht_sensor_mode": None,
            "co2_sensor_mode": None,
            "signal_output": None,
            "system_error_status": None,
            "active_incident": None,
        }

    @classmethod
    async def initialize(
        cls,
        hass: HomeAssistant,
        host: str,
        port: int,
        entry_id: str | None = None,
        indoor_temperature_entity: str | None = None,
    ) -> BrinkHrvModbusCoordinator:
        """Create the connection and restore only our own unfinished boost state."""
        self = cls(hass, entry_id, indoor_temperature_entity)
        self._brink = await Brink.initialize(host, port, 20)
        saved = await self._boost_store.async_load()
        if saved:
            self.boost_active = bool(saved.get("active", False))
            self.boost_reason = str(saved.get("reason", "Recovered boost"))
            self.boost_maximum_minutes = int(
                saved.get("maximum_minutes", _DEFAULT_BOOST_MAXIMUM_MINUTES)
            )
            raw_start = saved.get("started")
            if isinstance(raw_start, str):
                self.boost_started = dt_util.parse_datetime(raw_start)
        return self

    async def async_close(self) -> None:
        """Close the TCP client without attempting to modify appliance control."""
        self._brink.close()

    @property
    def direct_flow_maximum(self) -> int:
        """The documented Flair 400 limit; never inherit Flair 325's 325 limit."""
        return _DIRECT_FLOW_MAXIMUM_FLAIR_400

    @property
    def boost_elapsed_minutes(self) -> float | None:
        if not self.boost_active or self.boost_started is None:
            return None
        return round((dt_util.utcnow() - self.boost_started).total_seconds() / 60, 1)

    @property
    def boost_remaining_minutes(self) -> float | None:
        elapsed = self.boost_elapsed_minutes
        if elapsed is None:
            return None
        return max(0, round(self.boost_maximum_minutes - elapsed, 1))

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll dynamic telemetry every 10 s and low-rate diagnostics every minute."""
        now = dt_util.utcnow()
        include_slow = (
            self._last_slow_refresh is None
            or now - self._last_slow_refresh >= _SLOW_INTERVAL
        )
        try:
            dynamic = await self._brink.read_snapshot(include_slow=include_slow)
        except (BrinkModbusError, ModbusException, OSError) as err:
            raise UpdateFailed(f"Modbus read failed: {err}") from err

        if include_slow:
            self._slow_data.update(
                {key: value for key, value in dynamic.items() if key in self._slow_data}
            )
            self._last_slow_refresh = now
        data = {**self._slow_data, **dynamic}
        self._apply_data(data)
        self._calculate_metrics(data, now)
        await self._reconcile_boost(data, now)
        data.update(
            boost_active=self.boost_active,
            boost_reason=self.boost_reason,
            boost_elapsed_minutes=self.boost_elapsed_minutes,
            boost_remaining_minutes=self.boost_remaining_minutes,
        )
        self._apply_data(data)
        return data

    def _apply_data(self, data: dict[str, Any]) -> None:
        """Expose snapshot keys as coordinator attributes for existing entities."""
        for key, value in data.items():
            setattr(self, key, value)
        self.modbus_contol_mode = self.modbus_control_mode
        self.filter_used_in_cubic_meters_per_hour = self.filter_used_volume
        for number in range(1, 5):
            setattr(self, f"CO2_sensor_{number}", data.get(f"co2_sensor_{number}"))
            setattr(
                self,
                f"CO2_sensor_{number}_status",
                data.get(f"co2_sensor_{number}_status", 0),
            )

    def _calculate_metrics(self, data: dict[str, Any], now: datetime) -> None:
        supply_temp = data.get("supply_temperature")
        supply_rh = data.get("supply_humidity")
        exhaust_temp = data.get("exhaust_temperature")
        exhaust_rh = data.get("exhaust_humidity")
        supply_ah = absolute_humidity(supply_temp, supply_rh)
        exhaust_ah = absolute_humidity(exhaust_temp, exhaust_rh)
        data.update(
            supply_absolute_humidity=supply_ah,
            exhaust_absolute_humidity=exhaust_ah,
            supply_dew_point=dew_point(supply_temp, supply_rh),
            exhaust_dew_point=dew_point(exhaust_temp, exhaust_rh),
            absolute_humidity_difference=(
                round(exhaust_ah - supply_ah, 2)
                if exhaust_ah is not None and supply_ah is not None
                else None
            ),
        )
        if exhaust_ah is not None:
            self._humidity_history.append((now, exhaust_ah))
        history = list(self._humidity_history)
        if len(history) >= 3:
            # Lower third remains a useful baseline even after a shower has
            # raised humidity for most of a rolling hour.
            values = sorted(value for _, value in history)
            baseline = fmean(values[: max(1, len(values) // 3)])
            old_time, old_value = history[max(0, len(history) - 7)]
            minutes = max((now - old_time).total_seconds() / 60, 1 / 6)
            rate = (history[-1][1] - old_value) / minutes
            data["exhaust_absolute_humidity_baseline"] = round(baseline, 2)
            data["exhaust_humidity_baseline_deviation"] = round(
                exhaust_ah - baseline, 2
            )
            data["exhaust_humidity_rise_rate"] = round(rate, 2)
        else:
            data["exhaust_absolute_humidity_baseline"] = None
            data["exhaust_humidity_baseline_deviation"] = None
            data["exhaust_humidity_rise_rate"] = None

        supply_flow = data.get("supply_flow")
        exhaust_flow = data.get("exhaust_flow")
        supply_setpoint = data.get("supply_flow_setpoint")
        exhaust_setpoint = data.get("exhaust_flow_setpoint")
        data["airflow_balance"] = (
            supply_flow - exhaust_flow
            if supply_flow is not None and exhaust_flow is not None
            else None
        )
        data["airflow_imbalance_percent"] = (
            round(100 * (supply_flow - exhaust_flow) / exhaust_flow, 1)
            if exhaust_flow not in (None, 0) and supply_flow is not None
            else None
        )
        data["supply_setpoint_deviation"] = (
            supply_flow - supply_setpoint
            if supply_flow is not None and supply_setpoint is not None
            else None
        )
        data["exhaust_setpoint_deviation"] = (
            exhaust_flow - exhaust_setpoint
            if exhaust_flow is not None and exhaust_setpoint is not None
            else None
        )
        data["supply_rpm_per_airflow"] = self._safe_ratio(
            data.get("supply_fan_rpm"), supply_flow
        )
        data["exhaust_rpm_per_airflow"] = self._safe_ratio(
            data.get("exhaust_fan_rpm"), exhaust_flow
        )

        outside = data.get("outside_temperature")
        bypass_open = data.get("bypass_status") in (1, 2, 3)
        unsuitable = (
            bypass_open
            or data.get("preheater_status") == 2
            or data.get("frost_status") not in (2, 3)
        )
        external_indoor = self._external_indoor_temperature()
        indoor_extract = (
            external_indoor
            if external_indoor is not None
            else data.get("dwelling_temperature")
        )
        data["indoor_extract_temperature"] = indoor_extract
        delta = (
            indoor_extract - outside
            if indoor_extract is not None and outside is not None
            else None
        )
        if (
            not unsuitable
            and delta is not None
            and abs(delta) >= 1
            and supply_temp is not None
        ):
            data["heat_recovery_efficiency"] = round(
                100 * (supply_temp - outside) / delta, 1
            )
        else:
            data["heat_recovery_efficiency"] = None
        if (
            not unsuitable
            and supply_flow is not None
            and supply_temp is not None
            and outside is not None
            and supply_temp > outside
        ):
            data["recovered_thermal_power"] = round(
                0.34 * supply_flow * (supply_temp - outside)
            )
        else:
            data["recovered_thermal_power"] = None

    @staticmethod
    def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return round(numerator / denominator, 2)

    def _external_indoor_temperature(self) -> float | None:
        """Read an optional HA indoor/extract-temperature source safely."""
        if not self._indoor_temperature_entity:
            return None
        state = self.hass.states.get(self._indoor_temperature_entity)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            temperature = float(state.state)
        except ValueError:
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit == UnitOfTemperature.FAHRENHEIT:
            return (temperature - 32) * 5 / 9
        if unit == UnitOfTemperature.KELVIN:
            return temperature - 273.15
        return temperature

    async def _reconcile_boost(self, data: dict[str, Any], now: datetime) -> None:
        """Only release a control override that this integration persisted as ours."""
        if not self.boost_active:
            return
        if data.get("modbus_control_mode") != 1:
            self.boost_active = False
            self.boost_conflict = True
            self.boost_reason = "Conflict detected: Modbus mode changed externally"
            await self._save_boost_state()
            return
        if self.boost_started is None:
            self.boost_started = now
        if now - self.boost_started >= timedelta(minutes=self.boost_maximum_minutes):
            try:
                await self._brink.release_modbus_control()
            except BrinkModbusError as err:
                self.boost_reason = f"Maximum reached; return to auto failed: {err}"
                _LOGGER.error("Could not release expired Brink boost: %s", err)
                await self._save_boost_state()
                return
            self.boost_active = False
            self.boost_reason = (
                "Maximum duration reached; returned to Auto / RF Control"
            )
            data["modbus_control_mode"] = 0
            await self._save_boost_state()

    async def _save_boost_state(self) -> None:
        await self._boost_store.async_save(
            {
                "active": self.boost_active,
                "reason": self.boost_reason,
                "started": self.boost_started.isoformat()
                if self.boost_started
                else None,
                "maximum_minutes": self.boost_maximum_minutes,
            }
        )

    async def async_start_boost(self, reason: str = "Manual boost") -> None:
        """Request high ventilation, then explicitly enable switch override."""
        async with self._control_lock:
            current_mode = await self._brink.get_modbus_control_switch_mode()
            if self.boost_active and current_mode == 1:
                return
            if current_mode != 0:
                raise BrinkModbusError(
                    "Cannot start boost: another Modbus override is active. "
                    "Choose Auto / RF Control first."
                )
            await self._brink.start_switch_override(3)
            self.boost_active = True
            self.boost_conflict = False
            self.boost_reason = reason
            self.boost_started = dt_util.utcnow()
            await self._save_boost_state()
        await self.async_request_refresh()

    async def async_stop_boost(self) -> None:
        """Release a tracked boost, without overwriting a conflicting controller."""
        async with self._control_lock:
            current_mode = await self._brink.get_modbus_control_switch_mode()
            if self.boost_active and current_mode != 1:
                self.boost_active = False
                self.boost_conflict = True
                self.boost_reason = "Conflict detected: Modbus mode changed externally"
                await self._save_boost_state()
                raise BrinkModbusError(self.boost_reason)
            if self.boost_active or current_mode == 1:
                await self._brink.release_modbus_control()
            self.boost_active = False
            self.boost_reason = "Returned to Auto / RF Control"
            self.boost_started = None
            await self._save_boost_state()
        await self.async_request_refresh()

    async def set_modbus_control_mode(self, mode: int) -> None:
        """Explicitly select Auto/RF, switch control, or direct-flow control."""
        if mode not in (0, 1, 2):
            raise ValueError("Modbus control mode must be 0, 1, or 2")
        async with self._control_lock:
            if mode == 0:
                await self._brink.release_modbus_control()
                self.boost_active = False
                self.boost_reason = "Returned to Auto / RF Control"
                self.boost_started = None
                await self._save_boost_state()
            elif mode == 1:
                position = self.fan_state if self.fan_state in range(4) else 2
                await self._brink.start_switch_override(position)
                await self._manual_command_ended_boost()
            else:
                if (
                    not _DIRECT_FLOW_MINIMUM
                    <= self.direct_flow
                    <= self.direct_flow_maximum
                ):
                    raise ValueError(
                        "Set Requested Airflow to "
                        f"{_DIRECT_FLOW_MINIMUM}–{self.direct_flow_maximum} m³/h "
                        "before enabling Direct Flow"
                    )
                await self._brink.start_direct_flow_override(self.direct_flow)
                await self._manual_command_ended_boost()
        await self.async_request_refresh()

    async def set_switch_position(self, position: int) -> None:
        """Set a manual ventilation position and enter switch override explicitly."""
        if position not in range(4):
            raise ValueError("Ventilation position must be between Holiday and High")
        async with self._control_lock:
            await self._brink.start_switch_override(position)
            if position > 0:
                self.last_fan_position = position
            await self._manual_command_ended_boost()
        await self.async_request_refresh()

    async def set_direct_flow(self, airflow: int) -> None:
        """Store a direct airflow value without enabling direct override by itself."""
        if not _DIRECT_FLOW_MINIMUM <= airflow <= self.direct_flow_maximum:
            raise ValueError(
                "Requested airflow must be "
                f"{_DIRECT_FLOW_MINIMUM}–{self.direct_flow_maximum} m³/h "
                "for Flair 400"
            )
        async with self._control_lock:
            await self._brink.set_direct_flow(airflow)
            self.direct_flow = airflow
            if self.modbus_control_mode == 2:
                await self._manual_command_ended_boost()
        await self.async_request_refresh()

    async def _manual_command_ended_boost(self) -> None:
        """Stop tracking a temporary boost replaced by an explicit command."""
        if self.boost_active:
            self.boost_active = False
            self.boost_reason = "Manual Modbus command replaced temporary boost"
            self.boost_started = None
            await self._save_boost_state()

    async def set_standby_mode(self, value: int) -> None:
        if value not in (1, 2):
            raise ValueError("Standby command must be 1 (standby) or 2 (normal)")
        async with self._control_lock:
            await self._brink.set_standby_mode(value)
        await self.async_request_refresh()

    async def set_signal_output(self, value: int) -> None:
        if value not in range(4):
            raise ValueError("Signal output must be in the range 0..3")
        async with self._control_lock:
            await self._brink.set_signal_output(value)
        await self.async_request_refresh()

    async def set_bypass_mode(self, value: int) -> None:
        if value not in range(3):
            raise ValueError("Bypass mode must be Automatic, Closed, or Open")
        async with self._control_lock:
            await self._brink.set_bypass_mode(value)
        await self.async_request_refresh()

    async def reset_filter_warning(self) -> None:
        async with self._control_lock:
            await self._brink.reset_filter_warning()

    async def set_filter_warning_days(self, days: int) -> None:
        if not 1 <= days <= 365:
            raise ValueError("Filter warning days must be in the range 1..365")
        async with self._control_lock:
            await self._brink.set_filter_warning_days(days)
        await self.async_request_refresh()
