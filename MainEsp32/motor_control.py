
# motor_control.py
# Control de acelerador/freno con ADC locales y DAC MCP4725 ejecutado en asyncio.

import machine
import uasyncio as asyncio
import time

try:
    from version import module_version
except ImportError:  # pragma: no cover
    def module_version(name, default=None):
        return default if default is not None else "0.0.0"

__version__ = module_version("motor_control")

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
    "throttle_speed_max_kmh": 60.0,
    "throttle_mix_speed_kmh": 20.0,
    "throttle_mix_hyst_kmh": 3.0,
    "throttle_control_gain": 0.25,
    "throttle_filter_alpha": 0.3,
    "throttle_ratio_alpha": 0.4,
    "power_pid_kp": 0.25,
    "power_pid_ki": 0.02,
    "power_pid_kd": 0.0,
    "power_pid_integral_limit": 0.5,
    "power_pid_d_alpha": 0.3,
    "power_pid_output_alpha": 0.4,
    "speed_pid_kp": 0.35,
    "speed_pid_ki": 0.03,
    "speed_pid_kd": 0.0,
    "speed_pid_integral_limit": 0.5,
    "speed_pid_d_alpha": 0.3,
    "speed_pid_output_alpha": 0.4,
    "torque_pid_kp": 0.3,
    "torque_pid_ki": 0.02,
    "torque_pid_kd": 0.0,
    "torque_pid_integral_limit": 0.5,
    "torque_pid_d_alpha": 0.3,
    "torque_pid_output_alpha": 0.4,
    "throttle_torque_ref_speed_kmh": 10.0,
    "monitor_control_enabled": False,
    "monitor_control_period_ms": 1000,
    "monitor_compact_anomalies": False,
    "monitor_compact_delta_pct": 5.0,
    "loop_timing_monitor_enabled": False,
    "pid_timing_debug_enabled": False,
    "pid_timing_debug_period_ms": 1000,
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
        self._pid_state = {
            "power": {"integral": 0.0, "derivative": 0.0, "last_error": 0.0, "last_output": None},
            "speed": {"integral": 0.0, "derivative": 0.0, "last_error": 0.0, "last_output": None},
            "torque": {"integral": 0.0, "derivative": 0.0, "last_error": 0.0, "last_output": None},
        }
        self._last_loop_ms = None
        self._forced_speed_target_kmh = None
        self._raw_ratio_override = None
        self._loop_period_avg_ms = None
        self._timing_stats = {
            "adc": {"avg": None, "last": 0.0},
            "dac": {"avg": None, "last": 0.0},
            "compute": {"avg": None, "last": 0.0},
            "sections": {
                "sensors": {"avg": None, "last": 0.0},
                "controller": {"avg": None, "last": 0.0},
                "post": {"avg": None, "last": 0.0},
                "other": {"avg": None, "last": 0.0},
            },
            "controller_sections": {},
        }
        self._monitor_task = None
        self._pid_debug_data = {}

    def _update_section_timing(self, section, elapsed_ms):
        sections = self._timing_stats.setdefault("sections", {})
        stats = sections.get(section)
        if stats is None:
            stats = {"avg": None, "last": 0.0}
            sections[section] = stats
        stats["last"] = elapsed_ms
        stats["avg"] = _low_pass(stats.get("avg"), elapsed_ms, 0.2)

    def _sections_timing_snapshot(self):
        sections = self._timing_stats.get("sections") or {}
        snapshot = {}
        for name, stats in sections.items():
            if not isinstance(stats, dict):
                continue
            avg = stats.get("avg")
            if avg is not None:
                snapshot[name] = avg
        return snapshot

    def _update_controller_timing(self, section, elapsed_ms):
        bucket = self._timing_stats.setdefault("controller_sections", {})
        stats = bucket.get(section)
        if stats is None:
            stats = {"avg": None, "last": 0.0}
            bucket[section] = stats
        stats["last"] = elapsed_ms
        stats["avg"] = _low_pass(stats.get("avg"), elapsed_ms, 0.2)

    def _controller_timing_snapshot(self):
        bucket = self._timing_stats.get("controller_sections") or {}
        snapshot = {}
        for name, stats in bucket.items():
            if not isinstance(stats, dict):
                continue
            avg = stats.get("avg")
            if avg is not None:
                snapshot[name] = avg
        return snapshot

    def _record_pid_debug(self, mode, **metrics):
        store = self._pid_debug_data.setdefault(mode, {})
        for key, value in metrics.items():
            store[key] = value
        store["timestamp_ms"] = _ticks_ms_int()

    def _format_pid_debug_line(self):
        if not self.cfg.get("pid_timing_debug_enabled"):
            return None
        if not self._pid_debug_data:
            return None
        parts = []
        order = ("speed", "power", "torque")
        for mode in order:
            entry = self._pid_debug_data.get(mode)
            if not entry:
                continue
            try:
                compute = entry.get("elapsed_ms")
                err = entry.get("error")
                integ = entry.get("integral")
                deriv = entry.get("derivative")
                dt_ms = entry.get("dt_ms")
                output = entry.get("output")
                target = entry.get("target")
                actual = entry.get("actual")
                parts.append(
                    "{}:err={:.3f} int={:.3f} der={:.3f} dt={:.0f}ms out={:.3f} tgt={:.3f} act={:.3f} pid={:.0f}ms".format(
                        mode,
                        err if err is not None else 0.0,
                        integ if integ is not None else 0.0,
                        deriv if deriv is not None else 0.0,
                        dt_ms if dt_ms else 0.0,
                        output if output is not None else 0.0,
                        target if target is not None else 0.0,
                        actual if actual is not None else 0.0,
                        compute if compute is not None else 0.0,
                    )
                )
            except Exception:
                continue
        if not parts:
            return None
        return " | ".join(parts)

    def _maybe_print_pid_debug_line(self):
        if not self.cfg.get("pid_timing_debug_enabled"):
            return
        line = self._format_pid_debug_line()
        if line:
            print("[MotorControl] pid-debug:", line)

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

    def _reset_pid(self, mode=None):
        targets = [mode] if mode else self._pid_state.keys()
        for key in targets:
            state = self._pid_state.get(key)
            if not state:
                continue
            state["integral"] = 0.0
            state["derivative"] = 0.0
            state["last_error"] = 0.0
            state["last_output"] = None

    def _get_pid_cfg(self, mode):
        prefix = f"{mode}_pid"
        kp = float(self.cfg.get(f"{prefix}_kp", self.cfg.get("throttle_control_gain", 0.25) or 0.0) or 0.0)
        ki = float(self.cfg.get(f"{prefix}_ki", 0.0) or 0.0)
        kd = float(self.cfg.get(f"{prefix}_kd", 0.0) or 0.0)
        i_limit = float(self.cfg.get(f"{prefix}_integral_limit", 0.5) or 0.0)
        d_alpha = _clamp(float(self.cfg.get(f"{prefix}_d_alpha", 0.3) or 0.0), 0.0, 1.0)
        output_alpha = _clamp(
            float(self.cfg.get(f"{prefix}_output_alpha", self.cfg.get("throttle_ratio_alpha", 0.4) or 0.0) or 0.0),
            0.0,
            1.0,
        )
        return {
            "kp": kp,
            "ki": ki,
            "kd": kd,
            "i_limit": abs(i_limit),
            "d_alpha": d_alpha,
            "output_alpha": output_alpha,
        }

    def _control_pid_with_metric(self, mode, desired_ratio, metric_value, metric_max, dt_ms):
        pid_start = _ticks_ms_int()
        cfg = self._get_pid_cfg(mode)
        kp = cfg["kp"]
        ki = cfg["ki"]
        kd = cfg["kd"]
        enabled = kp > 0.0 or ki > 0.0 or kd > 0.0
        throttle_factor = _clamp(float(self.cfg.get("throttle_factor", 1.0) or 1.0), 0.0, 1.0)
        base_ratio = _clamp(desired_ratio, 0.0, 1.0)
        # Point 4 optimization: reduce float conversions by normalizing inputs once.
        try:
            metric_value = float(metric_value)
        except Exception:
            metric_value = None
        try:
            metric_max = float(metric_max)
        except Exception:
            metric_max = None
        if not enabled or metric_value is None or metric_max is None or metric_max <= 0.0 or dt_ms is None:
            self._reset_pid(mode)
            self._control_ratio = base_ratio
            return base_ratio
        target_ratio = _clamp(base_ratio * throttle_factor, 0.0, 1.0)
        actual_ratio = _clamp(metric_value / metric_max, 0.0, 2.0)
        dt_ms = max(1, int(dt_ms))
        dt_s = dt_ms / 1000.0
        state = self._pid_state.get(mode)
        if state is None:
            state = {"integral": 0.0, "derivative": 0.0, "last_error": 0.0, "last_output": None}
            self._pid_state[mode] = state
        error = target_ratio - actual_ratio
        use_integral = ki > 0.0
        use_derivative = kd > 0.0
        if use_integral:
            integral = state["integral"] + error * dt_s
            integral = _clamp(integral, -cfg["i_limit"], cfg["i_limit"])
            state["integral"] = integral
        else:
            integral = 0.0
            state["integral"] = 0.0
        if use_derivative:
            deriv_raw = (error - state["last_error"]) / dt_s
            derivative = state["derivative"] + cfg["d_alpha"] * (deriv_raw - state["derivative"])
            state["derivative"] = derivative
        else:
            derivative = 0.0
            state["derivative"] = 0.0
        state["last_error"] = error
        output = base_ratio + kp * error
        if use_integral:
            output += ki * integral
        if use_derivative:
            output += kd * derivative
        prev = state["last_output"]
        alpha = cfg["output_alpha"]
        if prev is None or alpha <= 0.0:
            smoothed = output
        elif alpha >= 1.0:
            smoothed = prev + (output - prev)
        else:
            smoothed = prev + alpha * (output - prev)
        smoothed = _clamp(smoothed, 0.0, 1.0)
        state["last_output"] = smoothed
        self._control_ratio = smoothed
        pid_elapsed = _ticks_diff_int(_ticks_ms_int(), pid_start)
        self._update_controller_timing("pid_{}".format(mode), pid_elapsed)
        if self.cfg.get("pid_timing_debug_enabled"):
            self._record_pid_debug(
                mode,
                elapsed_ms=pid_elapsed,
                error=error,
                integral=integral,
                derivative=derivative,
                dt_ms=dt_ms,
                output=smoothed,
                target=target_ratio,
                actual=actual_ratio,
            )
        return smoothed

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

    def _apply_control_mode(self, ratio_input, *, brake_active, dt_ms=None):
        if brake_active:
            self._control_ratio = 0.0
            self._filtered_power = None
            self._filtered_speed = None
            self._filtered_torque = None
            self._raw_ratio_override = None
            self._reset_pid()
            return 0.0

        mode = str(self.cfg.get("throttle_mode", "power") or "").lower()
        if not mode or mode in {"basic", "none", "off"} or self._state is None:
            self._control_ratio = ratio_input
            self._reset_pid()
            return ratio_input

        if mode != "mix":
            self._mix_use_speed = False

        if mode in {"open", "open_loop", "direct", "raw"}:
            self._control_ratio = ratio_input
            self._reset_pid()
            self._filtered_power = None
            self._filtered_speed = None
            self._filtered_torque = None
            self._mix_use_speed = False
            return ratio_input

        power_start = _ticks_ms_int()
        power_w = self._extract_power_w()
        self._update_controller_timing("power_fetch", _ticks_diff_int(_ticks_ms_int(), power_start))
        speed_start = _ticks_ms_int()
        speed_kmh = self._extract_speed_kmh()
        self._update_controller_timing("speed_fetch", _ticks_diff_int(_ticks_ms_int(), speed_start))
        max_power = max(1.0, float(self.cfg.get("throttle_power_max_w", 500.0) or 1.0))
        max_speed = max(1.0, float(self.cfg.get("throttle_speed_max_kmh", 50.0) or 1.0))

        forced_ratio = None
        if mode == "speed" and self._forced_speed_target_kmh is not None:
            forced_ratio = _clamp(self._forced_speed_target_kmh / max_speed, 0.0, 1.0)

        if forced_ratio is not None:
            ratio_input = forced_ratio
            self._raw_ratio_override = forced_ratio
        else:
            self._raw_ratio_override = None

        if mode == "power":
            return self._control_pid_with_metric("power", ratio_input, power_w, max_power, dt_ms)

        if mode == "speed":
            return self._control_pid_with_metric("speed", ratio_input, speed_kmh, max_speed, dt_ms)

        if mode == "torque":
            torque = None
            if power_w is not None:
                speed_mps = max((speed_kmh or 0.0) / 3.6, 0.3)
                torque = float(power_w) / speed_mps
            ref_speed = max(0.1, float(self.cfg.get("throttle_torque_ref_speed_kmh", 10.0) or 0.1))
            ref_speed_mps = max(ref_speed / 3.6, 0.3)
            max_speed_mps = max(max_speed / 3.6, ref_speed_mps)
            torque_max = max_power / max_speed_mps
            return self._control_pid_with_metric("torque", ratio_input, torque, torque_max, dt_ms)

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
                return self._control_pid_with_metric("speed", ratio_input, speed_kmh, max_speed, dt_ms)
            torque = None
            if power_w is not None:
                speed_mps = max((speed_kmh or 0.0) / 3.6, 0.3)
                torque = float(power_w) / speed_mps
            ref_speed = max(0.1, float(self.cfg.get("throttle_torque_ref_speed_kmh", 10.0) or 0.1))
            ref_speed_mps = max(ref_speed / 3.6, 0.3)
            max_speed_mps = max(max_speed / 3.6, ref_speed_mps)
            torque_max = max_power / max_speed_mps
            return self._control_pid_with_metric("torque", ratio_input, torque, torque_max, dt_ms)

        self._control_ratio = ratio_input
        return ratio_input

    def set_speed_target_override(self, kmh=None):
        if kmh is None:
            self._forced_speed_target_kmh = None
            self._raw_ratio_override = None
            return None
        try:
            value = float(kmh)
        except Exception as exc:
            raise ValueError("invalid speed target") from exc
        if value < 0.0:
            value = 0.0
        self._forced_speed_target_kmh = value
        return value

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
        self._reset_pid()
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
        self._refresh_monitor_task()
        while True:
            loop_started = _ticks_ms_int()
            self._refresh_monitor_task()
            try:
                self._ensure_hw()
                adc_start = _ticks_ms_int()
                vt_raw = self._adc_read_volts(self._adc_t)
                vb_raw = self._adc_read_volts(self._adc_b)
                adc_elapsed = _ticks_diff_int(_ticks_ms_int(), adc_start)
                self._timing_stats["adc"]["last"] = adc_elapsed
                self._timing_stats["adc"]["avg"] = _low_pass(self._timing_stats["adc"].get("avg"), adc_elapsed, 0.2)

                compute_start = _ticks_ms_int()
                sensors_elapsed = 0
                control_elapsed = 0
                post_elapsed = 0
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
                if self._last_loop_ms is None:
                    dt_ms = period_ms
                else:
                    dt_ms = _ticks_diff_int(loop_started, self._last_loop_ms)
                    if dt_ms <= 0:
                        dt_ms = period_ms
                self._last_loop_ms = loop_started
                try:
                    dt_float = float(dt_ms)
                except Exception:
                    dt_float = float(period_ms)
                self._loop_period_avg_ms = _low_pass(self._loop_period_avg_ms, dt_float, 0.2)
                sensors_elapsed = _ticks_diff_int(_ticks_ms_int(), compute_start)
                self._update_section_timing("sensors", sensors_elapsed)

                control_start = _ticks_ms_int()
                control_ratio = self._apply_control_mode(raw_ratio, brake_active=brake_active, dt_ms=dt_ms)
                control_elapsed = _ticks_diff_int(_ticks_ms_int(), control_start)
                self._update_section_timing("controller", control_elapsed)
                if control_ratio is None:
                    control_ratio = raw_ratio
                control_ratio = _clamp(control_ratio, 0.0, 1.0)
                if self._raw_ratio_override is not None:
                    raw_ratio = _clamp(self._raw_ratio_override, 0.0, 1.0)
                raw_ratio = _clamp(raw_ratio, 0.0, 1.0)

                post_start = _ticks_ms_int()
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
                post_elapsed = _ticks_diff_int(_ticks_ms_int(), post_start)
                self._update_section_timing("post", post_elapsed)

                compute_elapsed = _ticks_diff_int(_ticks_ms_int(), compute_start)
                self._timing_stats["compute"]["last"] = compute_elapsed
                self._timing_stats["compute"]["avg"] = _low_pass(self._timing_stats["compute"].get("avg"), compute_elapsed, 0.2)
                other_elapsed = compute_elapsed - (sensors_elapsed + control_elapsed + post_elapsed)
                if other_elapsed < 0:
                    other_elapsed = 0
                self._update_section_timing("other", other_elapsed)

                dac_start = _ticks_ms_int()
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
                dac_elapsed = _ticks_diff_int(_ticks_ms_int(), dac_start)
                self._timing_stats["dac"]["last"] = dac_elapsed
                self._timing_stats["dac"]["avg"] = _low_pass(self._timing_stats["dac"].get("avg"), dac_elapsed, 0.2)

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

    def _monitor_adc_percent(self, voltage):
        if voltage is None:
            return None
        try:
            base = float(self.cfg.get("throttle_monitor_min", self.cfg.get("throttle_input_min", 0.85) or 0.85))
        except Exception:
            base = 0.85
        try:
            max_override = self.cfg.get("throttle_monitor_max")
            if max_override is not None:
                top = float(max_override)
            else:
                span = float(self.cfg.get("throttle_monitor_span", 2.0) or 2.0)
                top = base + span
        except Exception:
            top = base + 2.0
        span = max(0.1, top - base)
        percent = _clamp((float(voltage) - base) / span, 0.0, 1.0) * 100.0
        return percent

    def _monitor_metric_context(self, raw_ratio):
        mode = str(self.cfg.get("throttle_mode", "power") or "").lower()
        throttle_factor = _clamp(float(self.cfg.get("throttle_factor", 1.0) or 1.0), 0.0, 1.0)
        target_ratio = _clamp(raw_ratio * throttle_factor, 0.0, 1.0)
        power_w = self._extract_power_w()
        speed_kmh = self._extract_speed_kmh()
        torque = None
        if power_w is not None:
            speed_mps = max((speed_kmh or 0.0) / 3.6, 0.3)
            torque = float(power_w) / speed_mps
        max_power = max(1.0, float(self.cfg.get("throttle_power_max_w", 500.0) or 1.0))
        max_speed = max(1.0, float(self.cfg.get("throttle_speed_max_kmh", 60.0) or 1.0))
        ref_speed = max(0.1, float(self.cfg.get("throttle_torque_ref_speed_kmh", 10.0) or 0.1))
        ref_speed_mps = max(ref_speed / 3.6, 0.3)
        max_speed_mps = max(max_speed / 3.6, ref_speed_mps)
        torque_max = max_power / max_speed_mps

        def _build(name, value, max_value, units):
            if max_value is None:
                target_value = None
            else:
                target_value = target_ratio * max_value
            return {
                "name": name,
                "value": value,
                "target": target_value,
                "max": max_value,
                "units": units,
            }

        if mode in {"open", "open_loop", "direct", "raw", "none", "off", "basic"}:
            return None
        if mode == "speed":
            return _build("speed", speed_kmh, max_speed, "km/h")
        if mode == "torque":
            return _build("torque", torque, torque_max, "Nm")
        if mode == "mix":
            if self._mix_use_speed:
                return _build("speed", speed_kmh, max_speed, "km/h")
            return _build("torque", torque, torque_max, "Nm")
        # Default to power
        return _build("power", power_w, max_power, "W")

    def _monitor_snapshot(self):
        try:
            raw_ratio_val = float(self.last_ratio_raw)
        except Exception:
            raw_ratio_val = 0.0
        try:
            control_ratio_val = float(self.last_ratio_control)
        except Exception:
            control_ratio_val = raw_ratio_val
        raw_ratio = _clamp(raw_ratio_val, 0.0, 1.0)
        control_ratio = _clamp(control_ratio_val, 0.0, 1.0)
        adc_pct = self._monitor_adc_percent(self.last_vt)
        metric_context = self._monitor_metric_context(raw_ratio)
        speed_kmh = self._extract_speed_kmh()
        try:
            mode_label = str(self.cfg.get("throttle_mode", "") or "").lower()
        except Exception:
            mode_label = ""
        sections_snapshot = self._sections_timing_snapshot()
        controller_sections = self._controller_timing_snapshot()
        pid_debug = None
        if self.cfg.get("pid_timing_debug_enabled") and self._pid_debug_data:
            pid_debug = {}
            for key, value in self._pid_debug_data.items():
                if isinstance(value, dict):
                    pid_debug[key] = value.copy()
        return {
            "mode": mode_label or "unknown",
            "adc_percent": adc_pct,
            "adc_voltage": self.last_vt,
            "raw_ratio": raw_ratio,
            "control_ratio": control_ratio,
            "dac_voltage": self.last_dac_throttle_v,
            "speed_kmh": speed_kmh,
            "metric": metric_context,
            "loop_period_ms": self._loop_period_avg_ms,
            "timing": {
                "adc": self._timing_stats["adc"].get("avg"),
                "dac": self._timing_stats["dac"].get("avg"),
                "compute": self._timing_stats["compute"].get("avg"),
                "sections": sections_snapshot,
                "controller": controller_sections,
            },
            "pid_debug": pid_debug,
        }

    def _monitor_indicator(self, target_pct, actual_pct):
        if target_pct is None or actual_pct is None:
            return "?"
        delta = target_pct - actual_pct
        if delta >= 10.0:
            return ">>"
        if delta >= 5.0:
            return ">"
        if delta <= -10.0:
            return "<<"
        if delta <= -5.0:
            return "<"
        return "="

    def _format_compact_monitor_line(
        self,
        *,
        adc_pct=None,
        adc_voltage=None,
        target=None,
        actual=None,
        units="",
        dac_voltage=None,
        delta_pct=None,
    ):
        parts = []
        if adc_pct is not None:
            if adc_voltage is not None:
                parts.append("ADC={:4.1f}% ({:.2f}V)".format(adc_pct, adc_voltage))
            else:
                parts.append("ADC={:4.1f}%".format(adc_pct))
        if target is not None:
            parts.append("target={:.1f}{}".format(target, units))
        if actual is not None:
            parts.append("speed={:.1f}{}".format(actual, units))
        if dac_voltage is not None:
            parts.append("DAC={:.2f}V".format(dac_voltage))
        if delta_pct is not None:
            parts.append("error={:+.1f}%".format(delta_pct))
        return " | ".join(parts) if parts else None

    def _format_monitor_line(self, snapshot):
        if not snapshot:
            return None
        mode = snapshot.get("mode", "unknown")
        adc_pct = snapshot.get("adc_percent")
        adc_line = "ADC=na"
        adc_voltage = snapshot.get("adc_voltage")
        if adc_pct is not None:
            if adc_voltage is not None:
                adc_line = "ADC={:4.1f}% ({:.2f}V)".format(adc_pct, adc_voltage)
            else:
                adc_line = "ADC={:4.1f}%".format(adc_pct)
        raw_ratio = snapshot.get("raw_ratio", 0.0)
        control_ratio = snapshot.get("control_ratio", raw_ratio)
        dac_voltage = snapshot.get("dac_voltage")
        dac_line = "DAC=na" if dac_voltage is None else "DAC={:.2f}V".format(dac_voltage)
        metric = snapshot.get("metric")
        show_timing = bool(self.cfg.get("loop_timing_monitor_enabled"))
        timing_desc = None
        if show_timing:
            timing = snapshot.get("timing") or {}
            if timing:
                adc = timing.get("adc")
                dac = timing.get("dac")
                comp = timing.get("compute")
                parts = []
                if adc is not None:
                    parts.append("ADC={:.0f}ms".format(adc))
                if comp is not None:
                    parts.append("CPU={:.0f}ms".format(comp))
                if dac is not None:
                    parts.append("DAC={:.0f}ms".format(dac))
                sections = timing.get("sections") or {}
                section_parts = []
                for key, label in (("sensors", "sens"), ("controller", "ctrl"), ("post", "post"), ("other", "other")):
                    value = sections.get(key)
                    if value is not None:
                        section_parts.append("{}={:.0f}ms".format(label, value))
                controller_details = timing.get("controller") or {}
                controller_parts = []
                controller_labels = (
                    ("speed_fetch", "spd"),
                    ("power_fetch", "pow"),
                    ("pid_speed", "pidS"),
                    ("pid_power", "pidP"),
                    ("pid_torque", "pidT"),
                )
                for key, label in controller_labels:
                    value = controller_details.get(key)
                    if value is not None:
                        controller_parts.append("{}={:.0f}ms".format(label, value))
                if parts or section_parts:
                    body = ", ".join(parts)
                    if section_parts:
                        detail = ", ".join(section_parts)
                        if body:
                            body = "{}; {}".format(body, detail)
                        else:
                            body = detail
                    if controller_parts:
                        ctrl_detail = ", ".join(controller_parts)
                        if body:
                            body = "{}; ctrl[{}]".format(body, ctrl_detail)
                        else:
                            body = "ctrl[{}]".format(ctrl_detail)
                    timing_desc = "timing[{}]".format(body)

        if metric is not None:
            name = metric.get("name", "metric")
            value = metric.get("value")
            target = metric.get("target")
            max_value = metric.get("max")
            units = metric.get("units", "")
            metric_pct = None
            target_pct = None
            if value is not None and max_value:
                metric_pct = _clamp(float(value) / float(max_value), 0.0, 2.0) * 100.0
            if target is not None and max_value:
                target_pct = _clamp(float(target) / float(max_value), 0.0, 2.0) * 100.0
            if metric_pct is None and control_ratio is not None:
                metric_pct = control_ratio * 100.0
            if target_pct is None and raw_ratio is not None:
                target_pct = raw_ratio * 100.0
            if target is None and target_pct is not None and max_value:
                target = (target_pct / 100.0) * max_value
            if value is None and metric_pct is not None and max_value:
                value = (metric_pct / 100.0) * max_value
            indicator = self._monitor_indicator(target_pct, metric_pct)
            unit_label = units or ""
            compact_enabled = bool(self.cfg.get("monitor_compact_anomalies"))
            compact_threshold = float(self.cfg.get("monitor_compact_delta_pct", 5.0) or 0.0)
            compact_delta = None
            if target_pct is not None and metric_pct is not None:
                compact_delta = target_pct - metric_pct
            if compact_enabled and compact_delta is not None:
                if abs(compact_delta) < compact_threshold:
                    return False
                compact_line = self._format_compact_monitor_line(
                    adc_pct=adc_pct,
                    adc_voltage=adc_voltage,
                    target=target,
                    actual=value,
                    units=unit_label,
                    dac_voltage=dac_voltage,
                    delta_pct=compact_delta,
                )
                if compact_line:
                    return compact_line
            if value is not None and metric_pct is not None:
                metric_desc = "{}={:.1f}{} ({:.1f}%)".format(name, value, unit_label, metric_pct)
            elif value is not None:
                metric_desc = "{}={:.1f}{}".format(name, value, unit_label)
            elif metric_pct is not None:
                metric_desc = "{}={:.1f}%".format(name, metric_pct)
            else:
                metric_desc = "{}=na".format(name)
            if target is not None and target_pct is not None:
                target_desc = "target={:.1f}{} ({:.1f}%)".format(target, unit_label, target_pct)
            elif target is not None:
                target_desc = "target={:.1f}{}".format(target, unit_label)
            elif target_pct is not None:
                target_desc = "target={:.1f}%".format(target_pct)
            else:
                target_desc = "target=na"
            loop_line = None
            loop_ms = snapshot.get("loop_period_ms")
            if loop_ms:
                try:
                    loop_hz = 1000.0 / loop_ms if loop_ms > 0 else 0.0
                    loop_line = "loop={:.0f}Hz ({:.0f}ms)".format(loop_hz, loop_ms)
                except Exception:
                    loop_line = None
            parts = [
                "mode={}".format(mode),
                adc_line,
                metric_desc,
                target_desc,
                dac_line,
                indicator,
            ]
            for extra in (loop_line, timing_desc):
                if extra:
                    parts.append(extra)
            return " | ".join(parts)
        # Fallback when no metric available
        indicator = self._monitor_indicator(raw_ratio * 100.0, control_ratio * 100.0)
        loop_line = None
        loop_ms = snapshot.get("loop_period_ms")
        if loop_ms:
            try:
                loop_hz = 1000.0 / loop_ms if loop_ms > 0 else 0.0
                loop_line = "loop={:.0f}Hz ({:.0f}ms)".format(loop_hz, loop_ms)
            except Exception:
                loop_line = None
        parts = [
            "mode={}".format(mode),
            adc_line,
            "raw={:.1f}%".format(raw_ratio * 100.0),
            "ctrl={:.1f}%".format(control_ratio * 100.0),
            dac_line,
            indicator,
        ]
        for extra in (loop_line, timing_desc):
            if extra:
                parts.append(extra)
        return " | ".join(parts)

    def _refresh_monitor_task(self):
        enabled = bool(self.cfg.get("monitor_control_enabled"))
        period_ms_cfg = self.cfg.get("monitor_control_period_ms", 1000)
        try:
            period_ms = max(200, int(period_ms_cfg))
        except Exception:
            period_ms = 1000
        if enabled:
            if self._monitor_task is not None:
                return
            task = None
            create_task = getattr(asyncio, "create_task", None)
            if callable(create_task):
                try:
                    task = create_task(self.monitor_control(period_ms=period_ms))
                except Exception:
                    task = None
            if task is None:
                get_loop = getattr(asyncio, "get_event_loop", None)
                if callable(get_loop):
                    try:
                        loop = get_loop()
                        loop_create = getattr(loop, "create_task", None)
                        if callable(loop_create):
                            task = loop_create(self.monitor_control(period_ms=period_ms))
                    except Exception:
                        task = None
            if task is None:
                return
            self._monitor_task = task
        else:
            if self._monitor_task is not None:
                task = self._monitor_task
                self._monitor_task = None
                cancel = getattr(task, "cancel", None)
                if callable(cancel):
                    try:
                        cancel()
                    except Exception:
                        pass

    def set_monitor_debug(self, enabled=True, period_ms=None):
        self.cfg["monitor_control_enabled"] = bool(enabled)
        if period_ms is not None:
            try:
                self.cfg["monitor_control_period_ms"] = max(200, int(period_ms))
            except Exception:
                pass
        return bool(self.cfg["monitor_control_enabled"])

    def set_monitor_compact_mode(self, *, anomalies_only=None, delta_pct=None):
        if anomalies_only is not None:
            self.cfg["monitor_compact_anomalies"] = bool(anomalies_only)
        if delta_pct is not None:
            try:
                value = float(delta_pct)
            except Exception:
                raise ValueError("invalid delta percentage")
            if value < 0.0:
                value = 0.0
            self.cfg["monitor_compact_delta_pct"] = value
        return {
            "anomalies_only": bool(self.cfg.get("monitor_compact_anomalies", False)),
            "delta_pct": float(self.cfg.get("monitor_compact_delta_pct", 5.0) or 0.0),
        }

    def set_loop_timing_monitor(self, enabled=None):
        if enabled is not None:
            self.cfg["loop_timing_monitor_enabled"] = bool(enabled)
        return bool(self.cfg.get("loop_timing_monitor_enabled"))

    def set_pid_timing_debug(self, enabled=True, period_ms=None):
        self.cfg["pid_timing_debug_enabled"] = bool(enabled)
        if period_ms is not None:
            try:
                self.cfg["pid_timing_debug_period_ms"] = max(200, int(period_ms))
            except Exception:
                pass
        return bool(self.cfg.get("pid_timing_debug_enabled"))

    async def monitor_control(self, period_ms=1000, *, once=False):
        period_ms = max(200, int(period_ms))
        try:
            while True:
                try:
                    snapshot = self._monitor_snapshot()
                    line = self._format_monitor_line(snapshot)
                    if line is False:
                        pass
                    elif line:
                        print("[MotorControl] monitor:", line)
                        self._maybe_print_pid_debug_line()
                    else:
                        print("[MotorControl] monitor: no data")
                except Exception as exc:
                    print("[MotorControl] monitor error:", exc)
                if once:
                    break
                await asyncio.sleep_ms(period_ms)
        except asyncio.CancelledError:
            return
        finally:
            current_task_fn = getattr(asyncio, "current_task", None)
            if callable(current_task_fn):
                try:
                    current = current_task_fn()
                    if current is not None and current is self._monitor_task:
                        self._monitor_task = None
                except Exception:
                    pass

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

