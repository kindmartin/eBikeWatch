# ESP Main 32 Helper Reference

This document catalogs the most frequently used helpers exposed by `inDev/t.py`. They are grouped by subsystem or hardware block so you can discover the right call quickly from the REPL.

## PR Offload Bridge & UART Utilities
- `pr_offload_wifi_connect(wait_ms=5000)`: Ask the PR offload MCU to run its frozen `wifiConnect` routine.
- `_ensure_pr_wake_pin(default_level=1)`: Internal guard that configures the shared wake GPIO (used by the helpers below).
- `pr_offload_hold_awake(enabled=True)`: Drive the PR wake line HIGH or LOW to keep the offload MCU alive or let it sleep.
- `pr_offload_allow_sleep()`: Convenience alias for `pr_offload_hold_awake(False)`.
- `pr_offload_wake(pulse_ms=50)`: Send a HIGH pulse on the wake line to start or refresh the offload MCU.
- `release_pr_uart_lines()`: Deinitialize the PR UART and place TX/RX into inputs so other peripherals (e.g., modem) can reuse the pins safely.

## Cellular Modem / SIM7600 Helpers
- `_get_cellular_modem()`: Lazy importer for `CellularLte.modem`; keeps boot time low when LTE is unused.
- `modem_power_off()` / `modem_power_on(wait_for_registration=True, timeout_ms=30000)`: Hardware-level power sequencing for the on-board SIM7600. The power-on call now starts the UART reader, forces full RF functionality, and blocks until the modem registers (unless you pass `wait_for_registration=False`).
- `_auto_disable_modem_on_boot()`: Invoked during `_main_async` to force the modem OFF unless some later code explicitly turns it back on.
- `_get_test_modem_module()`: Lazy loader for `testModem`, providing access to the diagnostic routines without importing them during boot.
- `modem_wait_for_registration(timeout_ms=30000, poll_ms=1500, verbose=False)`: Polls `AT+CPIN?`/`AT+CREG?` until the SIM is ready and registered (home or roaming) or a timeout occurs.
- `modem_collect_snapshot(power_down=False)`: Fetches the full telemetry snapshot defined in `testModem.collect_snapshot()`, powering the modem on if necessary and leaving it ON by default (pass `power_down=True` to shut it off afterwards).
- `print_modem_snapshot(power_down=False)`: Mirrors `testModem.print_snapshot()` with the same “stay on unless requested” behavior.
- `collect_alarm_snapshot(power_down_modem=False, wifi_limit=2, include_sys_battery=True, include_pr_battery=True)`: Builds a structured snapshot (cell/operator info, GPS fix, top-N Wi-Fi networks, system & PR battery data) and updates `AppState` so the alarm dashboard/snapshot serialization can use fresh data.

## Power Management Unit (AXP192) Helpers
- `_get_pmu_device(refresh=False)`: Reuses `make_i2c()` to instantiate and cache the AXP192 driver.
- `_format_pmu_flags(power_status, charge_status)`: Builds the concise status string (`AC,VBUS,BAT,...`) matching the standalone `testBatt` script.
- `battery_status_snapshot(refresh_pmu=False)`: Takes a single reading of VBUS, VBAT, charge/discharge currents, and status flags.
- `print_battery_status(refresh_pmu=False)`: Prints a one-line summary identical to `testBatt.probe()` but without looping forever.

## Sleep, Wake, and Power Guard
- `_enter_sleep_sequence(state, wake_pin)`: Performs the orderly shutdown (UI notice, PR sleep request, RTC snapshot) before calling `machine.deepsleep()`.
- `_sleep_guard_task(...)` & `schedule_sleep_guard(...)`: Monitor VBUS/BAT conditions and trigger the sleep sequence when external power disappears.
- `_read_wake_reason_code()` / `_woke_from_main_wake_pin()`: Decode ESP32 wake sources to differentiate alarm/accelerometer wakes from cold boots.
- `auto_wake_pr_offload()`: Async helper that nudges the PR offload MCU awake shortly after boot so it can accept commands.

## Diagnostics & Runtime Utilities
- `_track_task()` / `_cancel_tracked_tasks()`: Centralized coroutine bookkeeping used across UI, motor, and background workers.
- `_queue_uart_release()` / `_uart_release_worker()`: Provide deferred UART release without blocking the main async loop.
- `sample_throttle_brake_async()` / `sample_throttle_brake()`: Poll throttle and brake ADCs for tuning while the UI keeps running.
- `_apply_control_loop_debug_pref()`, `_apply_loop_timing_monitor_pref()`, `_apply_pid_timing_debug_pref()`: Runtime switches that adjust controller instrumentation based on global overrides.

Use this reference as the quick index when hacking on the ESP32 main firmware or testing hardware from the REPL.
