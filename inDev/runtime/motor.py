"""Motor configuration helpers and fallback controller for the eBikeWatch runtime."""

import uasyncio as asyncio

try:
    import ujson as json
except ImportError:  # pragma: no cover - CPython fallback
    import json

from HW import ADC_THROTTLE_PIN, ADC_BRAKE_PIN, make_adc
from motor_control import MotorControl, DEFAULTS as MOTOR_DEFAULTS, compute_output_voltages

MOTOR_CONFIG_FILE = "motor_config.json"


class FallbackMotorControl:
    """Lightweight controller used when MotorControl cannot be initialized."""

    is_stub = True

    def __init__(self, cfg, reason=None):
        self.cfg = dict(cfg) if isinstance(cfg, dict) else {}
        self.last_vt = 0.0
        self.last_vb = 0.0
        self.last_dac_throttle_v = 0.0
        self.last_dac_brake_v = 0.0
        self.last_ratio_raw = 0.0
        self.last_ratio_control = 0.0
        self.brake_active = False
        self._state = None
        self._reason = reason
        self._adc_th = None
        self._adc_br = None
        self._adc_error_reported = False
        if reason is not None:
            try:
                print("[Motor] fallback controller", reason)
            except Exception:
                pass

    # --- Runtime API -------------------------------------------------
    def bind_state(self, state):
        self._state = state

    def get_last_samples(self):
        return self.last_vt, self.last_vb

    def get_last_outputs(self):
        return self.last_dac_throttle_v, self.last_dac_brake_v

    def set_throttle_mode(self, mode):
        try:
            label = str(mode or "").strip().lower()
        except Exception:
            label = ""
        if not label:
            return False
        self.cfg["throttle_mode"] = label
        return True

    async def sample_voltages(self, samples=1, delay_ms=0):
        self._ensure_adcs()
        samples = max(1, int(samples))
        delay = max(0, int(delay_ms)) if delay_ms is not None else 0
        acc_t = 0.0
        acc_b = 0.0
        count = 0
        for idx in range(samples):
            vt, vb = self._read_voltages_once()
            acc_t += vt
            acc_b += vb
            count += 1
            if delay and idx + 1 < samples:
                await asyncio.sleep_ms(delay)
        if count <= 0:
            return 0.0, 0.0
        return acc_t / count, acc_b / count

    async def run(self, period_ms=None):
        period = int(period_ms) if period_ms else int(self.cfg.get("update_period_ms", 1000) or 1000)
        while True:
            self._ensure_adcs()
            vt, vb = self._read_voltages_once()
            self.last_vt = vt
            self.last_vb = vb
            self.last_dac_throttle_v = 0.0
            self.last_dac_brake_v = 0.0
            self.brake_active = vb >= self.cfg.get("brake_threshold", 2.8)
            if self._state is not None:
                try:
                    self._state.throttle_v = vt
                    self._state.brake_v = vb
                    self._state.dac_throttle_v = 0.0
                    self._state.dac_brake_v = 0.0
                    self._state.motor_control = self
                except Exception:
                    pass
            await asyncio.sleep_ms(period)

    # --- Helpers -----------------------------------------------------
    def _ensure_adcs(self):
        if self._adc_th is not None and self._adc_br is not None:
            return
        try:
            if self._adc_th is None:
                pin_t = int(self.cfg.get("adc_pin_throttle", ADC_THROTTLE_PIN))
                self._adc_th = make_adc(pin_t)
            if self._adc_br is None:
                pin_b = int(self.cfg.get("adc_pin_brake", ADC_BRAKE_PIN))
                self._adc_br = make_adc(pin_b)
        except Exception as exc:
            if not self._adc_error_reported:
                print("[Motor fallback] ADC init error:", exc)
                self._adc_error_reported = True
            self._adc_th = None
            self._adc_br = None

    def _read_voltages_once(self):
        vt = self._adc_read_volts(self._adc_th)
        vb = self._adc_read_volts(self._adc_br)
        return (vt if vt is not None else 0.0, vb if vb is not None else 0.0)

    def _adc_read_volts(self, adc):
        if adc is None:
            return None
        read = getattr(adc, "read", None)
        if callable(read):
            try:
                raw = read()
                return (float(raw) * float(self.cfg.get("adc_vref", 3.3))) / 4095.0
            except Exception:
                return None
        read_u16 = getattr(adc, "read_u16", None)
        if callable(read_u16):
            try:
                raw = read_u16()
                return (float(raw) * float(self.cfg.get("adc_vref", 3.3))) / 65535.0
            except Exception:
                return None
        return None


def load_motor_config(config_path=MOTOR_CONFIG_FILE):
    cfg = MOTOR_DEFAULTS.copy()
    try:
        with open(config_path, "r") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def save_motor_config(cfg, config_path=MOTOR_CONFIG_FILE):
    if not isinstance(cfg, dict):
        return False
    payload = {}
    for key, value in cfg.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            payload[key] = value
        else:
            try:
                payload[key] = float(value)
            except Exception:
                continue
    try:
        with open(config_path, "w") as fh:
            json.dump(payload, fh)
        return True
    except Exception as exc:
        print("[Motor] config save error:", exc)
        return False


def create_motor_control(cfg, config_file=MOTOR_CONFIG_FILE):
    attempts = (
        lambda: MotorControl(**cfg),
        lambda: MotorControl(config_file=config_file),
        lambda: MotorControl(),
    )
    for factory in attempts:
        try:
            motor = factory()
        except TypeError:
            continue
        except OSError as exc:
            print("[Motor] init hardware error:", exc)
            return FallbackMotorControl(cfg, reason=exc)
        except Exception as exc:
            print("[Motor] init unexpected error:", exc)
            return FallbackMotorControl(cfg, reason=exc)
        current_cfg = getattr(motor, "cfg", None)
        if isinstance(current_cfg, dict):
            try:
                current_cfg.update(cfg)
            except Exception:
                pass
        return motor
    print("[Motor] init: unsupported constructor signature")
    return FallbackMotorControl(cfg, reason="unsupported constructor")


__all__ = [
    "FallbackMotorControl",
    "MOTOR_CONFIG_FILE",
    "load_motor_config",
    "save_motor_config",
    "create_motor_control",
    "compute_output_voltages",
    "MOTOR_DEFAULTS",
]
