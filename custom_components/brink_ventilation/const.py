"""Constants for the Brink HRV Modbus integration."""

DOMAIN = "brink_ventilation"
CONF_HOST = "host"
CONF_PORT = "port"
DEFAULT_PORT = 502
DEFAULT_NAME = "Brink HRV Modbus (kloknibor)"
# Keep the registry device name stable so a new fork release does not change
# Home Assistant's generated object-id prefix or make dashboard examples drift.
DEVICE_NAME = "Brink HRV Modbus"
CONF_INDOOR_TEMPERATURE_ENTITY = "indoor_temperature_entity"
