"""Console monitor to inspect throttle/brake ADC inputs and derived DAC outputs.

Run on the device REPL:
    import signals_terminal
    signals_terminal.run()
"""

import time

try:
    import ujson as json
except ImportError:  # CPython fallback
    import json

from HW import ADC_THROTTLE_PIN, ADC_BRAKE_PIN, make_adc
from motor_control import DEFAULTS as MOTOR_DEFAULTS, compute_output_voltages

_REFRESH_MS = 500  # 2 Hz


def _load_config():
    cfg = MOTOR_DEFAULTS.copy()
    try:
        with open("motor_config.json", "r") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def _prepare_adc(pin):
    try:
        return make_adc(pin)
    except Exception as exc:
        print("[signalsAtTerminal] ADC init error on pin {}: {}".format(pin, exc))
        return None


def _read_volts(adc, scale):
    if adc is None:
        return None
    try:
        raw = adc.read()
    except Exception:
        return None
    if raw is None:
        return None
    return raw * scale


def _fmt(volts):
    if volts is None:
        return "  -- "
    try:
        return "{:5.2f}".format(float(volts))
    except Exception:
        return "  -- "


def run(period_ms=_REFRESH_MS):
    cfg = _load_config()
    adc_pin_th = cfg.get("adc_pin_throttle", ADC_THROTTLE_PIN)
    adc_pin_br = cfg.get("adc_pin_brake", ADC_BRAKE_PIN)
    adc_th = _prepare_adc(adc_pin_th)
    adc_br = _prepare_adc(adc_pin_br)

    adc_vref = float(cfg.get("adc_vref", 3.3) or 3.3)
    scale = adc_vref / 4095.0 if adc_vref else 0.0

    print("signalsAtTerminal monitor – period {} ms".format(period_ms))
    print("  ADC_TR  ADC_BR |  OUT_TR  OUT_BR  [V]")

    try:
        while True:
            v_tr = _read_volts(adc_th, scale)
            v_br = _read_volts(adc_br, scale)

            if v_tr is None or v_br is None:
                out_tr = None
                out_br = None
            else:
                out_tr, out_br = compute_output_voltages(v_tr, v_br, cfg)

            line = " {0} {1} |  {2}  {3}".format(_fmt(v_tr), _fmt(v_br), _fmt(out_tr), _fmt(out_br))
            print(line)
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(period_ms)
            else:
                time.sleep(period_ms / 1000.0)
    except KeyboardInterrupt:
        print("\n[signalsAtTerminal] stopped")


if __name__ == "__main__":
    run()
