# Pending items (ESP32 main runtime)

1. **Alarm-mode modem policy**  
   Detect whether the boot reason corresponds to the accelerometer/alarm wake pin and keep the SIM7600 powered only in that scenario. Normal boots should continue forcing the modem off.

2. **Alarm dashboard data source**  
   Wire the new modem snapshot helpers into the alarm dashboard/state updates so the UI shows CSQ/operator/last GNSS fix during anti-theft mode.

3. **Runtime refactor follow-up**  
   Execute Phase 1 of `ToDoPlan.md` (split `t.py` into runtime manager, PR bridge API, and dashboard loader) to reduce the entrypoint footprint.

4. **Battery telemetry integration**  
   Feed `battery_status_snapshot()` into the state machine so periodic readings appear on the system battery dashboard without launching the standalone `testBatt` loop.

5. **Documentation refresh**  
   Extend `espMain32.md` with wiring diagrams / pin references from `HW.py` and link it from the main README for quick onboarding.
