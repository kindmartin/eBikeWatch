# PR-Offload Helper Reference

Quick guide to the runtime helpers exposed by `pr_offload_esp32.py`. Import this module on the PR-offload ESP32 REPL (`import pr_offload_esp32 as off`) and use the helpers below to inspect or tune the Phaserunner poller.

## Polling Cadence
- `off.get_fast_interval()` &rarr; current fast-loop period in milliseconds (default 50 ms / 20 Hz).
- `off.set_fast_interval(ms)` &rarr; update the fast-loop period (min 20 ms). Returns the applied value.
- `off.get_slow_interval()` &rarr; current slow snapshot cadence in milliseconds (default 1000 ms / 1 Hz).
- `off.set_slow_interval(ms)` &rarr; update slow cadence (clamped to ≥ fast interval). Returns the applied value.

## Telemetry Snapshots
- `off.get_latest(name)` &rarr; most recent cached value for any register (fast fields refresh every loop, slow fields refresh when sampled).
- `off.get_snapshot()` &rarr; returns a dict `{"ts", "seq", "fast", "slow", "errors"}` mirroring the JSON sent to the main ESP32.
- `off.get_errors()` &rarr; copy of the current error map (keys = register names, values = last exception string).

### Example
```
>>> import pr_offload_esp32 as off
>>> off.get_fast_interval()
50
>>> off.set_fast_interval(40)
40
>>> off.get_latest("battery_current")
12.781
>>> off.get_latest("battery_voltage")
80.65625
>>> off.get_snapshot()
{'ts': 825394, 'seq': 312, 'fast': {'battery_current': 12.78, 'vehicle_speed': 4.2, 'motor_input_power': 585.0},
 'slow': {'controller_temp': 32.0, 'motor_temp': 25.5, 'motor_rpm': 0.0, 'battery_voltage': 81.0,
          'throttle_voltage': 1.67, 'brake_voltage_1': 0.00, 'digital_inputs': 0, 'warnings': 0},
 'errors': {}}
>>> off.get_errors()
{}
```

## Streaming Format (for reference)
Each UART frame emitted to the main ESP32 is a single JSON object:
```json
{
  "seq": 42,
  "ts": 123456789,
  "fast": {"battery_current": 12.34, ...},
  "slow": {"controller_temp": 32.0, ...},
  "errors": {"battery_current": "Modbus timeout"}
}
```
- Fast set (20 Hz): `battery_current`, `vehicle_speed`, `motor_input_power`.
- Slow set (1 Hz snapshot): `controller_temp`, `motor_temp`, `motor_rpm`, `battery_voltage`, `throttle_voltage`, `brake_voltage_1`, `digital_inputs`, `warnings`.

## Main ESP Bridge Shortcuts
From the main controller REPL (`import t`), the new helpers talk to the PR-offload MCU over the shared UART:
- `t.pr_version()` &rarr; obtain PR-offload firmware + protocol versions (bump `FW_VERSION` in `pr_offload_esp32.py` whenever you deploy new features).

## Usage Tips
1. **Live tuning** – connect to the PR-offload REPL, import the module as `off`, and adjust cadences on the fly.
2. **Diagnostics** – call `off.get_snapshot()` before/after field rides to capture exactly what is being streamed.
3. **Error tracking** – `off.get_errors()` highlights persistent Modbus issues without parsing the UART feed.
4. **Integration testing** – when the main ESP32 consumer is offline, use the REPL snapshot to verify data without needing the bridge.

Keep this document updated if new helper functions or telemetry fields are added.
