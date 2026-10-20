[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/kloknibor/brink-hrv-modbus?style=for-the-badge)](https://github.com/kloknibor/brink-hrv-modbus/releases)

# Brink HRV Modbus (kloknibor)

Home Assistant integration for Brink heat-recovery ventilation appliances with a
UWA2-B or compatible interface, connected through a native Modbus TCP-to-RTU
gateway. This is the maintained **kloknibor** fork of
[jarcovlieger/brink-hrv-modbus](https://github.com/jarcovlieger/brink-hrv-modbus).
It retains the `brink_ventilation` domain, config entries, device identifiers,
and existing entity unique IDs so an upstream installation can be upgraded in
place. The original author retains attribution and the project remains MIT
licensed.

The integration has been developed for Flair equipment, including Flair 400.
It does not need a UWA2-E Plus PCB. A Flair 400 with UWA2-B uses X15. Brink
uses RTU on that connection; this integration deliberately keeps Modbus TCP
between Home Assistant and the Ethernet gateway.

## Install or upgrade with HACS

1. In HACS, add `https://github.com/kloknibor/brink-hrv-modbus` as a custom
   integration repository, or open the repository with HACS.
2. Download/update **Brink HRV Modbus (kloknibor)** and restart Home Assistant.
3. Existing `brink_ventilation` config entries are discovered unchanged. Do
   not add a second integration entry for the same gateway.

For a manual install, copy `custom_components/brink_ventilation` to the same
directory in your Home Assistant configuration and restart Home Assistant.

## Gateway and appliance setup

The integration never contains a gateway IP address. Add the IP address and
TCP port for your own TCP-to-RTU gateway in the config flow. For the commonly
used Waveshare RS485 TO POE ETH (B), configure transparent Modbus TCP-to-RTU
with the Brink's settings. A typical Flair 400 UWA2-B configuration is slave
ID 20, 19200 baud, 8E1, connected to X15; verify the actual appliance settings
at menu 14.1–14.4 before use.

The authoritative register source is Brink's
[UWA2-B/UWA2-E Modbus reference](https://www.brinkclimatesystems.nl/documenten/modbus-uwa2-b-uwa2-e-installation-regulations-gb-614882.pdf).
This integration intentionally uses the documented `4000`/`6000`/`8000`
numbers unchanged because that is the addressing convention the original
working TCP integration used.

Wireless Brink RF CO₂ sensors remain local Brink devices. Enable CO₂ sensor
mode on the appliance (parameter 6.1 / holding register 6150) if readings at
4200–4207 are wanted. The integration only reads that setting; it never
enables, disables, or overwrites RF CO₂ configuration. CO₂ ppm is published
only while the corresponding sensor reports `Running`; `Error`, `Not
Initialized`, and warm-up states deliberately publish no stale ppm value.

## Control priority and safety

Fresh installs start in monitoring mode. No Modbus override is enabled at
startup. All writes use FC06, are serialized with polls, and are read back
before Home Assistant reports success.

`Modbus Control Mode` reads register 8000 and has three options:

| Option | Register value | Result |
| --- | ---: | --- |
| Auto / RF Control | 0 | Releases Modbus priority and lets RF controllers and CO₂ regulation decide airflow. |
| Manual Switch | 1 | Uses the requested Holiday/Low/Normal/High switch position at 8001. |
| Direct Flow | 2 | Uses requested airflow at 8002; RF controls, humidity sensor and multiple switch cannot jointly control the appliance in this mode. |

The main fan exposes the existing `holiday`, `low`, `medium`, and `high`
presets plus `auto`. Select **auto** or `Auto / RF Control` to return control
to Brink. `fan.turn_off` deliberately retains the upstream behaviour and
selects **Holiday** through manual switch control; it does not mean Standby or
return to Auto. Standby remains its own switch (8003).

`Requested Direct Airflow` writes 8002 but does not activate a direct override
on its own. Select Direct Flow explicitly afterwards. The Flair 400 range is
validated as 50–400 m³/h; this avoids imposing the Flair 325 325 m³/h limit.

## Temporary shower boost

Use the **Start Boost** button or `brink_ventilation.start_boost` action to
request High at 8001, then enable switch override at 8000. The integration
records ownership only after both values read back correctly. **Stop Boost /
Return to Auto** and `brink_ventilation.stop_boost` release with `8000 = 0`;
they do not write Normal or Low.

`Boost Active`, `Boost Reason`, elapsed/remaining time, and `Boost Maximum
Duration` make the state visible. The default safety maximum is 60 minutes.
An unfinished integration-owned boost is persisted and reconciled after a HA
restart: it is released once its maximum expires, but a changed 8000 mode is
reported as an external conflict and is not overwritten. A Home Assistant
power outage or disconnected gateway cannot write `8000 = 0`; use the
appliance/local controller after restoring power, or select **Auto / RF
Control** when connectivity returns.

## Humidity automation (opt-in)

The integration supplies the reliable override mechanism and moisture metrics.
Humidity decisions are opt-in Home Assistant blueprints so users can tune them
for their bathroom and can disable them without losing telemetry or controls.

* [External bathroom humidity blueprint](blueprints/automation/brink_ventilation/external_humidity_shower_boost.yaml)
  starts after a configurable high-RH duration and stops after a configurable
  lower-RH duration, minimum run time, maximum safety run time, and cooldown.
* [Brink moisture analytics blueprint](blueprints/automation/brink_ventilation/internal_humidity_shower_boost.yaml)
  uses exhaust absolute-humidity deviation from a rolling lower-third baseline,
  not an arbitrary exhaust-RH threshold. It includes rise/deviation and
  recovery hysteresis.
* [Manual boost example](examples/manual_boost_automation.yaml) shows simple
  Home Assistant actions.

Exhaust RH can be high because air cools or condenses in the heat exchanger.
For that reason, `Exhaust Humidity > 70%` is not a shower detector. Supply and
exhaust absolute humidity and dew point are calculated only from a temperature
and RH pair at the same location. The exhaust rolling baseline, deviation, and
rate are diagnostics for tuning; their default blueprint values are starting
points, not universal thresholds.

## Telemetry and calculations

Dynamic values are grouped into documented contiguous FC04 blocks every ten
seconds; settings/counters are read at most once a minute. Optional firmware
registers 4800–4801 are isolated so an unsupported register cannot make the
appliance unavailable. Failed reads are unavailable/errors, never fabricated
zeroes.

Added telemetry includes supply/exhaust pressure, actual/setpoint flows, RPM,
fan-control type, ventilation mode, bypass step, outside temperature, RHT
humidity, current bypass/preheater/frost states, filter/lifetime volume,
configured flow presets, CO₂/RHT modes, and optional error status/incident.
`Filter Used Volume` is a cumulative m³ counter (4116–4117), corrected from
the old incorrect m³/h rate unit. Frost fan reduction is shown without
inversion: Brink defines 0% as no reduction and 100% as maximum reduction.

Calculated entities include supply/exhaust absolute humidity and dew point,
humidity baseline/deviation/rate, airflow balance/imbalance/setpoint deviation,
RPM per airflow diagnostic, and estimated recovered thermal power.
Heat-recovery efficiency is only shown when there is a suitable indoor extract
temperature, sufficient temperature difference, closed bypass, no active
preheater, and no frost intervention. Flair 400 does not provide the optional
dwelling NTC used by some Flair variants, so set an external indoor/extract
temperature entity in the integration's **Configure** options if an estimate
is wanted. The thermal-power and efficiency entities are estimates, not energy
meters. Use Home Assistant's Integration helper on estimated recovered thermal
power (W) to create an estimated kWh counter.

See [the dashboard example](examples/dashboard.yaml) for Air Quality,
Ventilation, Heat Recovery, and Maintenance views.

## Manual Flair 400 verification

1. Confirm monitoring first: temperatures, flow, both RF CO₂ values, and fan
   mode update while 8000 remains `Auto / RF Control`.
2. Select Low then High on the fan and confirm 8001 readback and 8000 `Manual
   Switch`. Select **auto** and confirm 8000 returns to zero and the RF/CO₂
   controllers resume authority.
3. Set Requested Direct Airflow to a safe value such as 150 m³/h, select
   Direct Flow, verify actual flow, then select Auto / RF Control.
4. Press Start Boost. Confirm High, Boost Active, and remaining time. Press
   Stop Boost / Return to Auto and confirm 8000 reads zero.
5. Import a humidity blueprint with conservative thresholds. Exercise it with
   a test threshold; verify it does not start from unavailable sensor data and
   that it returns to Auto after recovery or the configured maximum.
6. Check that frost/bypass protection still changes its own read-only states;
   forced bypass should normally remain Automatic.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md). The project uses PyModbus 3.11's async
TCP API and requires no USB serial or ESPHome transport.
