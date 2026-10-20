# Changelog

## 2.1.0 — recovered-energy estimate

- Add a persistent, cumulative `Estimated Recovered Thermal Energy` kWh sensor
  by integrating only valid estimated thermal-power samples. It starts with
  this release and excludes long polling or Home Assistant outages.

## 2.0.2 — advanced telemetry hotfix

- Correct the advanced-sensor metadata handling so Home Assistant registers the
  new airflow, moisture, and calculated diagnostic entities.

## 2.0.1 — setup hotfix

- Prevent the coordinator from assigning its read-only calculated boost-time
  properties during the initial data refresh, which caused setup to retry.

## 2.0.0 — kloknibor fork

- Brand the visible integration, HACS metadata, documentation and support links
  as **Brink HRV Modbus (kloknibor)** while preserving the
  `brink_ventilation` domain and existing unique IDs.
- Replace individual register polling with serialized, safe contiguous FC04
  blocks plus lower-frequency FC03 diagnostics and reconnect/read-error
  handling.
- Add documented airflow, pressure, RPM, control-mode, outside-air,
  maintenance, diagnostics, and calculated moisture/balance/recovery entities.
- Add explicit Modbus control mode, direct airflow, bypass mode, safe boost
  actions/buttons/services, ownership tracking, readback verification and
  restart reconciliation.
- Add opt-in external-sensor and internal-moisture shower boost blueprints,
  dashboard YAML, manual boost example, and safety documentation.
- Correct filter-air counter metadata from m³/h to cumulative m³ and retain
  Brink's documented frost fan-reduction meaning.
