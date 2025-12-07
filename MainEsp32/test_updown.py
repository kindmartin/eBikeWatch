"""Manual tester for the shared Up/Down button ADC ladder.

Copy this script to the ESP32 root (same folder as `boot.py`) and run:

    import test_updown
    test_updown.loop()

Press the Up and Down buttons to see the raw ADC value, the computed
voltage, and the interpreted state.
"""

import time

from HW import UPDOWN_ADC_PIN, make_adc

# Match the main firmware defaults so we see the same state transitions.
UP_MAX = 50
DOWN_MAX = 2000
VREF = 3.3

def _init_adc():
    try:
        return make_adc(UPDOWN_ADC_PIN)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Failed to init Up/Down ADC: {}".format(exc))

_ADC = _init_adc()


def _classify(raw_value):
    if raw_value <= UP_MAX:
        return "UP"
    if raw_value <= DOWN_MAX:
        return "DOWN"
    return "IDLE"


def read_once():
    """Return a single (raw, volts, state) tuple."""
    raw = _ADC.read()
    volts = (raw / 4095.0) * VREF
    return raw, volts, _classify(raw)


def loop(period_ms=250):
    """Continuously print button voltage/state every period_ms milliseconds."""
    if period_ms < 50:
        period_ms = 50
    print("[test_updown] Watching pin {} ({} ms)...".format(UPDOWN_ADC_PIN, period_ms))
    print("Raw threshold: UP<=%d, DOWN<=%d" % (UP_MAX, DOWN_MAX))
    try:
        while True:
            raw, volts, state = read_once()
            print("RAW={:4d}  VOLTS={:>4.3f}V  STATE={}".format(raw, volts, state))
            time.sleep_ms(period_ms)
    except KeyboardInterrupt:
        print("\n[test_updown] Stopped")


if __name__ == "__main__":  # pragma: no cover
    loop()
