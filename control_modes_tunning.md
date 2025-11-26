# Control Modes Tuning Guide

This note explains how to monitor and adjust the closed-loop control modes (power, speed, torque) in `MotorControl`.

## Live Monitor

The monitor prints the control loop state every second (default). Enable it directly from the runtime:

```python
import t

# turn on diagnostics (optionally set period_ms >= 200)
t.enable_control_loop_debug(1, period_ms=800)

# turn off
t.enable_control_loop_debug(0)

# query current preference
t.enable_control_loop_debug()
```

Typical output:

```
[MotorControl] monitor: mode=speed | ADC=32.4% (1.48V) | speed=18.6km/h (34.0%) | target=22.0km/h (40.0%) | DAC=2.10V | >
```

**Fields**
- `mode`: active control mode.
- `ADC`: throttle position (0.85 V = 0 %, 2.85 V = 100 % by default).
- `<metric>`: controlled variable (speed/power/torque) with its unit and normalized percent.
- `target`: expected metric computed from the ADC input.
- `DAC`: actual throttle output voltage.
- Final arrow `>>`, `>`, `=`, `<`, `<<` indicates how far the measured metric is from target (> lagging, < overshooting, = within ±5 %).

Use the arrows and percentages to see whether you need more/less controller aggressiveness.

## PID Helpers

Query or update the gains without touching `motor_config.json` manually:

```python
# Inspect power loop gains (includes short guidance strings)
t.get_pid_params("power")

# Bump speed gains and persist to disk
t.set_pid_params("speed", kp=0.42, ki=0.05, output_alpha=0.25)
```

Supported modes: `power`, `speed`, `torque`. The helpers clamp `d_alpha`/`output_alpha` to [0, 1]. When the live controller is running, the corresponding PID state is reset so changes take effect immediately.

### Parameter Cheatsheet
| Parameter | Effect | When to Increase | When to Decrease |
|-----------|--------|------------------|------------------|
| `kp` | Proportional gain | Metric lags target (`>`); steady-state error persists | Oscillation or overshoot (`<`)
| `ki` | Integral gain | Reaches target then sags lower; needs bias removal | Slow drift past target or hunting
| `kd` | Derivative gain | Oscillates even with low `kp`; need extra damping | Response becomes sluggish or noisy
| `integral_limit` | Caps integral term | Recovery too slow after brake release | Integral wind-up causes large surge
| `d_alpha` | Derivative filter | Derivative too noisy; jittery indicator | Derivative lags; need quicker damping
| `output_alpha` | Output low-pass | DAC jitter; noisy throttle | Laggy response or persistent `>` arrow

## Manual Tuning Workflow

1. **Baseline**: Disable `ki`/`kd` (set to 0). Raise `kp` until the monitor shows repeated `<`/`>` oscillation, then back off ~20 %.
2. **Eliminate bias**: Increase `ki` in small steps (e.g., 0.01) until steady-state error disappears. Watch for slow overshoot; lower `ki` if the arrow flips `<` after settling.
3. **Damping**: If overshoot remains, add `kd` (0.02–0.05) or increase `output_alpha` to smooth the command.
4. **Integral limit**: Keep around 0.3–0.6. Lower if the controller surges after braking; raise slightly if it never recovers.
5. **Filter tweaks**: Use `d_alpha` ~0.3 to start. Raise it if derivative noise appears; lower for quicker derivative action.
6. **Throttle factor**: Remember `throttle_factor` scales the whole loop. If you see saturation (ADC near 100 % but target still unmet), either raise `throttle_factor` or increase `throttle_*_max` for that mode.

Always make changes with the monitor enabled so you can correlate the numeric deltas with the arrow guidance.

## Autotuning?

There is no fully automatic tuner yet. Implementing Ziegler–Nichols or relay autotune would require scripted throttle steps with safety checks (cut power if overshoot exceeds a threshold). For now, the manual loop plus the `>`/`<` indicators provide fast feedback without risky automation. If you want to explore an automated routine later, plan on collecting logs while sweeping throttle and logging speed/power to derive the ultimate gain/period.
