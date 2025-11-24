

# ================================
# 2) power.py
# ================================

import machine, time, sys
try:
    import esp32
except:
    esp32 = None

import HW
from axp192 import AXP192  # fileciteturn0file0

_axp = None

def axp():
    global _axp
    if _axp: return _axp
    _axp = AXP192(HW.i2c())
    return _axp


def setup_pwron(long_ms=1500, short_ms=128):
    try:
        axp().configure_pwron(long_ms, short_ms)
    except Exception as e:
        print("AXP PWRON setup error:", e)


def enter_deepsleep_with_accel():
    """Deep sleep; wake on MMA8452Q INT (active low assumed) and on timer fallback."""
    c = HW.config["MMA8452Q"]
    pin_int = machine.Pin(c.get("int_pin", 39), machine.Pin.IN, machine.Pin.PULL_UP)
    if esp32:
        esp32.wake_on_ext0(pin=pin_int, level=0)
    # fallback wake-up after ~24h to keep device reachable
    machine.deepsleep(24*60*60*1000)

