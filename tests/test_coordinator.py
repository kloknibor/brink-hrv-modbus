"""Tests for grouped polling, calculations, and temporary boost ownership."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.brink_ventilation.coordinator import (
    BrinkHrvModbusCoordinator,
    absolute_humidity,
    dew_point,
)
from custom_components.brink_ventilation.lib.brink import Brink, BrinkModbusError
from custom_components.brink_ventilation.sensors.advanced_sensors import (
    DESCRIPTIONS,
    BrinkDataSensor,
)


def snapshot(**overrides):
    """Return all dynamic snapshot values expected by the coordinator."""
    values = {
        "active_function": 10,
        "fan_control_type": 1,
        "ventilation_mode": 4,
        "supply_pressure": 12.3,
        "exhaust_pressure": 10.2,
        "supply_fan_status": 4,
        "supply_flow_setpoint": 100,
        "supply_flow": 95,
        "supply_fan_rpm": 1200,
        "supply_temperature": 18.0,
        "supply_humidity": 50,
        "exhaust_fan_status": 4,
        "exhaust_flow_setpoint": 100,
        "exhaust_flow": 90,
        "exhaust_fan_rpm": 1250,
        "exhaust_temperature": 21.0,
        "exhaust_humidity": 60,
        "bypass_status": 4,
        "bypass_step_position": 0,
        "preheater_status": 1,
        "preheater_capacity": 0,
        "frost_status": 2,
        "frost_heater_power": 0,
        "frost_fan_reduction": 0,
        "flow_switch_position": 2,
        "outside_temperature": 5.0,
        "dwelling_temperature": 22.0,
        "rht_humidity": None,
        "co2_sensor_1_status": 4,
        "co2_sensor_1": 700,
        "co2_sensor_2_status": 4,
        "co2_sensor_2": 800,
        "co2_sensor_3_status": 1,
        "co2_sensor_3": None,
        "co2_sensor_4_status": 1,
        "co2_sensor_4": None,
        "modbus_control_mode": 0,
        "fan_state": 2,
        "direct_flow": 150,
        "standby_mode": 0,
        "filter_dirty": False,
        "operating_hours": 100,
        "filter_used_in_hours": 10,
        "filter_used_volume": 1000,
        "lifetime_air_volume": 5000,
        "flow_preset_0": 50,
        "flow_preset_1": 100,
        "flow_preset_2": 150,
        "flow_preset_3": 300,
        "bypass_mode": 0,
        "filter_warning_days": 90,
        "rht_sensor_mode": 0,
        "co2_sensor_mode": 1,
        "signal_output": 0,
        "system_error_status": None,
        "active_incident": None,
    }
    values.update(overrides)
    return values


def mock_brink(values=None):
    brink = MagicMock(spec=Brink)
    brink.read_snapshot = AsyncMock(return_value=snapshot(**(values or {})))
    brink.get_modbus_control_switch_mode = AsyncMock(return_value=0)
    brink.start_switch_override = AsyncMock()
    brink.start_direct_flow_override = AsyncMock()
    brink.release_modbus_control = AsyncMock()
    brink.set_direct_flow = AsyncMock()
    brink.set_bypass_mode = AsyncMock()
    brink.set_signal_output = AsyncMock()
    brink.set_filter_warning_days = AsyncMock()
    brink.set_standby_mode = AsyncMock()
    brink.reset_filter_warning = AsyncMock()
    return brink


def test_advanced_sensor_keeps_runtime_mapping_separate_from_ha_metadata(hass):
    """The runtime mapping must not be treated as an HA EntityDescription."""
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator.fan_control_type = 1

    sensor = BrinkDataSensor(coordinator, "entry", DESCRIPTIONS[0])

    assert sensor.native_value == "Constant Flow"
    assert sensor._description is DESCRIPTIONS[0]
    assert getattr(sensor, "entity_description", None) is None


async def test_update_data_populates_flow_and_calculated_attributes(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()

    data = await coordinator._async_update_data()

    assert coordinator.supply_flow_setpoint == 100
    assert coordinator.supply_flow == 95
    assert coordinator.exhaust_flow_setpoint == 100
    assert coordinator.exhaust_flow == 90
    assert data["airflow_balance"] == 5
    assert data["airflow_imbalance_percent"] == 5.6
    assert data["heat_recovery_efficiency"] == 76.5
    assert data["recovered_thermal_power"] == 420


async def test_update_uses_grouped_snapshot_and_slow_interval(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()

    await coordinator._async_update_data()
    await coordinator._async_update_data()

    assert coordinator._brink.read_snapshot.await_args_list[0].kwargs == {
        "include_slow": True
    }
    assert coordinator._brink.read_snapshot.await_args_list[1].kwargs == {
        "include_slow": False
    }


async def test_start_and_stop_boost_use_owned_switch_override(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator.async_request_refresh = AsyncMock()

    await coordinator.async_start_boost("Humidity automation")

    coordinator._brink.start_switch_override.assert_awaited_once_with(3)
    assert coordinator.boost_active is True
    assert coordinator.boost_reason == "Humidity automation"

    coordinator._brink.get_modbus_control_switch_mode = AsyncMock(return_value=1)
    await coordinator.async_stop_boost()

    coordinator._brink.release_modbus_control.assert_awaited_once()
    assert coordinator.boost_active is False
    assert coordinator.boost_reason == "Returned to Auto / RF Control"


async def test_boost_does_not_overwrite_another_modbus_override(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator._brink.get_modbus_control_switch_mode = AsyncMock(return_value=2)

    with pytest.raises(BrinkModbusError, match="another Modbus override"):
        await coordinator.async_start_boost()

    coordinator._brink.start_switch_override.assert_not_awaited()


async def test_expired_owned_boost_releases_auto_control(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator.boost_active = True
    coordinator.boost_started = dt_util.utcnow() - timedelta(minutes=61)
    coordinator.boost_maximum_minutes = 60
    values = snapshot(modbus_control_mode=1)

    await coordinator._reconcile_boost(values, dt_util.utcnow())

    coordinator._brink.release_modbus_control.assert_awaited_once()
    assert coordinator.boost_active is False
    assert values["modbus_control_mode"] == 0


async def test_changed_mode_marks_boost_conflict_without_a_write(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator.boost_active = True

    await coordinator._reconcile_boost(
        snapshot(modbus_control_mode=2), dt_util.utcnow()
    )

    assert coordinator.boost_active is False
    assert coordinator.boost_conflict is True
    coordinator._brink.release_modbus_control.assert_not_awaited()


async def test_manual_command_replaces_tracked_boost_without_returning_auto(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.boost_active = True
    coordinator.boost_started = dt_util.utcnow()

    await coordinator.set_switch_position(1)

    coordinator._brink.start_switch_override.assert_awaited_once_with(1)
    coordinator._brink.release_modbus_control.assert_not_awaited()
    assert coordinator.boost_active is False
    assert coordinator.boost_reason == "Manual Modbus command replaced temporary boost"


async def test_direct_flow_is_validated_and_does_not_enable_override(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator.async_request_refresh = AsyncMock()

    with pytest.raises(ValueError, match="50–400"):
        await coordinator.set_direct_flow(401)

    await coordinator.set_direct_flow(200)

    coordinator._brink.set_direct_flow.assert_awaited_once_with(200)
    coordinator._brink.start_direct_flow_override.assert_not_awaited()


async def test_direct_control_requires_a_valid_requested_airflow(hass):
    coordinator = BrinkHrvModbusCoordinator(hass)
    coordinator._brink = mock_brink()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.direct_flow = 0

    with pytest.raises(ValueError, match="Requested Airflow"):
        await coordinator.set_modbus_control_mode(2)

    coordinator._brink.start_direct_flow_override.assert_not_awaited()


def test_humidity_math_requires_valid_matched_values():
    assert absolute_humidity(20, 50) == 8.64
    assert dew_point(20, 50) == 9.27
    assert absolute_humidity(None, 50) is None
    assert dew_point(20, 0) is None
