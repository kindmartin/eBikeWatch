# Control Loop Frequency Debug Task

This checklist walks through the exact REPL commands to capture loop timing, disable Phaserunner telemetry, and isolate which async task is starving the motor control loop. Run each block in order; copy/paste is safe because every snippet is self-contained.

## 1. Clean Start

```python
import t

t.enable_control_loop_debug(0)
t.set_loop_timing_monitor(0)
t.set_pid_timing_debug(0)
```

Resets diagnostic noise before enabling anything else.

## 2. Disable Phaserunner Thread (optional for speed mode)

```python
t.set_pr_thread(False)
```

If you later need PR data back, rerun `t.set_pr_thread(True)` AFTER capturing logs.

## 3. Enable Loop + PID Timing

```python
t.enable_control_loop_debug(1, period_ms=500)
t.set_loop_timing_monitor(1)
t.set_pid_timing_debug(1, period_ms=500)
```

Watch the `loop=..Hz` and `dt=..ms` values to confirm the slowdown.

## 4. Capture Baseline Snapshot

```python
t.get_pr_snapshot()
```

Confirms PR polling is really off (values stay frozen) and gives a reference state.

## 5. UI Task Isolation

```python
t.set_ui_frame_interval(500)
```

Recheck the monitor output. If the loop rate jumps up, the OLED refresh was the bottleneck; keep it slow or profile dashboards.

## 6. Dashboard Timing Probe

```python
t.debug_signals_timing(True, threshold_ms=80)
```

Any screen draw that exceeds the threshold prints a warning. Use it while flipping through dashboards, then disable via `t.debug_signals_timing(False)`.

## 7. Stretch Background Tasks

```python
t.set_integrator_interval(500)
```

Optionally also raise the Signals dashboard tick:

```python
t.set_signals_interval(500)
```

If the loop rate recovers only after these calls, those tasks were delaying the scheduler.

## 8. Trip Counter Pause (if still slow)

```python
# Temporarily disable trip counting by commenting out the async task in t.py
# or raise its interval inside motor_config.json (trip_counter_interval_ms).
```

Because editing code is harder on-device, tweak the JSON value when you can, then reboot and rerun steps 1–7.

## 9. Re-enable Everything

Once the culprit is known, restore defaults:

```python
t.set_pr_thread(True)
t.set_ui_frame_interval(80)
t.set_integrator_interval(200)
t.set_signals_interval(200)
t.debug_signals_timing(False)
t.enable_control_loop_debug(0)
t.set_loop_timing_monitor(0)
t.set_pid_timing_debug(0)
```

Only re-enable the task that caused the slowdown after mitigating it (e.g., keep the UI interval high during tuning).
