
# motor_control.py
# Control de acelerador/freno con ADC locales y DAC MCP4725 ejecutado en asyncio.

import machine
import uasyncio as asyncio
import time

try:
    from drivers.mcp4725 import MCP4725
except ImportError:
    from mcp4725 import MCP4725

from HW import (
    ADC_THROTTLE_PIN,
    ADC_BRAKE_PIN,
    DAC0_ADDR,
    DAC1_ADDR,
    I2C_ID,
    I2C_SCL,
    I2C_SDA,
)

__all__ = [
    "MotorControl",
    "compute_output_voltages",
    "DEFAULTS",
]

DEFAULTS = {
    "i2c_id": I2C_ID,
    "scl": I2C_SCL,
    "sda": I2C_SDA,
    "i2c_freq": 400_000,
    "adc_pin_throttle": ADC_THROTTLE_PIN,
    "adc_pin_brake": ADC_BRAKE_PIN,
    "adc_vref": 3.3,
    "dac_vref": 3.3,
    "dac_addr_throttle": DAC0_ADDR,
    "dac_addr_brake": DAC1_ADDR,
    "throttle_supply_voltage": 3.3,
    "throttle_input_min": 0.85,
    "throttle_input_max": 1.85,
    "throttle_output_min": 1.4,
    "throttle_output_max": 3.3,
    "throttle_factor": 1.0,
    "throttle_mode": "power",
    "throttle_power_max_w": 500.0,
    "throttle_speed_max_kmh": 50.0,
    "throttle_mix_speed_kmh": 20.0,
    "throttle_mix_hyst_kmh": 3.0,
    "throttle_control_gain": 0.25,
    "throttle_filter_alpha": 0.3,
    "throttle_ratio_alpha": 0.4,
    "throttle_torque_ref_speed_kmh": 10.0,
    "brake_supply_voltage": 3.3,
    "brake_input_min": 0.85,
    "brake_input_threshold": 1.6,
    "brake_input_max": 1.85,
    "brake_output_min": 1.5,
    "brake_output_max": 3.3,
    "brake_factor": 1.0,
    "brake_threshold": 1.6,
    "adc_tr_offset": 0.18,
    "adc_tr_scale": 1.0,
    "adc_br_offset": 0.18,
    "adc_br_scale": 1.0,
    "update_period_ms": 20,
}


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _volts_to_dac12(volts, vref):
    clipped = _clamp(volts, 0.0, vref)
    return int((clipped / vref) * 4095 + 0.5)


def _to_float(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            if not value:
                return 0.0
            return float(value)
        if hasattr(value, "__float__"):
            return float(value)  # type: ignore[arg-type]
    except Exception:
        return None
    return None


def _throttle_ratio_from_adc(vt, cfg):
    throttle_min = float(cfg.get("throttle_input_min", 0.85))
    throttle_max = float(cfg.get("throttle_input_max", 1.85))
    throttle_span = (throttle_max - throttle_min) or 1.0
    try:
        vt_val = float(vt)
    except (TypeError, ValueError):
        vt_val = 0.0
    return _clamp((vt_val - throttle_min) / throttle_span, 0.0, 1.0)


def _low_pass(prev, value, alpha):
    if value is None:
        return None
    alpha = _clamp(alpha, 0.0, 1.0)
    if prev is None or alpha >= 1.0:
        return value
    if alpha <= 0.0:
        return prev
    return prev + alpha * (value - prev)


def compute_output_voltages(vt, vb, cfg, *, control_ratio=None, raw_ratio=None):
    try:
        vt = float(vt)
    except (TypeError, ValueError):
        vt = 0.0
    try:
        vb = float(vb)
    except (TypeError, ValueError):
        vb = 0.0

    throttle_min = float(cfg.get("throttle_input_min", 0.85))
    throttle_max = float(cfg.get("throttle_input_max", 1.85))
    throttle_out_min = float(cfg.get("throttle_output_min", 1.4))
    throttle_out_max = float(cfg.get("throttle_output_max", cfg.get("dac_vref", 3.3)))
    try:
        throttle_factor = float(cfg.get("throttle_factor", 1.0))
    except (TypeError, ValueError):
        throttle_factor = 1.0
    throttle_factor = _clamp(throttle_factor, 0.0, 1.0)

    brake_threshold = float(cfg.get("brake_input_threshold", cfg.get("brake_threshold", 1.6)))
    brake_max = float(cfg.get("brake_input_max", 1.85))
    brake_out_min = float(cfg.get("brake_output_min", 1.5))
    brake_out_max = float(cfg.get("brake_output_max", cfg.get("dac_vref", 3.3)))
    try:
        brake_factor = float(cfg.get("brake_factor", 1.0))
    except (TypeError, ValueError):
        brake_factor = 1.0
    brake_factor = _clamp(brake_factor, 0.0, 1.0)

    max_tr_v = float(cfg.get("dac_vref", 3.3))
    max_br_v = min(brake_out_max, float(cfg.get("dac_vref", 3.3)))

    brake_span = (brake_max - brake_threshold) or 1.0

    if vb < brake_threshold:
        if raw_ratio is None:
            raw_ratio = _throttle_ratio_from_adc(vt, cfg)
        ratio_tr = control_ratio if control_ratio is not None else raw_ratio
        ratio_tr = _clamp(ratio_tr, 0.0, 1.0)
        out_tr = throttle_out_min + ratio_tr * throttle_factor * (throttle_out_max - throttle_out_min)
        out_tr = _clamp(out_tr, throttle_out_min, throttle_out_max)
        out_br = brake_out_min
    else:
        out_tr = throttle_out_min
        ratio_br = _clamp((vb - brake_threshold) / brake_span, 0.0, 1.0)
        out_br = brake_out_min + ratio_br * brake_factor * (brake_out_max - brake_out_min)

    out_tr = _clamp(out_tr, 0.0, max_tr_v)
    out_br = _clamp(out_br, 0.0, max_br_v)
    return out_tr, out_br


class MotorControl:
    def __init__(self, **kwargs):
        self.cfg = DEFAULTS.copy()
        self.cfg.update(kwargs)

        self.is_stub = False

        self._i2c = None
        self._adc_t = None
        self._adc_b = None
        self._dac_th = None
        self._dac_br = None

        self.dac_status = {"throttle": False, "brake": False}
        self._dac_error_reported = {"throttle": False, "brake": False}

        self.last_vt = 0.0
        self.last_vb = 0.0
        self.last_vt_raw = 0.0
        self.last_vb_raw = 0.0
        self.last_code_th = 0
        self.last_code_br = 0
        self.last_dac_throttle_v = 0.0
        self.last_dac_brake_v = 0.0
        self.brake_active = False
        self._state = None
        self._control_ratio = None
        self.last_ratio_raw = 0.0
        self.last_ratio_control = 0.0
        self._filtered_power = None
        self._filtered_speed = None
        self._filtered_torque = None
        self._mix_use_speed = False

    def _ensure_i2c(self):
        if self._i2c is not None:
            return
        try:
            self._i2c = machine.I2C(
                int(self.cfg["i2c_id"]),
                scl=machine.Pin(int(self.cfg["scl"])),
                sda=machine.Pin(int(self.cfg["sda"])),
                freq=int(self.cfg["i2c_freq"]),
            )
        except Exception as exc:
            print("[MotorControl] I2C init error:", exc)
            self._i2c = None

    def _ensure_adcs(self):
        if self._adc_t is not None and self._adc_b is not None:
            return
        try:
            self._adc_t = machine.ADC(machine.Pin(int(self.cfg["adc_pin_throttle"])))
            self._adc_b = machine.ADC(machine.Pin(int(self.cfg["adc_pin_brake"])))
            attn = getattr(machine.ADC, "ATTN_11DB", None)
            width = getattr(machine.ADC, "WIDTH_12BIT", None)
            for adc in (self._adc_t, self._adc_b):
                try:
                    atten_fn = getattr(adc, "atten", None)
                    if callable(atten_fn) and attn is not None:
                        atten_fn(attn)
                    width_fn = getattr(adc, "width", None)
                    if callable(width_fn) and width is not None:
                        width_fn(width)
                except Exception:
                    pass
        except Exception as exc:
            print("[MotorControl] ADC init error:", exc)
            self._adc_t = None
            self._adc_b = None

    def _ensure_dacs(self):
        if self._dac_th is not None and self._dac_br is not None:
            return
        if self._i2c is None:
            return
        try:
            self._dac_th = MCP4725(self._i2c, address=int(self.cfg["dac_addr_throttle"]))
            self._report_dac_ok("throttle")
        except Exception as exc:
            self._dac_th = None
            self._report_dac_error("throttle", exc)
        try:
            self._dac_br = MCP4725(self._i2c, address=int(self.cfg["dac_addr_brake"]))
            self._report_dac_ok("brake")
        except Exception as exc:
            self._dac_br = None
            self._report_dac_error("brake", exc)

        for dac, label in ((self._dac_th, "throttle"), (self._dac_br, "brake")):
            if dac is None:
                continue
            try:
                write = getattr(dac, "write", None)
                if callable(write):
                    write(0)
                    self._report_dac_ok(label)
            except Exception as exc:
                self._report_dac_error(label, exc)

    def _ensure_hw(self):
        self._ensure_i2c()
        self._ensure_adcs()
        self._ensure_dacs()

    def _adc_read_volts(self, adc):
        if adc is None:
            return None
        reader = getattr(adc, "read", None) or getattr(adc, "read_u16", None)
        if reader is None:
            return None
        try:
            raw = reader()
        except Exception:
            return None
        try:
            numeric = float(raw)
        except Exception:
            return None
        return (numeric * float(self.cfg.get("adc_vref", 3.3))) / 4095.0

    def _calibrate_adc(self, value, kind):
        if value is None:
            return None
        if kind == "throttle":
            scale = float(self.cfg.get("adc_tr_scale", 1.0) or 1.0)
            offset = float(self.cfg.get("adc_tr_offset", 0.0) or 0.0)
        else:
            scale = float(self.cfg.get("adc_br_scale", 1.0) or 1.0)
            offset = float(self.cfg.get("adc_br_offset", 0.0) or 0.0)
        try:
            return value * scale + offset
        except Exception:
            return value

    def _extract_speed_kmh(self):
        st = self._state
        if st is None:
            return None
        vehicle_speed_fn = getattr(st, "vehicle_speed", None)
        if callable(vehicle_speed_fn):
            try:
                value = vehicle_speed_fn()
            except Exception:
                value = None
            converted = _to_float(value)
            if converted is not None:
                return converted
        try:
            counter_available = bool(getattr(st, "trip_counter_available"))
        except Exception:
            counter_available = False
        if counter_available:
            try:
                return float(getattr(st, "trip_speed_kmh", 0.0) or 0.0)
            except Exception:
                return 0.0
        get_pr = getattr(st, "get_pr", None)
        if callable(get_pr):
            try:
                result = get_pr("vehicle_speed", (None, ""))
            except Exception:
                result = None
            if result is None:
                try:
                    result = get_pr("vehicle_speed_PR", (None, ""))
                except Exception:
                    result = None
            if result is not None:
                try:
                    if isinstance(result, (tuple, list)):
                        result = result[0]
                    converted = _to_float(result)
                    if converted is not None:
                        return converted
                except Exception:
                    pass
        return None

    def _extract_power_w(self):
        st = self._state
        if st is None:
            return None
        get_pr = getattr(st, "get_pr", None)
        if not callable(get_pr):
            return None
        try:
            result = get_pr("motor_input_power", (None, ""))
        except Exception:
            result = None
        if result is not None:
            try:
                if isinstance(result, (tuple, list)):
                    result = result[0]
                converted = _to_float(result)
                if converted is not None:
                    return converted
            except Exception:
                pass
        voltage = None
        current = None
        try:
            v_res = get_pr("battery_voltage", (None, ""))
        except Exception:
            v_res = None
        try:
            c_res = get_pr("battery_current", (None, ""))
        except Exception:
            c_res = None
        if isinstance(v_res, (tuple, list)):
            voltage = v_res[0]
        else:
            voltage = v_res
        if isinstance(c_res, (tuple, list)):
            current = c_res[0]
        else:
            current = c_res
        try:
            v_val = _to_float(voltage)
            c_val = _to_float(current)
            if v_val is not None and c_val is not None:
                return v_val * c_val
        except Exception:
            pass
        return None

    def _control_with_metric(self, desired_ratio, metric_value, metric_max, *, filter_attr, gain, filter_alpha, ratio_alpha):
        metric_max = float(metric_max or 0.0)
        if metric_value is None or metric_max <= 0.0:
            setattr(self, filter_attr, None)
            self._control_ratio = desired_ratio
            return desired_ratio
        filtered_prev = getattr(self, filter_attr)
        filtered = _low_pass(filtered_prev, float(metric_value), filter_alpha)
        setattr(self, filter_attr, filtered)
        if filtered is None:
            self._control_ratio = desired_ratio
            return desired_ratio
        normalized = _clamp(filtered / metric_max, 0.0, 2.0)
        target_ratio = desired_ratio + gain * (desired_ratio - normalized)
        target_ratio = _clamp(target_ratio, 0.0, 1.0)
        prev_ratio = self._control_ratio if self._control_ratio is not None else desired_ratio
        smoothed = _low_pass(prev_ratio, target_ratio, ratio_alpha)
        if smoothed is None:
            smoothed = target_ratio
        smoothed = _clamp(smoothed, 0.0, 1.0)
        self._control_ratio = smoothed
        return smoothed

    def _apply_control_mode(self, ratio_input, *, brake_active):
        if brake_active:
            self._control_ratio = 0.0
            self._filtered_power = None
            self._filtered_speed = None
            self._filtered_torque = None
            return 0.0

        mode = str(self.cfg.get("throttle_mode", "power") or "").lower()
        if not mode or mode in {"basic", "none", "off"} or self._state is None:
            self._control_ratio = ratio_input
            return ratio_input

        if mode != "mix":
            self._mix_use_speed = False

        if mode in {"open", "open_loop", "direct", "raw"}:
            self._control_ratio = ratio_input
            self._filtered_power = None
            self._filtered_speed = None
            self._filtered_torque = None
            self._mix_use_speed = False
            return ratio_input

        gain = max(0.0, float(self.cfg.get("throttle_control_gain", 0.25) or 0.0))
        if gain <= 0.0:
            self._control_ratio = ratio_input
            return ratio_input

        filter_alpha = _clamp(float(self.cfg.get("throttle_filter_alpha", 0.3) or 0.0), 0.0, 1.0)
        ratio_alpha = _clamp(float(self.cfg.get("throttle_ratio_alpha", 0.4) or 0.0), 0.0, 1.0)

        power_w = self._extract_power_w()
        speed_kmh = self._extract_speed_kmh()
        max_power = max(1.0, float(self.cfg.get("throttle_power_max_w", 500.0) or 1.0))
        max_speed = max(1.0, float(self.cfg.get("throttle_speed_max_kmh", 50.0) or 1.0))

        if mode == "power":
            return self._control_with_metric(
                ratio_input,
                power_w,
                max_power,
                filter_attr="_filtered_power",
                gain=gain,
                filter_alpha=filter_alpha,
                ratio_alpha=ratio_alpha,
            )

        if mode == "speed":
            return self._control_with_metric(
                ratio_input,
                speed_kmh,
                max_speed,
                filter_attr="_filtered_speed",
                gain=gain,
                filter_alpha=filter_alpha,
                ratio_alpha=ratio_alpha,
            )

        if mode == "torque":
            torque = None
            if power_w is not None:
                speed_mps = max((speed_kmh or 0.0) / 3.6, 0.3)
                torque = float(power_w) / speed_mps
            ref_speed = max(0.1, float(self.cfg.get("throttle_torque_ref_speed_kmh", 10.0) or 0.1))
            ref_speed_mps = max(ref_speed / 3.6, 0.3)
            max_speed_mps = max(max_speed / 3.6, ref_speed_mps)
            torque_max = max_power / max_speed_mps
            return self._control_with_metric(
                ratio_input,
                torque,
                torque_max,
                filter_attr="_filtered_torque",
                gain=gain,
                filter_alpha=filter_alpha,
                ratio_alpha=ratio_alpha,
            )

        if mode == "mix":
            threshold = float(self.cfg.get("throttle_mix_speed_kmh", 20.0) or 0.0)
            hyst = abs(float(self.cfg.get("throttle_mix_hyst_kmh", 3.0) or 0.0))
            if self._mix_use_speed:
                if speed_kmh is None or speed_kmh < (threshold - hyst):
                    self._mix_use_speed = False
            else:
                if speed_kmh is not None and speed_kmh >= threshold:
                    self._mix_use_speed = True
            if self._mix_use_speed:
                return self._control_with_metric(
                    ratio_input,
                    speed_kmh,
                    max_speed,
                    filter_attr="_filtered_speed",
                    gain=gain,
                    filter_alpha=filter_alpha,
                    ratio_alpha=ratio_alpha,
                )
            torque = None
            if power_w is not None:
                speed_mps = max((speed_kmh or 0.0) / 3.6, 0.3)
                torque = float(power_w) / speed_mps
            ref_speed = max(0.1, float(self.cfg.get("throttle_torque_ref_speed_kmh", 10.0) or 0.1))
            ref_speed_mps = max(ref_speed / 3.6, 0.3)
            max_speed_mps = max(max_speed / 3.6, ref_speed_mps)
            torque_max = max_power / max_speed_mps
            return self._control_with_metric(
                ratio_input,
                torque,
                torque_max,
                filter_attr="_filtered_torque",
                gain=gain,
                filter_alpha=filter_alpha,
                ratio_alpha=ratio_alpha,
            )

        self._control_ratio = ratio_input
        return ratio_input

    def set_throttle_mode(self, mode):
        try:
            label = str(mode or "").strip().lower()
        except Exception:
            return False
        if not label:
            return False
        self.cfg["throttle_mode"] = label
        self._control_ratio = None
        self._filtered_power = None
        self._filtered_speed = None
        self._filtered_torque = None
        self._mix_use_speed = False
        return True

    def bind_state(self, state):
        self._state = state

    def get_last_samples(self):
        return self.last_vt, self.last_vb

    def get_last_outputs(self):
        return self.last_dac_throttle_v, self.last_dac_brake_v

    async def sample_voltages(self, samples=1, delay_ms=0):
        self._ensure_hw()
        samples = max(1, int(samples))
        delay_ms = max(0, int(delay_ms))
        acc_t = 0.0
        acc_b = 0.0
        count = 0
        for idx in range(samples):
            vt_raw = self._adc_read_volts(self._adc_t)
            vb_raw = self._adc_read_volts(self._adc_b)
            vt = self._calibrate_adc(vt_raw, "throttle")
            vb = self._calibrate_adc(vb_raw, "brake")
            if vt is not None:
                acc_t += vt
            if vb is not None:
                acc_b += vb
            count += 1
            if delay_ms and idx + 1 < samples:
                await asyncio.sleep_ms(delay_ms)
        if count <= 0:
            return (0.0, 0.0)
        return (acc_t / count, acc_b / count)

    async def run(self, period_ms=None):
        if period_ms is None:
            period_ms = int(self.cfg.get("update_period_ms", 20) or 20)
        period_ms = max(1, period_ms)
        self._ensure_hw()
        while True:
            loop_started = _ticks_ms_int()
            try:
                self._ensure_hw()
                vt_raw = self._adc_read_volts(self._adc_t)
                vb_raw = self._adc_read_volts(self._adc_b)
                vt = self._calibrate_adc(vt_raw, "throttle")
                vb = self._calibrate_adc(vb_raw, "brake")
                if vt is None:
                    vt = 0.0
                if vb is None:
                    vb = 0.0

                raw_ratio = _throttle_ratio_from_adc(vt, self.cfg)
                brake_threshold_cfg = self.cfg.get("brake_input_threshold", self.cfg.get("brake_threshold", 1.6))
                try:
                    brake_threshold = float(brake_threshold_cfg)
                except Exception:
                    brake_threshold = 1.6
                brake_active = vb >= brake_threshold
                control_ratio = self._apply_control_mode(raw_ratio, brake_active=brake_active)
                if control_ratio is None:
                    control_ratio = raw_ratio
                control_ratio = _clamp(control_ratio, 0.0, 1.0)
                raw_ratio = _clamp(raw_ratio, 0.0, 1.0)

                out_tr, out_br = compute_output_voltages(
                    vt,
                    vb,
                    self.cfg,
                    control_ratio=control_ratio,
                    raw_ratio=raw_ratio,
                )

                state = self._state
                guard_voltage = None
                guard_active = False
                if state is not None:
                    guard_active = bool(getattr(state, "battery_guard_active", False))
                    guard_voltage = getattr(state, "battery_guard_throttle_v", None)
                if guard_active and guard_voltage is not None:
                    try:
                        guard_value = float(guard_voltage)
                    except Exception:
                        guard_value = None
                    if guard_value is not None:
                        if out_tr > guard_value:
                            out_tr = guard_value
                        if state is not None:
                            state.battery_guard_applied = True
                    else:
                        if state is not None:
                            state.battery_guard_applied = False
                else:
                    if state is not None:
                        state.battery_guard_applied = False

                code_th = _volts_to_dac12(out_tr, self.cfg["dac_vref"])
                code_br = _volts_to_dac12(out_br, self.cfg["dac_vref"])

                try:
                    write_th = getattr(self._dac_th, "write", None)
                    if callable(write_th):
                        result = write_th(code_th)
                        if result is False:
                            raise RuntimeError("write returned False")
                        self._report_dac_ok("throttle")
                    elif self._dac_th is None:
                        self._report_dac_error("throttle", "not available")
                except Exception as exc:
                    self._report_dac_error("throttle", exc)
                try:
                    write_br = getattr(self._dac_br, "write", None)
                    if callable(write_br):
                        result = write_br(code_br)
                        if result is False:
                            raise RuntimeError("write returned False")
                        self._report_dac_ok("brake")
                    elif self._dac_br is None:
                        self._report_dac_error("brake", "not available")
                except Exception as exc:
                    self._report_dac_error("brake", exc)

                self.last_vt_raw = vt_raw if vt_raw is not None else vt
                self.last_vb_raw = vb_raw if vb_raw is not None else vb
                self.last_vt = vt
                self.last_vb = vb
                self.last_code_th = code_th
                self.last_code_br = code_br
                self.last_dac_throttle_v = out_tr
                self.last_dac_brake_v = out_br
                self.brake_active = vb >= brake_threshold
                self.last_ratio_raw = raw_ratio
                self.last_ratio_control = control_ratio

                if self._state is not None:
                    try:
                        self._state.throttle_v = vt
                        self._state.brake_v = vb
                        self._state.brake_v_raw = self.last_vb_raw
                        self._state.throttle_v_raw = self.last_vt_raw
                        self._state.dac_throttle_v = out_tr
                        self._state.dac_brake_v = out_br
                        self._state.throttle_ratio_raw = raw_ratio
                        self._state.throttle_ratio_control = control_ratio
                        try:
                            current_mode = str(self.cfg.get("throttle_mode", "") or "")
                        except Exception:
                            current_mode = ""
                        self._state.throttle_mode_active = current_mode.lower()
                        self._state.motor_control = self
                    except Exception:
                        pass
            except Exception as exc:
                print("[MotorControl] loop error:", exc)
            elapsed = _ticks_diff_int(_ticks_ms_int(), loop_started)
            wait_ms = period_ms - max(0, int(elapsed))
            if wait_ms > 0:
                await asyncio.sleep_ms(wait_ms)
            else:
                await asyncio.sleep_ms(0)

    def _report_dac_error(self, kind, exc):
        self.dac_status[kind] = False
        if not self._dac_error_reported[kind]:
            print("[MotorControl] DAC {} issue:".format(kind), exc)
            self._dac_error_reported[kind] = True

    def _report_dac_ok(self, kind):
        if not self.dac_status[kind]:
            print("[MotorControl] DAC {} ready".format(kind))
        self.dac_status[kind] = True
        self._dac_error_reported[kind] = False


def _ticks_ms_int():
    value = time.ticks_ms()
    if value is None:
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _ticks_diff_int(now, then):
    try:
        return int(time.ticks_diff(int(now), int(then)))
    except Exception:
        return 0

