"""Minimal trip pulse counter.

Run this on the main ESP (MicroPython):
    import test.testTrip as trip
    trip.run()
"""

import time
from machine import Pin

from HW import TRIP_COUNTER_PIN, TRIP_COUNTER_EDGE

_EDGE_FLAGS = {
    "rising": Pin.IRQ_RISING,
    "falling": Pin.IRQ_FALLING,
    "both": Pin.IRQ_RISING | Pin.IRQ_FALLING,
}


def _edge_flag():
    try:
        return _EDGE_FLAGS[TRIP_COUNTER_EDGE.lower()]
    except Exception:
        return Pin.IRQ_RISING


def run(duration_s=None):
    """Start counting trip pulses until Ctrl+C (or ``duration_s`` seconds)."""

    counter_pin = Pin(TRIP_COUNTER_PIN, Pin.IN, Pin.PULL_UP)
    trigger = _edge_flag()
    pulses = {"count": 0}

    def _on_pulse(_):
        pulses["count"] += 1

    counter_pin.irq(trigger=trigger, handler=_on_pulse)
    start_ms = time.ticks_ms()
    next_report = start_ms
    print("[testTrip] counter armed on GPIO{} (edge={})".format(TRIP_COUNTER_PIN, TRIP_COUNTER_EDGE))
    print("[testTrip] press Ctrl+C to stop")

    try:
        while True:
            now = time.ticks_ms()
            if duration_s is not None and time.ticks_diff(now, start_ms) >= int(duration_s * 1000):
                break
            if time.ticks_diff(now, next_report) >= 1000:
                elapsed = time.ticks_diff(now, start_ms) / 1000
                print("elapsed {:6.1f}s  pulses {:6d}".format(elapsed, pulses["count"]))
                next_report = now
            time.sleep_ms(50)
    except KeyboardInterrupt:
        print("\n[testTrip] interrupted")
    finally:
        counter_pin.irq(handler=None)
        elapsed = time.ticks_diff(time.ticks_ms(), start_ms) / 1000
        print("[testTrip] total {:6d} pulses in {:.1f}s".format(pulses["count"], elapsed))


if __name__ == "__main__":
    run()
