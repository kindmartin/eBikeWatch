# Manual Hardware Test Scripts

This reference summarizes the standalone scripts used to validate key ESP32 subsystems. All paths are relative to the firmware workspace root (`inDev/` is the ESP32 filesystem root).

---

## `testBatt.py` – AXP192 power/charging probe
- **Location**: `inDev/testBatt.py`
- **Purpose**: Poll the LilyGO T-PCIE PMU (AXP192) to verify USB/VBUS presence, battery voltage, charge/discharge currents, and charger flags.
- **Hardware setup**: Ensure the AXP192 shares I2C bus `ID=0`, `SCL=GPIO22`, `SDA=GPIO21` (default for the board). Requires `drivers/axp192.py` copied alongside the script.
- **How to run**:
  1. Copy `testBatt.py` and `drivers/axp192.py` to the ESP32 filesystem if they are not already there.
  2. Open the REPL and run `import testBatt; testBatt.probe()`.
  3. The script logs one line every few seconds showing VBUS voltage/current, VBAT voltage, charge/discharge currents, and decoded status flags (`AC`, `VBUS`, `BAT`, `CHG`, etc.).
  4. Press `Ctrl+C` to stop.
- **What to look for**:
  - Confirm VBUS presence when USB is attached.
  - Verify battery voltage and charging current behave as expected when the charger is connected/disconnected.
  - Flags help diagnose missing battery packs or thermal faults.

---

## `testModem.py` – SIM7600 diagnostic console
- **Location**: `inDev/testModem.py`
- **Purpose**: Exercise the on-board SIM7600 module for cellular signal, operator registration, GNSS, Wi-Fi scans, SMS sending, and RTC synchronization.
- **Key helpers**:
  - `power_on(force=False)` / `power_off()`: Control modem + GNSS power rails.
  - `collect_snapshot()` / `print_snapshot()`: Gather CSQ, COPS, CREG, CPSI, GNSS (`AT+CGNSINF` fallback to `AT+CGPSINFO`), and Wi-Fi RSSI data into a single dict.
  - `monitor_gnss(...)` and `sync_rtc_from_gnss(...)`: Keep polling until a GNSS fix is acquired and optionally set the ESP32 RTC.
  - `send_status_sms(number=...)`: Pack the snapshot into a concise SMS payload.
- **How to run a snapshot**:
  1. At the REPL: `import testModem; snap = testModem.print_snapshot()`.
  2. The helper powers the modem if needed, waits for AT responses, and prints the telemetry block.
  3. Use `testModem.power_off()` when finished to save power (unless the runtime keeps it on for alarm mode).
- **Notes**:
  - Relies on `CellularLte/modem.py` and `CellularLte/gnss.py` modules for AT command handling.
  - When SMS or NTP helpers are used, ensure SIM APN credentials are valid; error messages are printed if CNTP/NITZ preconditions are missing.

---

## `testPR1.py` – Phaserunner UART link test ("testPr")
- **Location**: `inDev/testPR1.py`
- **Purpose**: Manually validate the UART bridge between the main ESP32 and the PR-offload ESP32 board.
- **Wiring reminder**:
  - Main ESP32 GPIO13 (RX) ←→ PR-offload GPIO4 (TX)
  - Main ESP32 GPIO15 (TX) ←→ PR-offload GPIO5 (RX)
- **Key helpers**:
  - `send_line(text, append_newline=True)`: Pushes data over the shared UART (named `u`).
  - `read_available()`: Dumps any received bytes, tagging them as `[rx-main]` in the REPL.
  - `ping_loop(label="MAIN", interval_ms=1000)`: Automates a periodic ping while checking for inbound traffic—handy for soak tests.
  - `close_uart()`: Releases the UART once testing is complete.
- **Usage example**:
  ```python
  import testPR1
  testPR1.send_line("hello PR")
  testPR1.read_available()
  # Optional stress loop:
  testPR1.ping_loop()
  ```
  Interrupt with `Ctrl+C` to stop the ping loop.
- **What to look for**:
  - Bidirectional traffic without framing errors.
  - Stable timing during `ping_loop` runs (no dropped packets or mismatched counters).

Use these scripts whenever you need to validate hardware blocks in isolation before integrating them into the main `t.py` runtime.
