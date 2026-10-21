"""Safe asynchronous Modbus access for Brink UWA2-B appliances.

Brink's published register numbers are used as-is. Existing installations of
this integration use those numbers successfully with PyModbus TCP gateways, so
they must not be decremented for the often-confusing 0/1 based Modbus notation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException


class BrinkModbusError(ModbusException):
    """A Modbus request failed or returned an exception response."""


def signed_16(value: int) -> int:
    """Convert one unsigned Modbus word to a signed 16-bit integer."""
    return value - 0x10000 if value & 0x8000 else value


def unsigned_32(high_word: int, low_word: int) -> int:
    """Decode the documented high-word/low-word Brink 32-bit counters."""
    return (high_word << 16) | low_word


class Brink:
    """One serialized Modbus TCP connection to one Brink appliance."""

    def __init__(self, device_id: int = 20) -> None:
        self._device_id = device_id
        self._client: AsyncModbusTcpClient | None = None
        self._io_lock = asyncio.Lock()

    @classmethod
    async def initialize(cls, host: str, port: int, device_id: int) -> Brink:
        """Connect to a native Modbus TCP gateway."""
        self = cls(device_id)
        self._client = AsyncModbusTcpClient(host, port=port)
        if not await self._client.connect():
            raise ConnectionException(f"Could not connect to {host}:{port}")
        return self

    def close(self) -> None:
        """Close the underlying Modbus connection."""
        if self._client is not None:
            self._client.close()

    @property
    def _modbus(self) -> AsyncModbusTcpClient:
        if self._client is None:
            raise ConnectionException("Modbus client has not been initialized")
        return self._client

    @staticmethod
    def _validate_response(response: Any, operation: str) -> Any:
        """Turn PyModbus exception responses into real exceptions."""
        is_error = response.isError() if hasattr(response, "isError") else False
        # PyModbus returns an actual bool. Checking identity keeps basic mocks
        # from accidentally becoming failures just because MagicMock is truthy.
        if is_error is True:
            raise BrinkModbusError(f"{operation} failed: {response}")
        if not hasattr(response, "registers") and operation.startswith("read"):
            raise BrinkModbusError(f"{operation} returned no registers")
        return response

    async def _execute(
        self, operation: Callable[[], Awaitable[Any]], label: str
    ) -> Any:
        """Run an operation and reconnect once after a transport failure."""
        try:
            return self._validate_response(await operation(), label)
        except (ConnectionException, OSError) as err:
            # A Waveshare gateway can drop an idle TCP session. One retry is
            # sufficient for that case without a busy reconnect loop.
            if await self._modbus.connect():
                try:
                    return self._validate_response(await operation(), label)
                except (ConnectionException, OSError, ModbusException) as retry_err:
                    raise BrinkModbusError(
                        f"{label} failed after reconnect: {retry_err}"
                    ) from retry_err
            raise BrinkModbusError(f"{label} failed: {err}") from err
        except ModbusException:
            raise

    async def _read_input_unlocked(self, address: int, count: int = 1) -> list[int]:
        response = await self._execute(
            lambda: self._modbus.read_input_registers(
                address=address, count=count, device_id=self._device_id
            ),
            f"read input registers {address}+{count}",
        )
        registers = list(response.registers)
        if len(registers) != count:
            raise BrinkModbusError(
                f"read input registers {address}+{count} returned "
                f"{len(registers)} words"
            )
        return registers

    async def _read_holding_unlocked(self, address: int, count: int = 1) -> list[int]:
        response = await self._execute(
            lambda: self._modbus.read_holding_registers(
                address=address, count=count, device_id=self._device_id
            ),
            f"read holding registers {address}+{count}",
        )
        registers = list(response.registers)
        if len(registers) != count:
            raise BrinkModbusError(
                f"read holding registers {address}+{count} returned "
                f"{len(registers)} words"
            )
        return registers

    async def _write_unlocked(self, address: int, value: int) -> None:
        await self._execute(
            lambda: self._modbus.write_register(
                address=address, value=value, device_id=self._device_id
            ),
            f"write holding register {address}",
        )

    async def read_input_registers(self, address: int, count: int = 1) -> list[int]:
        """Read a documented FC04 block through the serialized connection."""
        async with self._io_lock:
            return await self._read_input_unlocked(address, count)

    async def read_holding_registers(self, address: int, count: int = 1) -> list[int]:
        """Read a documented FC03 block through the serialized connection."""
        async with self._io_lock:
            return await self._read_holding_unlocked(address, count)

    async def write_holding_register(self, address: int, value: int) -> None:
        """Write one FC06 holding register through the serialized connection."""
        async with self._io_lock:
            await self._write_unlocked(address, value)

    async def _write_and_verify_unlocked(self, address: int, value: int) -> None:
        await self._write_unlocked(address, value)
        actual = (await self._read_holding_unlocked(address))[0]
        if actual != value:
            raise BrinkModbusError(
                f"holding register {address} read back {actual}, expected {value}"
            )

    async def write_and_verify(self, address: int, value: int) -> None:
        """Write then read back a holding register while retaining the I/O lock."""
        async with self._io_lock:
            await self._write_and_verify_unlocked(address, value)

    async def read_snapshot(
        self, include_slow: bool = False
    ) -> dict[str, int | float | None]:
        """Read safe contiguous documented blocks and decode their values.

        The dynamic snapshot is nine transactions instead of the old 30+
        per-register transactions. Slow counters/settings are added by the
        coordinator every minute. Firmware-specific error registers are
        optional: an exception there never makes normal telemetry unavailable.
        """
        async with self._io_lock:
            a4020 = await self._read_input_unlocked(4020, 5)
            a4030 = await self._read_input_unlocked(4030, 8)
            a4040 = await self._read_input_unlocked(4040, 8)
            a4050 = await self._read_input_unlocked(4050, 2)
            a4060 = await self._read_input_unlocked(4060, 2)
            a4070 = await self._read_input_unlocked(4070, 3)
            a4080 = await self._read_input_unlocked(4080, 4)
            a4200 = await self._read_input_unlocked(4200, 8)
            a8000 = await self._read_holding_unlocked(8000, 4)
            data: dict[str, int | float | None] = {
                "active_function": a4020[0],
                "fan_control_type": a4020[1],
                "ventilation_mode": a4020[2],
                "supply_pressure": signed_16(a4020[3]) / 10,
                "exhaust_pressure": signed_16(a4020[4]) / 10,
                "supply_fan_status": a4030[0],
                "supply_flow_setpoint": a4030[1],
                "supply_flow": a4030[2],
                "supply_fan_rpm": a4030[4],
                "supply_temperature": signed_16(a4030[6]) / 10,
                "supply_humidity": self._humidity(a4030[7]),
                "exhaust_fan_status": a4040[0],
                "exhaust_flow_setpoint": a4040[1],
                "exhaust_flow": a4040[2],
                "exhaust_fan_rpm": a4040[4],
                "exhaust_temperature": signed_16(a4040[6]) / 10,
                "exhaust_humidity": self._humidity(a4040[7]),
                "bypass_status": a4050[0],
                "bypass_step_position": a4050[1],
                "preheater_status": a4060[0],
                "preheater_capacity": a4060[1],
                "frost_status": a4070[0],
                "frost_heater_power": a4070[1],
                "frost_fan_reduction": a4070[2],
                "flow_switch_position": a4080[0],
                "outside_temperature": signed_16(a4080[1]) / 10,
                "dwelling_temperature": self._temperature_or_none(a4080[2]),
                "rht_humidity": self._humidity(a4080[3]),
                "co2_sensor_1_status": a4200[0],
                "co2_sensor_1": self._co2_value(a4200[0], a4200[1]),
                "co2_sensor_2_status": a4200[2],
                "co2_sensor_2": self._co2_value(a4200[2], a4200[3]),
                "co2_sensor_3_status": a4200[4],
                "co2_sensor_3": self._co2_value(a4200[4], a4200[5]),
                "co2_sensor_4_status": a4200[6],
                "co2_sensor_4": self._co2_value(a4200[6], a4200[7]),
                "modbus_control_mode": a8000[0],
                "fan_state": a8000[1],
                "direct_flow": a8000[2],
                "standby_mode": a8000[3],
            }
            if include_slow:
                data.update(await self._read_slow_unlocked())
        return data

    @staticmethod
    def _humidity(value: int) -> int | None:
        """Validate documented humidity values before publishing a percentage."""
        return value if 0 <= value <= 100 else None

    @staticmethod
    def _temperature_or_none(value: int) -> float | None:
        """9999 means an optional NTC is not connected."""
        return None if value == 9999 else signed_16(value) / 10

    @staticmethod
    def _co2_value(status: int, value: int) -> int | None:
        """Only Running is a measuring state; stale values are misleading."""
        return value if status == 4 else None

    async def _read_slow_unlocked(self) -> dict[str, int | float | None]:
        """Read lower-frequency blocks. Caller holds ``_io_lock``."""
        a4100 = await self._read_input_unlocked(4100)
        a4113 = await self._read_input_unlocked(4113, 7)
        h6000 = await self._read_holding_unlocked(6000, 4)
        h6100 = await self._read_holding_unlocked(6100)
        h6120 = await self._read_holding_unlocked(6120)
        h6140 = await self._read_holding_unlocked(6140)
        h6150 = await self._read_holding_unlocked(6150)
        h6170 = await self._read_holding_unlocked(6170)
        data: dict[str, int | float | None] = {
            "filter_dirty": a4100[0] == 1,
            "operating_hours": unsigned_32(a4113[0], a4113[1]),
            "filter_used_in_hours": a4113[2],
            "filter_used_volume": unsigned_32(a4113[3], a4113[4]),
            "lifetime_air_volume": unsigned_32(a4113[5], a4113[6]),
            "flow_preset_0": h6000[0],
            "flow_preset_1": h6000[1],
            "flow_preset_2": h6000[2],
            "flow_preset_3": h6000[3],
            "bypass_mode": h6100[0],
            "filter_warning_days": h6120[0],
            "rht_sensor_mode": h6140[0],
            "co2_sensor_mode": h6150[0],
            "signal_output": h6170[0],
        }
        try:
            a4800 = await self._read_input_unlocked(4800, 2)
        except (BrinkModbusError, ModbusException):
            # 4800/4801 require specific firmware. Absence is not "no error".
            data["system_error_status"] = None
            data["active_incident"] = None
        else:
            data["system_error_status"] = a4800[0]
            data["active_incident"] = a4800[1]
        return data


    async def start_switch_override(self, position: int) -> None:
        """Enable Modbus switch control before setting the position."""
        if position not in range(4):
            raise ValueError("switch position must be in the range 0..3")
    
        async with self._io_lock:
            await self._write_and_verify_unlocked(8000, 1)
            await self._write_and_verify_unlocked(8001, position)


    async def start_direct_flow_override(self, airflow: int) -> None:
        """Set 8002, enable 8000=2, and verify both documented readbacks."""
        if airflow < 0 or airflow > 65535:
            raise ValueError("airflow must fit an unsigned Modbus word")
        async with self._io_lock:
            await self._write_and_verify_unlocked(8002, airflow)
            await self._write_and_verify_unlocked(8000, 2)

    async def release_modbus_control(self) -> None:
        """Return priority to the Brink's local/RF/CO₂ control."""
        async with self._io_lock:
            await self._write_and_verify_unlocked(8000, 0)

    # The original single-register client API stays public for custom users.
    # The coordinator itself uses read_snapshot() for grouped polling.
    async def _input_value(self, address: int) -> int:
        return (await self.read_input_registers(address))[0]

    async def _holding_value(self, address: int) -> int:
        return (await self.read_holding_registers(address))[0]

    async def get_supply_fan_status(self) -> int:
        return await self._input_value(4030)

    async def get_supply_fan_temperature(self) -> float:
        return signed_16(await self._input_value(4036)) / 10

    async def get_supply_fan_relative_humidity(self) -> int | None:
        return self._humidity(await self._input_value(4037))

    async def get_supply_fan_flow_setpoint(self) -> int:
        return await self._input_value(4031)

    async def get_supply_fan_flow(self) -> int:
        return await self._input_value(4032)

    async def get_supply_fan_rpm(self) -> int:
        return await self._input_value(4034)

    async def get_supply_pressure(self) -> float:
        return signed_16(await self._input_value(4023)) / 10

    async def get_exhaust_fan_status(self) -> int:
        return await self._input_value(4040)

    async def get_exhaust_fan_temperature(self) -> float:
        return signed_16(await self._input_value(4046)) / 10

    async def get_exhaust_fan_relative_humidity(self) -> int | None:
        return self._humidity(await self._input_value(4047))

    async def get_exhaust_fan_flow_setpoint(self) -> int:
        return await self._input_value(4041)

    async def get_exhaust_fan_flow(self) -> int:
        return await self._input_value(4042)

    async def get_exhaust_fan_rpm(self) -> int:
        return await self._input_value(4044)

    async def get_exhaust_pressure(self) -> float:
        return signed_16(await self._input_value(4024)) / 10

    async def get_active_function(self) -> int:
        return await self._input_value(4020)

    async def get_fan_control_type(self) -> int:
        return await self._input_value(4021)

    async def get_ventilation_mode(self) -> int:
        return await self._input_value(4022)

    async def get_bypass_status(self) -> int:
        return await self._input_value(4050)

    async def get_bypass_step_position(self) -> int:
        return await self._input_value(4051)

    async def get_preheater_status(self) -> int:
        return await self._input_value(4060)

    async def get_preheater_capacity(self) -> int:
        return await self._input_value(4061)

    async def get_frost_status(self) -> int:
        return await self._input_value(4070)

    async def get_frost_heater_power(self) -> int:
        return await self._input_value(4071)

    async def get_frost_fan_reduction(self) -> int:
        return await self._input_value(4072)

    async def get_outside_temperature(self) -> float:
        return signed_16(await self._input_value(4081)) / 10

    async def get_filter_dirty(self) -> bool:
        return await self._input_value(4100) == 1

    async def get_operating_hours(self) -> int:
        value = await self.read_input_registers(4113, 2)
        return unsigned_32(*value)

    async def get_filter_used_in_hours(self) -> int:
        return await self._input_value(4115)

    async def get_filter_used_in_cubic_meters(self) -> int:
        value = await self.read_input_registers(4116, 2)
        return unsigned_32(*value)

    async def get_filter_used_in_cubic_meters_per_hour(self) -> int:
        """Deprecated alias; the documented counter is volume (m³)."""
        return await self.get_filter_used_in_cubic_meters()

    async def get_total_air_volume(self) -> int:
        value = await self.read_input_registers(4118, 2)
        return unsigned_32(*value)

    async def get_CO2_sensor_1_status(self) -> int:
        return await self._input_value(4200)

    async def get_CO2_sensor_2_status(self) -> int:
        return await self._input_value(4202)

    async def get_CO2_sensor_3_status(self) -> int:
        return await self._input_value(4204)

    async def get_CO2_sensor_4_status(self) -> int:
        return await self._input_value(4206)

    async def get_CO2_sensor_1(self) -> int | None:
        return self._co2_value(
            await self.get_CO2_sensor_1_status(), await self._input_value(4201)
        )

    async def get_CO2_sensor_2(self) -> int | None:
        return self._co2_value(
            await self.get_CO2_sensor_2_status(), await self._input_value(4203)
        )

    async def get_CO2_sensor_3(self) -> int | None:
        return self._co2_value(
            await self.get_CO2_sensor_3_status(), await self._input_value(4205)
        )

    async def get_CO2_sensor_4(self) -> int | None:
        return self._co2_value(
            await self.get_CO2_sensor_4_status(), await self._input_value(4207)
        )

    async def get_modbus_control_switch_mode(self) -> int:
        return await self._holding_value(8000)

    async def get_switch_position(self) -> int:
        return await self._holding_value(8001)

    async def get_direct_flow(self) -> int:
        return await self._holding_value(8002)

    async def get_standby_mode(self) -> int:
        return await self._holding_value(8003)

    async def get_filter_warning_days(self) -> int:
        return await self._holding_value(6120)

    async def get_signal_output(self) -> int:
        return await self._holding_value(6170)

    async def get_bypass_mode(self) -> int:
        return await self._holding_value(6100)

    async def set_modbus_control_switch_mode(self, value: int) -> None:
        await self.write_and_verify(8000, value)

    async def set_switch_position(self, value: int) -> None:
        await self.write_and_verify(8001, value)

    async def set_direct_flow(self, value: int) -> None:
        await self.write_and_verify(8002, value)

    async def set_standby_mode(self, value: int) -> None:
        await self.write_and_verify(8003, value)

    async def set_filter_warning_days(self, value: int) -> None:
        await self.write_and_verify(6120, value)

    async def set_signal_output(self, value: int) -> None:
        await self.write_and_verify(6170, value)

    async def set_bypass_mode(self, value: int) -> None:
        await self.write_and_verify(6100, value)

    async def reset_filter_warning(self) -> None:
        await self.write_holding_register(8010, 1)
