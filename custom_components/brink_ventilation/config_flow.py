"""Config flow for the Brink HRV Modbus integration."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from pymodbus.exceptions import ConnectionException

from .const import (
    CONF_HOST,
    CONF_INDOOR_TEMPERATURE_ENTITY,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)
from .lib.brink import Brink


class BrinkHraModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up native TCP-to-RTU Brink Modbus access."""

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

            brink = None
            try:
                brink = await Brink.initialize(
                    user_input[CONF_HOST], user_input[CONF_PORT], 20
                )
            except ConnectionException:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
            finally:
                if brink is not None:
                    brink.close()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return BrinkHrvModbusOptionsFlow(config_entry)


class BrinkHrvModbusOptionsFlow(OptionsFlow):
    """Optional external temperature source for a meaningful efficiency estimate."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            entity_id = user_input.get(CONF_INDOOR_TEMPERATURE_ENTITY, "").strip()
            return self.async_create_entry(
                title="",
                data={CONF_INDOOR_TEMPERATURE_ENTITY: entity_id or None},
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INDOOR_TEMPERATURE_ENTITY,
                        default=self.config_entry.options.get(
                            CONF_INDOOR_TEMPERATURE_ENTITY, ""
                        ),
                    ): str,
                }
            ),
        )
