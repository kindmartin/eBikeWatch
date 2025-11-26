# PR-Offload ↔ Main ESP32 Serial Protocol (Draft)

Goal: stream Phaserunner telemetry and status info from the PR-offload MCU to the main eBike controller with predictable latency, sequencing, and extensibility.

## Physical Link
- UART2 on PR-offload → dedicated UART on main ESP32.
- 115200 baud, 8N1, newline-terminated frames (\n).
- Flow is unidirectional today (offload → main); reserve reverse channel for control in v2.

## Frame Format
Each frame is a single JSON object serialized on one line:
```json
{
   "type": "telemetry",
  "seq": 1234,          // uint16 rollover sequence number (detect drops)
  "ts": 123456789,      // ticks_ms() timestamp from PR-offload (diagnostics)
  "fast": { ... },      // latest 20 Hz fields
  "slow": { ... },      // latest 1 Hz fields (last snapshot)
  "errors": {           // optional per-field error strings
     "battery_current": "Modbus timeout"
  }
}
```

### Field Sets
- `fast`: `battery_current`, `vehicle_speed`, `motor_input_power` (20 Hz loop)
- `slow`: `controller_temp`, `motor_temp`, `motor_rpm`, `battery_voltage`, `throttle_voltage`, `brake_voltage_1`, `digital_inputs`, `warnings` (sampled together every second)

### Error Handling
- `_safe_read` records last exception string per register.
- When a read fails, the value is `null` and `errors[reg]` carries the textual reason.
- Main ESP32 can track error streaks and raise dashboard warnings.

## Main ESP32 Consumer Plan
1. **Reader Task**: blocking UART line reader (e.g., `uasyncio` task) parses JSON per line and inspects the optional `type` field. Frames with `type == "telemetry"` carry streaming data; `type == "resp"` are answers to commands.
2. **Sequencing**: verify `seq` increments (with rollover). If a gap>1 is detected, mark data stale.
3. **State Store**: maintain latest fast + slow dicts in shared `app_state.pr` section with timestamp of receipt.
4. **UI Hooks**: existing `status PR` command can use new data source seamlessly.
5. **Command Channel**: the same UART carries newline-delimited JSON requests from the main ESP. Each request may include a `req_id` integer; the reply will echo it so callers can pair responses. Supported `cmd` values today:
   - `ping` → `{type:"resp",cmd:"ping",ts,...}`
   - `status`, `snapshot`, `errors`
   - `set_fast`, `set_slow`, `set_rate` (payload uses `ms` fields)
   - `poll` with `action` = `pause|resume|start|stop`
   - `reboot` (ack then MCU resets)
   - `sleep` currently returns an error because GPIO18/19 cannot wake the chip from deep sleep.
- `version` returns `{fw:"2025.11.25.1", protocol:1}` so the main ESP can ensure compatibility.
   Commands always receive a `type:"resp"` frame; telemetry continues concurrently.

## Future Enhancements
- Binary framing option (CBOR + CRC) if bandwidth becomes a concern.
- Compression flag (`type":"delta"`) to send only changed values.
- Signed integrity field (CRC16) appended before newline for noisy links.

This draft is enough to start integrating the main ESP32 consumer while leaving room for protocol evolution.
