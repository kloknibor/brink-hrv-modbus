"""Unit tests for the Brink Modbus client wrapper."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.brink_ventilation.lib.brink import (
    Brink,
    BrinkModbusError,
    signed_16,
    unsigned_32,
)

DEVICE_ID = 20


def _brink_with_mock_client(register_value: int) -> tuple[Brink, MagicMock]:
    """A Brink instance wired to a mock Modbus client returning one register."""
    brink = Brink(DEVICE_ID)
    client = MagicMock()
    result = MagicMock()
    result.registers = [register_value]
    client.read_input_registers = AsyncMock(return_value=result)
    brink._client = client
    return brink, client


@pytest.mark.parametrize(
    ("method_name", "address"),
    [
        ("get_supply_fan_flow_setpoint", 4031),
        ("get_supply_fan_flow", 4032),
        ("get_exhaust_fan_flow_setpoint", 4041),
        ("get_exhaust_fan_flow", 4042),
    ],
)
async def test_flow_getter_reads_correct_register(method_name, address):
    brink, client = _brink_with_mock_client(register_value=350)

    value = await getattr(brink, method_name)()

    client.read_input_registers.assert_awaited_once_with(
        address=address, count=1, device_id=DEVICE_ID
    )
    assert value == 350


@pytest.mark.parametrize(
    "method_name",
    [
        "get_supply_fan_flow_setpoint",
        "get_supply_fan_flow",
        "get_exhaust_fan_flow_setpoint",
        "get_exhaust_fan_flow",
    ],
)
async def test_flow_getter_applies_no_scaling(method_name):
    """Unlike temperature registers, flow registers are already whole m3/h."""
    brink, _client = _brink_with_mock_client(register_value=123)

    value = await getattr(brink, method_name)()

    assert value == 123


async def test_get_active_function_reads_correct_register():
    brink, client = _brink_with_mock_client(register_value=8)

    value = await brink.get_active_function()

    client.read_input_registers.assert_awaited_once_with(
        address=4020, count=1, device_id=DEVICE_ID
    )
    assert value == 8


async def test_frost_fan_reduction_is_not_inverted():
    brink, client = _brink_with_mock_client(register_value=100)

    value = await brink.get_frost_fan_reduction()

    client.read_input_registers.assert_awaited_once_with(
        address=4072, count=1, device_id=DEVICE_ID
    )
    assert value == 100


def test_signed_and_unsigned_register_conversions():
    assert signed_16(0x000A) == 10
    assert signed_16(0xFFF6) == -10
    assert unsigned_32(0x0001, 0x0002) == 65538
    assert unsigned_32(0xFFFF, 0xFFFF) == 4_294_967_295


async def test_snapshot_groups_contiguous_dynamic_input_blocks():
    brink = Brink(DEVICE_ID)
    client = MagicMock()

    input_blocks = {
        4020: [12, 1, 4, 123, 0xFFF6],
        4030: [4, 100, 95, 0, 1200, 0, 185, 55],
        4040: [4, 100, 90, 0, 1250, 0, 210, 60],
        4050: [4, 7],
        4060: [1, 0],
        4070: [2, 0, 0],
        4080: [2, 50, 9999, 0],
        4200: [4, 700, 1, 999, 4, 800, 0, 777],
    }

    def input_response(*, address, count, device_id):
        assert device_id == DEVICE_ID
        result = MagicMock()
        result.registers = input_blocks[address]
        result.isError.return_value = False
        assert len(result.registers) == count
        return result

    def holding_response(*, address, count, device_id):
        assert (address, count, device_id) == (8000, 4, DEVICE_ID)
        result = MagicMock()
        result.registers = [0, 2, 150, 0]
        result.isError.return_value = False
        return result

    client.read_input_registers = AsyncMock(side_effect=input_response)
    client.read_holding_registers = AsyncMock(side_effect=holding_response)
    brink._client = client

    data = await brink.read_snapshot()

    assert data["supply_pressure"] == 12.3
    assert data["exhaust_pressure"] == -1.0
    assert data["supply_temperature"] == 18.5
    assert data["outside_temperature"] == 5.0
    assert data["dwelling_temperature"] is None
    assert data["co2_sensor_1"] == 700
    assert data["co2_sensor_2"] is None
    assert data["co2_sensor_3"] == 800
    assert data["co2_sensor_4"] is None
    assert [
        call.kwargs["address"] for call in client.read_input_registers.await_args_list
    ] == [4020, 4030, 4040, 4050, 4060, 4070, 4080, 4200]


async def test_slow_snapshot_keeps_unsupported_error_registers_optional():
    brink = Brink(DEVICE_ID)
    client = MagicMock()
    dynamic = {
        4020: [10, 1, 4, 0, 0],
        4030: [4, 100, 100, 0, 1, 0, 200, 50],
        4040: [4, 100, 100, 0, 1, 0, 210, 60],
        4050: [4, 0],
        4060: [1, 0],
        4070: [2, 0, 0],
        4080: [2, 0, 9999, 0],
        4200: [1, 0] * 4,
        4100: [0],
        4113: [0, 10, 5, 0, 20, 0, 30],
        4800: [0, 0],
    }
    holding = {
        8000: [0, 2, 150, 0],
        6000: [50, 100, 150, 300],
        6100: [0],
        6120: [90],
        6140: [0],
        6150: [1],
        6170: [0],
    }

    def input_response(*, address, count, device_id):
        if address == 4800:
            result = MagicMock()
            result.isError.return_value = True
            return result
        result = MagicMock()
        result.registers = dynamic[address]
        result.isError.return_value = False
        return result

    def holding_response(*, address, count, device_id):
        result = MagicMock()
        result.registers = holding[address]
        result.isError.return_value = False
        return result

    client.read_input_registers = AsyncMock(side_effect=input_response)
    client.read_holding_registers = AsyncMock(side_effect=holding_response)
    brink._client = client

    data = await brink.read_snapshot(include_slow=True)

    assert data["operating_hours"] == 10
    assert data["filter_used_volume"] == 20
    assert data["lifetime_air_volume"] == 30
    assert data["system_error_status"] is None
    assert data["active_incident"] is None


async def test_switch_override_writes_position_before_control_and_verifies():
    brink = Brink(DEVICE_ID)
    client = MagicMock()
    holding = {8000: 0, 8001: 0}

    async def write(*, address, value, device_id):
        holding[address] = value
        result = MagicMock()
        result.isError.return_value = False
        return result

    async def read(*, address, count, device_id):
        result = MagicMock()
        result.registers = [holding[address]]
        result.isError.return_value = False
        return result

    client.write_register = AsyncMock(side_effect=write)
    client.read_holding_registers = AsyncMock(side_effect=read)
    brink._client = client

    await brink.start_switch_override(3)

    assert [
        call.kwargs["address"] for call in client.write_register.await_args_list
    ] == [8001, 8000]
    assert holding == {8000: 1, 8001: 3}


async def test_write_readback_mismatch_is_an_error():
    brink = Brink(DEVICE_ID)
    client = MagicMock()
    write_result = MagicMock()
    write_result.isError.return_value = False
    client.write_register = AsyncMock(return_value=write_result)
    read_result = MagicMock()
    read_result.registers = [0]
    read_result.isError.return_value = False
    client.read_holding_registers = AsyncMock(return_value=read_result)
    brink._client = client

    with pytest.raises(BrinkModbusError, match="read back"):
        await brink.write_and_verify(8000, 1)


async def test_transport_timeout_is_not_interpreted_as_zero():
    brink = Brink(DEVICE_ID)
    client = MagicMock()
    client.read_input_registers = AsyncMock(side_effect=OSError("timed out"))
    client.connect = AsyncMock(return_value=False)
    brink._client = client

    with pytest.raises(BrinkModbusError, match="timed out"):
        await brink.get_supply_fan_flow()
