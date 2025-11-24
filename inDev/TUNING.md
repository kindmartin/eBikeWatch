# Runtime Tuning Cheat Sheet

Use these helpers from the MicroPython REPL after `import t` to inspect or tweak runtime behaviour on the fly.

## Phaserunner Polling
- `t.set_pr_fast_interval()` &rarr; current fast poll period (ms).
- `t.set_pr_fast_interval(100)` &rarr; set fast loop cadence (e.g. 10&nbsp;Hz).
- `t.set_pr_slow_interval()` &rarr; current slow-cycle length.
- `t.set_pr_slow_interval(1800)` &rarr; set slow loop to 1.8&nbsp;s.
- `t.get_pr_intervals()` &rarr; tuple `(fast_ms, slow_ms)`.
- `t.start_pr_thread()` &rarr; (re)start the dedicated Phaserunner thread if idle.
- `t.start_pr_thread(force=True)` &rarr; restart the thread after forcing a stop.
- `t.stop_pr_thread(wait_ms=500, disable=True)` &rarr; stop the thread (optionally disable future auto-starts).
- `t.set_pr_thread(False)` / `t.set_pr_thread(True)` &rarr; disable/enable automatic PR worker management.
- `t.set_pr_thread_stack()` &rarr; view or update the PR worker stack size (bytes).

## UI & Integrator Cadences
- `t.set_ui_frame_interval()` &rarr; current dashboard redraw period.
- `t.set_ui_frame_interval(60)` &rarr; set redraw cadence to 60&nbsp;ms.
- `t.set_integrator_interval()` &rarr; current integrator step.
- `t.set_integrator_interval(120)` &rarr; step integration every 120&nbsp;ms.
- `t.get_ui_intervals()` &rarr; tuple `(ui_frame_ms, integrator_ms)`.

## Dashboard Refresh Rates
- `t.set_signals_interval()` / `t.set_signals_interval(120)` &rarr; query/update Signals dashboard tick (ms).
- `t.set_trip_interval()` / `t.set_trip_interval(250)` &rarr; query/update Trip dashboard cadence.
- `t.set_battery_interval()` / `t.set_battery_interval(200)` &rarr; query/update Battery Status refresh.
- `t.debug_signals_timing(True, threshold_ms=150)` &rarr; enable Signals timing diagnostics (optional threshold).

## Trip Counter
- `t.set_trip_counter_interval()` &rarr; view current machine.Counter sampling period.
- `t.set_trip_counter_interval(150)` &rarr; adjust wheel pulse sampling cadence (min 100&nbsp;ms).

## Motor ADC/DAC Loop
- `t._motor.cfg["update_period_ms"]` &rarr; current throttle/brake service period (ms).
- `cfg = t._load_motor_config(); cfg["update_period_ms"] = 40; t._save_motor_config(cfg)` &rarr; persist new ADC/DAC cadence, then restart `t`.
- `t.sample_throttle_brake(samples=16, delay_ms=5)` &rarr; grab averaged throttle/brake volts on demand.
- `t._motor.last_vt`, `t._motor.last_vb` &rarr; most recent ADC readings used by the control loop.
- `t._motor.last_dac_throttle_v`, `t._motor.last_dac_brake_v` &rarr; most recent DAC outputs (volts).
- `import motor_control; motor_control.compute_output_voltages(vt, vb, t._motor.cfg)` &rarr; predict DAC outputs for hypothetical readings.

### Up/Down Rocker Polling
- `t._updown_buttons.ADC_PERIOD_MS` &rarr; current polling interval (ms) for the rocker ADC.
- `t._updown_buttons.ADC_PERIOD_MS = 10` &rarr; apply a faster poll rate for the current session (persist via your config tooling if needed).

## Buttons & Input Calibration
- `t.set_page_button_timings()` &rarr; return current Page button timing map.
- `t.set_page_button_timings(DOUBLE_MS=400, SHORT_MS=500)` &rarr; update individual timings.
- `t.set_button_debug(True)` &rarr; verbose button event logging (toggle with `False`).
- `t.set_updown_thresholds(up_max=1200, down_max=3200)` &rarr; update ADC thresholds and print the new limits.
- `t.sample_updown_adc(samples=16, delay_ms=20)` &rarr; capture raw ADC values for calibration.

## Battery Pack Helpers
- `t.list_battery_packs()` &rarr; available pack identifiers.
- `t.show_battery_pack("52V_20Ah")` &rarr; inspect configuration.
- `t.save_battery_pack("custom", cells_series=21, parallel=2, cell_capacity_mAh=4500)` &rarr; persist/update definition and refresh dashboards.
- `t.select_battery_pack("custom")` &rarr; activate a pack.
- `t.reload_battery_pack()` &rarr; reload the active pack from storage.

## Diagnostics & Status
- `t.print_status()` &rarr; console snapshot of key runtime metrics.
- `t.debug_on()` / `t.debug_off()` &rarr; toggle console heartbeat prints.
- `t.get_pr_snapshot()` (if available) &rarr; inspect latest Phaserunner readings.

### Phaserunner Telemetry Inspection
- `t._state.get_pr("battery_current")` &rarr; latest fast-loop value (100&nbsp;ms cadence by default).
- `t._state.get_pr("motor_input_power")` &rarr; paired fast-loop power reading (W).
- `t._state.get_pr("batt_voltage_calc")` &rarr; derived voltage from fast samples.
- `t._state.get_pr("vehicle_speed_PR")`, `t._state.get_pr("controller_temp")`, ... &rarr; slow-loop values (cycled across `_PR_SLOW_MS`).
- `snapshot = t._state.snapshot_pr()` &rarr; grab all PR registers at once (dict of `(value, unit)`).
- `t.get_pr_intervals()` &rarr; confirm current fast/slow periods (`_PR_FAST_MS`, `_PR_SLOW_MS`).
- `t.print_status()` &rarr; formatted mix of fast + slow data for quick console checks.

Keep this file in sync when adding new runtime knobs so quick tuning stays easy during field tests.
