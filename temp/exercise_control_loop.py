import sys
import types

# Stub machine module for host-side testing
if "machine" not in sys.modules:
    machine = types.ModuleType("machine")

    class Pin:
        IN = 0
        OUT = 1

        def __init__(self, *_, **__):
            pass

    class ADC:
        ATTN_11DB = 0
        WIDTH_12BIT = 12

        def __init__(self, *_, **__):
            pass

        def atten(self, *_, **__):
            pass

        def width(self, *_, **__):
            pass

        def read(self):
            return 0

    class I2C:
        def __init__(self, *_, **__):
            pass

    machine.Pin = Pin
    machine.ADC = ADC
    machine.I2C = I2C
    sys.modules["machine"] = machine

if "uasyncio" not in sys.modules:
    import asyncio

    sys.modules["uasyncio"] = asyncio

from inDev.motor_control import MotorControl, DEFAULTS


class DummyState:
    def __init__(self):
        self.trip_counter_available = True
        self.trip_speed_kmh = 0.0
        self.motor_input_power = 0.0
        self.throttle_v = 0.0
        self.brake_v = 0.0
        self.brake_v_raw = 0.0
        self.throttle_v_raw = 0.0
        self.dac_throttle_v = 0.0
        self.dac_brake_v = 0.0

    def get_pr(self, key, default=None):
        return getattr(self, key, default)


def exercise_mode(mode, speed, power, ratio_input=0.6, **cfg_overrides):
    cfg = DEFAULTS.copy()
    cfg.update({"throttle_mode": mode})
    cfg.update(cfg_overrides)
    mc = MotorControl(**cfg)
    state = DummyState()
    state.trip_speed_kmh = speed
    state.motor_input_power = power
    mc.bind_state(state)
    output_ratio = mc._apply_control_mode(ratio_input, brake_active=False)
    return output_ratio, mc._control_ratio


if __name__ == "__main__":
    scenarios = [
        ("power", 15.0, 600.0),
        ("speed", 35.0, 300.0),
        ("torque", 10.0, 400.0),
        ("mix", 12.0, 500.0),
        ("mix", 28.0, 500.0),
    ]

    for mode, speed, power in scenarios:
        ratio, control = exercise_mode(mode, speed, power)
        print(f"Mode {mode:>6} | speed {speed:5.1f} km/h | power {power:6.1f} W -> ratio {ratio:.3f}, control_state {control}")
