"""Additional documented and calculated Brink sensor entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.helpers.entity import EntityCategory

from ..entity import BrinkEntity

ACTIVE_FUNCTION = {
    0: "Standby",
    1: "Bootloader",
    2: "Reserved",
    3: "Reserved",
    4: "Manual",
    5: "Holiday",
    6: "Night Ventilation",
    7: "Party",
    8: "Bypass Boost",
    9: "Normal Boost",
    10: "Auto CO₂",
    11: "Auto eBus",
    12: "Auto Modbus",
    13: "Auto LAN/WLAN Portal",
    14: "Auto LAN/WLAN Local",
}
FAN_CONTROL = {
    0: "Initializing",
    1: "Constant Flow",
    2: "Constant PWM",
    3: "Off",
    4: "Error",
    5: "Mass Balance",
    6: "Standby",
}
VENTILATION_MODE = {0: "Holiday", 1: "Low", 2: "Normal", 3: "High", 4: "Auto"}
FAN_STATUS = {
    2: "No Communication",
    3: "Idle",
    4: "Running",
    5: "Blocked",
    6: "Fan Error",
}
BYPASS_STATUS = {0: "Initialize", 1: "Open", 2: "Closing", 3: "Open", 4: "Closed"}
PREHEATER_STATUS = {0: "Initialize", 1: "Inactive", 2: "Active", 3: "Test Mode"}
FROST_STATUS = {
    0: "Not Initialized",
    1: "Power Up Delay",
    2: "No Frost",
    3: "No Frost Delay",
    4: "Frost Control Start Delay",
    5: "Wait for Icing",
    6: "Ice Detected Delay",
    7: "Heating",
    8: "Wait for Free Heater",
    9: "Fan Control Start Delay",
    10: "Fan Control Wait Delay",
    11: "Fan Control",
    12: "Fan Off Delay",
    13: "Fan Off",
    14: "Fan Restarting",
    15: "Error",
    16: "Test Mode",
}
SYSTEM_ERROR = {
    0: "No Error",
    1: "Warning",
    2: "Non-blocking Error",
    3: "Blocking Error",
}


@dataclass(frozen=True, kw_only=True)
class BrinkSensorDescription:
    key: str
    name: str
    suffix: str
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    entity_category: EntityCategory | None = None
    disabled_by_default: bool = False
    enum: dict[int, str] | None = None


class BrinkDataSensor(BrinkEntity, SensorEntity):
    """A coordinator-backed numeric or enum sensor."""

    _attr_should_poll = False

    def __init__(
        self, coordinator: Any, entry_id: str, description: BrinkSensorDescription
    ) -> None:
        super().__init__(coordinator, entry_id)
        # This is deliberately not assigned to ``entity_description``.
        # Home Assistant reserves that attribute for SensorEntityDescription
        # instances and reads fields such as ``translation_key`` from it while
        # adding an entity.  BrinkSensorDescription is our runtime mapping,
        # not Home Assistant's metadata object.
        self._description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{entry_id}_{description.suffix}"
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = not description.disabled_by_default
        if description.enum is not None:
            self._attr_options = [*description.enum.values(), "Unknown"]

    @property
    def native_value(self) -> Any:
        value = getattr(self.coordinator, self._description.key, None)
        if self._description.enum is None or value is None:
            return value
        return self._description.enum.get(value, "Unknown")


DESCRIPTIONS: tuple[BrinkSensorDescription, ...] = (
    BrinkSensorDescription(
        key="fan_control_type",
        name="Fan Control Type",
        suffix="fan_control_type",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        enum=FAN_CONTROL,
    ),
    BrinkSensorDescription(
        key="ventilation_mode",
        name="Ventilation Mode",
        suffix="ventilation_mode",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        enum=VENTILATION_MODE,
    ),
    BrinkSensorDescription(
        key="supply_pressure",
        name="Supply Pressure",
        suffix="supply_pressure",
        unit=UnitOfPressure.PA,
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="exhaust_pressure",
        name="Exhaust Pressure",
        suffix="exhaust_pressure",
        unit=UnitOfPressure.PA,
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="supply_fan_rpm",
        name="Supply Fan RPM",
        suffix="supply_fan_rpm",
        unit="rpm",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="exhaust_fan_rpm",
        name="Exhaust Fan RPM",
        suffix="exhaust_fan_rpm",
        unit="rpm",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="bypass_step_position",
        name="Bypass Step Position",
        suffix="bypass_step_position",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="outside_temperature",
        name="Outside Air Temperature",
        suffix="outside_air_temperature",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    BrinkSensorDescription(
        key="dwelling_temperature",
        name="Dwelling Air Temperature",
        suffix="dwelling_air_temperature",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        disabled_by_default=True,
    ),
    BrinkSensorDescription(
        key="indoor_extract_temperature",
        name="Indoor Extract Temperature Used for Estimate",
        suffix="indoor_extract_temperature_used_for_estimate",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        disabled_by_default=True,
    ),
    BrinkSensorDescription(
        key="rht_humidity",
        name="RHT Humidity",
        suffix="rht_humidity",
        unit=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        disabled_by_default=True,
    ),
    BrinkSensorDescription(
        key="lifetime_air_volume",
        name="Lifetime Air Volume",
        suffix="lifetime_air_volume",
        unit=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="flow_preset_0",
        name="Configured Flow Holiday",
        suffix="configured_flow_holiday",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="flow_preset_1",
        name="Configured Flow Low",
        suffix="configured_flow_low",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="flow_preset_2",
        name="Configured Flow Normal",
        suffix="configured_flow_normal",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="flow_preset_3",
        name="Configured Flow High",
        suffix="configured_flow_high",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="co2_sensor_mode",
        name="CO₂ Sensor Mode",
        suffix="co2_sensor_mode",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        enum={0: "Off", 1: "On"},
    ),
    BrinkSensorDescription(
        key="rht_sensor_mode",
        name="RHT Sensor Mode",
        suffix="rht_sensor_mode",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        disabled_by_default=True,
        enum={0: "Off", 1: "On"},
    ),
    BrinkSensorDescription(
        key="system_error_status",
        name="System Error Status",
        suffix="system_error_status",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        disabled_by_default=True,
        enum=SYSTEM_ERROR,
    ),
    BrinkSensorDescription(
        key="active_incident",
        name="Active Incident",
        suffix="active_incident",
        entity_category=EntityCategory.DIAGNOSTIC,
        disabled_by_default=True,
    ),
    BrinkSensorDescription(
        key="supply_absolute_humidity",
        name="Supply Absolute Humidity",
        suffix="supply_absolute_humidity",
        unit="g/m³",
    ),
    BrinkSensorDescription(
        key="exhaust_absolute_humidity",
        name="Exhaust Absolute Humidity",
        suffix="exhaust_absolute_humidity",
        unit="g/m³",
    ),
    BrinkSensorDescription(
        key="absolute_humidity_difference",
        name="Exhaust minus Supply Absolute Humidity",
        suffix="absolute_humidity_difference",
        unit="g/m³",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="supply_dew_point",
        name="Supply Dew Point",
        suffix="supply_dew_point",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    BrinkSensorDescription(
        key="exhaust_dew_point",
        name="Exhaust Dew Point",
        suffix="exhaust_dew_point",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    BrinkSensorDescription(
        key="exhaust_absolute_humidity_baseline",
        name="Exhaust Absolute Humidity Baseline",
        suffix="exhaust_absolute_humidity_baseline",
        unit="g/m³",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="exhaust_humidity_baseline_deviation",
        name="Exhaust Humidity Baseline Deviation",
        suffix="exhaust_humidity_baseline_deviation",
        unit="g/m³",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="exhaust_humidity_rise_rate",
        name="Exhaust Humidity Rise Rate",
        suffix="exhaust_humidity_rise_rate",
        unit="g/m³/min",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="airflow_balance",
        name="Airflow Balance",
        suffix="airflow_balance",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
    ),
    BrinkSensorDescription(
        key="airflow_imbalance_percent",
        name="Airflow Imbalance",
        suffix="airflow_imbalance",
        unit=PERCENTAGE,
    ),
    BrinkSensorDescription(
        key="supply_setpoint_deviation",
        name="Supply Airflow Setpoint Deviation",
        suffix="supply_airflow_setpoint_deviation",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="exhaust_setpoint_deviation",
        name="Exhaust Airflow Setpoint Deviation",
        suffix="exhaust_airflow_setpoint_deviation",
        unit=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="supply_rpm_per_airflow",
        name="Supply RPM per Airflow",
        suffix="supply_rpm_per_airflow",
        unit="rpm/(m³/h)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="exhaust_rpm_per_airflow",
        name="Exhaust RPM per Airflow",
        suffix="exhaust_rpm_per_airflow",
        unit="rpm/(m³/h)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="heat_recovery_efficiency",
        name="Estimated Heat Recovery Efficiency",
        suffix="estimated_heat_recovery_efficiency",
        unit=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="recovered_thermal_power",
        name="Estimated Recovered Thermal Power",
        suffix="estimated_recovered_thermal_power",
        unit=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BrinkSensorDescription(
        key="boost_reason",
        name="Boost Reason",
        suffix="boost_reason",
        state_class=None,
    ),
    BrinkSensorDescription(
        key="boost_elapsed_minutes",
        name="Boost Elapsed Time",
        suffix="boost_elapsed_time",
        unit=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    BrinkSensorDescription(
        key="boost_remaining_minutes",
        name="Boost Remaining Time",
        suffix="boost_remaining_time",
        unit=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
)
