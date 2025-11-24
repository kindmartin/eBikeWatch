# Control Mode Reference

Comprehensive notes for the closed-loop logic implemented by `MotorControl` in `inDev/motor_control.py`.

## Loop Overview

All modes share the same execution path inside `MotorControl.run()`:

1. **Sample Inputs**: `vt_raw` and `vb_raw` are read from the throttle and brake ADCs. Values are calibrated via `_calibrate_adc` before use.
2. **Normalize Demand**: `_throttle_ratio_from_adc` maps the calibrated throttle voltage to `raw_ratio` (0…1). Brake involvement is detected against `brake_input_threshold`.
3. **Mode Dispatch**: `_apply_control_mode` receives `raw_ratio` plus the brake flag and returns `control_ratio`, potentially reusing `_control_with_metric` for feedback modes. When the brake is active every mode forces `control_ratio = 0` and clears filter state.
4. **Output Voltages**: `compute_output_voltages` merges `raw_ratio`/`control_ratio` with configuration limits to generate target DAC voltages for throttle and brake.
5. **Actuate DACs**: `_volts_to_dac12` converts voltages to 12-bit codes and the MCP4725 drivers are updated. `_report_dac_ok`/`_report_dac_error` track hardware health.
6. **Publish State**: The loop stores the latest samples (`last_vt`, `last_vb`, ratios, DAC volts) and mirrors them into `AppState` (`throttle_v`, `throttle_ratio_control`, `throttle_mode_active`, etc.) for UI and telemetry consumers.
7. **Timing**: The coroutine sleeps for the remaining portion of `update_period_ms`; if the work ran long it yields immediately to keep the loop cooperative.

These steps give a consistent structure to describe every mode.

## Shared Closed-Loop Variables

- **`raw_ratio`** — direct rider demand derived from the pedal ADC (normalized 0…1).
- **`control_ratio`** — command returned by `_apply_control_mode`; may be filtered or limited based on telemetry. Persisted in `self._control_ratio`.
- **`_filtered_power`, `_filtered_speed`, `_filtered_torque`** — low-pass filtered metrics used by feedback modes. Cleared whenever the brake triggers or a mode switch happens.
- **`_mix_use_speed`** — hysteresis latch for the `mix` selector that chooses between speed- and torque-based control.
- **`throttle_ratio_raw`, `throttle_ratio_control`** (in `AppState`) — values exported to the UI; updated each loop after computing outputs.

## Mode Details

Each subsection references the key logic residing in `_apply_control_mode`.

### `open`

- **Closed-loop vars**: sets `self._control_ratio = raw_ratio`; filters remain `None`.
- **Evaluation**: no telemetry is read; the function quits early once the brake is confirmed inactive.
- **Post action**: outputs follow rider demand (subject only to `compute_output_voltages` clamps). Useful for diagnostics or manual override.

### `power`

- **Closed-loop vars**:
  - Uses `_filtered_power` with `throttle_filter_alpha` to smooth power readings.
  - `control_ratio` evolves via `_control_with_metric` to keep normalized power close to `ratio_input`.
- **Evaluation**:
  1. `_extract_power_w` retrieves `AppState` data: prefers direct Phaserunner `motor_input_power`, otherwise multiplies `battery_voltage` and `battery_current`.
  2. `_control_with_metric` normalizes filtered power against `throttle_power_max_w`, applies proportional gain `throttle_control_gain`, and smooths the result with `throttle_ratio_alpha`.
- **Post action**: Updated `control_ratio` modulates throttle DAC voltage, reducing demand when measured power exceeds the configured ceiling.

### `speed`

- **Closed-loop vars**:
  - Relies on `_filtered_speed` (low-pass of vehicle speed).
  - Shares `throttle_control_gain`, `throttle_filter_alpha`, and `throttle_ratio_alpha` with the other feedback modes.
- **Evaluation**:
  1. `_extract_speed_kmh` prefers wheel-counter derived `trip_speed_kmh`; if unavailable it reads Phaserunner `vehicle_speed`.
  2. `_control_with_metric` compares filtered speed against `throttle_speed_max_kmh`.
- **Post action**: Throttle volts are trimmed whenever speed exceeds the desired envelope, while brake output remains governed by the brake ADC.

### `torque`

- **Closed-loop vars**:
  - Utilises `_filtered_torque` to average the infered torque signal.
  - Maintains `self._control_ratio` as the smoothed command.
- **Evaluation**:
  1. Torque estimate derived from `power / max(speed_mps, 0.3)`; ensures non-zero denominator with `throttle_torque_ref_speed_kmh`.
  2. `torque_max` equals `throttle_power_max_w / max_speed_mps`, anchoring the limit to configuration.
  3. `_control_with_metric` closes the loop on torque rather than power or speed.
- **Post action**: Encourages consistent wheel torque across varying speeds until capped by power or DAC limits.

### `mix`

- **Closed-loop vars**:
  - Shares `_filtered_speed`, `_filtered_torque`, and the `_mix_use_speed` latch.
  - `self._control_ratio` transitions between speed- and torque-driven targets.
- **Evaluation**:
  1. Compares current speed against `throttle_mix_speed_kmh` with hysteresis `throttle_mix_hyst_kmh` to decide the controlling metric.
  2. If `_mix_use_speed` is true, behaves like the `speed` mode; otherwise mirrors the `torque` branch.
- **Post action**: Provides torque-focused control at low speeds for launch feel, then shifts to speed limiting once cruising.

## Brake Handling

`brake_active` is asserted when `vb` crosses `brake_input_threshold`. Every mode reacts identically:

- Resets `_control_ratio` and all filtered metrics to `None`.
- Forces the returned ratio to `0.0`, reducing throttle output to `throttle_output_min` while the brake voltage is produced by the brake ADC span.
- `AppState.brake_v` and `AppState.dac_brake_v` reflect the live brake state in the same loop iteration.

## Post-Loop State Updates

Before yielding, each iteration copies the following into `AppState` (if bound via `bind_state`):

- **Voltages**: `throttle_v`, `brake_v`, plus the raw ADC captures (`throttle_v_raw`, `brake_v_raw`).
- **Ratios**: `throttle_ratio_raw`, `throttle_ratio_control`.
- **Outputs**: `dac_throttle_v`, `dac_brake_v`, and the active mode label in `throttle_mode_active`.
- **Motor Binding**: `state.motor_control = self` lets other components reuse hardware handles (e.g., to read DAC state without new ADC objects).

These updates allow UI dashboards, telemetry exporters, and diagnostics helpers to track both the user request and the closed-loop response in real time.
