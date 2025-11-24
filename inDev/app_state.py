"""Shared application state container for the eBikeWatch runtime."""

import _thread
from time import ticks_ms, ticks_diff

import bats
from HW import ADC_THROTTLE_PIN, ADC_BRAKE_PIN, make_adc
from motor_control import DEFAULTS as MOTOR_DEFAULTS, compute_output_voltages

THROTTLE_MODES_DEFAULT = ["direct", "power", "speed", "torque", "mix"]
_CELL_FULL_DEFAULT = 4.15
_CELL_EMPTY_DEFAULT = 3.2
_CELL_GUARD_DEFAULT = 3.3


class AppState:
    """Mutable state shared across display, motor control, and telemetry tasks."""

    def __init__(self):
        self.screen = 0
        self._lock = _thread.allocate_lock()
        self.pr = {}  # name -> (value, unit)
        self.boot_ms = ticks_ms()
        self._last_int_ms = self.boot_ms
        self.km_total = 0.0
        self.wh_total = 0.0
        self.adc_throttle = None
        self.adc_brake = None
        self.throttle_v = 0.0
        self.brake_v = 0.0
        self.dac_throttle_v = 0.0
        self.dac_brake_v = 0.0
        self.battery_pack = None
        self.battery_pack_name = ""
        self.battery_voltage_v = 0.0
        self.battery_current_a = 0.0
        self.battery_power_w = 0.0
        self.battery_guard_throttle_v = 1.3
        self.battery_guard_active = False
        self.battery_guard_applied = False
        self.battery_actual_oper_voltage = 0.0
        self.battery_oper_voltage_empty = 0.0
        self.battery_remaining_wh = 0.0
        self.battery_capacity_wh_now = 0.0
        self.battery_max_wh = 0.0
        self.battery_max_power_w = 0.0
        self.battery_max_current_a = 0.0
        self.battery_voltage_max = 0.0
        self.battery_voltage_min = 0.0
        self.battery_guard_voltage = 0.0
        self.cell_avg_voltage = 0.0
        self.cell_avg_voltage_min = 3.3
        self.cell_voltage_span = 0.0
        self.guard_voltage_span = 0.0
        self.cell_empty_voltage = _CELL_EMPTY_DEFAULT
        self.cell_full_voltage = _CELL_FULL_DEFAULT
        self.pack_capacity_ah = 0.0
        self.battery_cells_series = 0
        self.battery_parallel = 1
        self.set_battery_pack(bats.load_current_pack())
        self.motor_control = None
        self.trip_pulses = 0
        self.trip_distance_m = 0.0
        self.trip_distance_km = 0.0
        self.trip_speed_kmh = 0.0
        self.trip_counter_available = False
        self.trip_counter_error = ""
        self.throttle_modes = list(THROTTLE_MODES_DEFAULT)
        self.throttle_mode_index = 0
        self.throttle_mode_active = "direct"
        self.throttle_mode_candidate = "direct"
        self.throttle_mode_confirmed_ms = 0
        self.throttle_ratio_raw = 0.0
        self.throttle_ratio_control = 0.0
        self.total_dashboards = 0

    def set_battery_pack(self, pack):
        if not isinstance(pack, dict):
            pack = {}
        self.battery_pack = dict(pack)
        self.battery_pack_name = pack.get("key", "")
        self.battery_max_wh = float(pack.get("pack_capacity_Wh", 0.0) or 0.0)
        self.battery_max_power_w = float(pack.get("max_power_w", 0.0) or 0.0)
        self.battery_max_current_a = float(pack.get("max_current_a", 0.0) or 0.0)
        self.battery_voltage_max = float(pack.get("max_voltage", 0.0) or 0.0)
        self.battery_voltage_min = float(pack.get("min_voltage", 0.0) or 0.0)
        self.battery_guard_voltage = float(pack.get("guard_voltage", 0.0) or 0.0)
        self.cell_avg_voltage_min = float(pack.get("cell_avg_voltage_min", 3.3) or 3.3)
        self.cell_voltage_span = float(pack.get("cell_voltage_span", 0.0) or 0.0)
        self.guard_voltage_span = float(pack.get("guard_span", 0.0) or 0.0)
        self.cell_empty_voltage = float(pack.get("cell_empty_v", _CELL_EMPTY_DEFAULT) or _CELL_EMPTY_DEFAULT)
        self.cell_full_voltage = float(pack.get("cell_full_v", _CELL_FULL_DEFAULT) or _CELL_FULL_DEFAULT)
        self.pack_capacity_ah = float(pack.get("pack_capacity_Ah", 0.0) or 0.0)
        guard_throttle = pack.get("guard_throttle_v")
        if guard_throttle is not None:
            try:
                self.battery_guard_throttle_v = float(guard_throttle)
            except Exception:
                pass
        self.battery_cells_series = int(pack.get("cells_series", 0) or 0)
        self.battery_parallel = int(pack.get("parallel", 1) or 1)
        self.battery_guard_active = False
        self.battery_guard_applied = False
        self.cell_avg_voltage = 0.0
        self.battery_actual_oper_voltage = 0.0
        self.battery_oper_voltage_empty = 0.0
        self.battery_remaining_wh = 0.0
        self.battery_capacity_wh_now = 0.0
        self.battery_voltage_v = 0.0
        self.battery_current_a = 0.0
        self.battery_power_w = 0.0

    def set_pr(self, name, value, unit):
        with self._lock:
            self.pr[name] = (value, unit)
            if name == "vehicle_speed_PR":
                self.pr["vehicle_speed"] = (value, unit)

    def get_pr(self, name, default=(None, "")):
        with self._lock:
            return self.pr.get(name, default)

    def snapshot_pr(self):
        with self._lock:
            return dict(self.pr)

    def init_local_adcs(self, *, force=False):
        if not force and self.motor_control is not None and self.adc_throttle is not None and self.adc_brake is not None:
            return
        try:
            self.adc_throttle = make_adc(ADC_THROTTLE_PIN)
            self.adc_brake = make_adc(ADC_BRAKE_PIN)
        except Exception:
            self.adc_throttle = None
            self.adc_brake = None

    def _adc_direct_read(self, adc):

        def update_battery_metrics(self):
            pack = self.battery_pack or {}
            cells_series = self.battery_cells_series or int(pack.get("cells_series", 0) or 0)

            voltage = self.get_pr("battery_voltage", (None, ""))[0]
            if voltage is None:
                voltage = self.get_pr("batt_voltage_calc", (None, ""))[0]
            if voltage is None:
                voltage = self.battery_voltage_v
            try:
                voltage = float(voltage)
            except Exception:
                voltage = 0.0

            current = self.get_pr("battery_current", (None, ""))[0]
            try:
                current = float(current)
            except Exception:
                current = 0.0

            power = voltage * current

            cell_avg = voltage / cells_series if cells_series > 0 else 0.0
            guard_cell_min = self.cell_avg_voltage_min or _CELL_GUARD_DEFAULT
            cell_full = self.cell_full_voltage or _CELL_FULL_DEFAULT
            cell_empty = self.cell_empty_voltage or _CELL_EMPTY_DEFAULT
            if cell_full <= cell_empty:
                cell_full = cell_empty + 0.01
            span_empty = cell_full - cell_empty
            span_guard = cell_full - guard_cell_min if guard_cell_min < cell_full else cell_full - cell_empty
            if span_guard < 0:
                span_guard = 0.0

            oper_from_empty = cell_avg - cell_empty
            if oper_from_empty < 0:
                oper_from_empty = 0.0
            if oper_from_empty > span_empty:
                oper_from_empty = span_empty

            oper_from_guard = cell_avg - guard_cell_min
            if oper_from_guard < 0:
                oper_from_guard = 0.0
            if span_guard > 0 and oper_from_guard > span_guard:
                oper_from_guard = span_guard

            ratio = (oper_from_empty / span_empty) if span_empty > 0 else 0.0
            if ratio < 0:
                ratio = 0.0
            if ratio > 1:
                ratio = 1.0

            self.battery_voltage_v = voltage
            self.battery_current_a = current
            self.battery_power_w = power
            self.cell_avg_voltage = cell_avg if cell_avg == cell_avg else 0.0
            self.battery_actual_oper_voltage = oper_from_guard
            self.battery_oper_voltage_empty = oper_from_empty
            self.battery_remaining_wh = self.battery_max_wh * ratio
            self.battery_capacity_wh_now = cells_series * oper_from_empty * self.pack_capacity_ah

            guard_trigger = cell_avg <= guard_cell_min and guard_cell_min > 0
            self.battery_guard_active = bool(guard_trigger)
            if not self.battery_guard_active:
                self.battery_guard_applied = False
        if adc is None:
            return None
            self.update_battery_metrics()
        reader = getattr(adc, "read", None)
        if reader is None:
            reader = getattr(adc, "read_u16", None)
            scale = 3.3 / 65535.0
        else:
            scale = 3.3 / 4095.0
        if reader is None:
            return None
        try:
            raw = reader()
        except Exception:
            return None
        if raw is None:
            return None
        try:
            return float(raw) * scale
        except Exception:
            return None

    def update_local_voltages(self):
        mc = self.motor_control
        if mc is not None:
            vt = vb = out_tr = out_br = None
            get_samples = getattr(mc, "get_last_samples", None)
            if callable(get_samples):
                try:
                    result = get_samples()
                    if isinstance(result, (tuple, list)) and len(result) >= 2:
                        vt, vb = result[0], result[1]
                    else:
                        vt = vb = None
                except Exception:
                    vt = vb = None
            if vt is None:
                vt = getattr(mc, "last_vt", None)
            if vb is None:
                vb = getattr(mc, "last_vb", None)

            get_outputs = getattr(mc, "get_last_outputs", None)
            if callable(get_outputs):
                try:
                    result = get_outputs()
                    if isinstance(result, (tuple, list)) and len(result) >= 2:
                        out_tr, out_br = result[0], result[1]
                    else:
                        out_tr = out_br = None
                except Exception:
                    out_tr = out_br = None
            if out_tr is None:
                out_tr = getattr(mc, "last_dac_throttle_v", None)
            if out_br is None:
                out_br = getattr(mc, "last_dac_brake_v", None)

            cfg = getattr(mc, "cfg", None)
            if isinstance(cfg, dict):
                vref = float(cfg.get("dac_vref", 3.3) or 3.3)
                cfg_for_calc = cfg
            else:
                vref = 3.3
                cfg_for_calc = MOTOR_DEFAULTS
            if out_tr is None:
                code_th = getattr(mc, "last_code_th", None)
                if code_th is not None:
                    try:
                        out_tr = (float(code_th) / 4095.0) * vref
                    except Exception:
                        out_tr = None
            if out_br is None:
                code_br = getattr(mc, "last_code_br", None)
                if code_br is not None:
                    try:
                        out_br = (float(code_br) / 4095.0) * vref
                    except Exception:
                        out_br = None

            if vt is not None and vb is not None and (out_tr is None or out_br is None):
                try:
                    calc_tr, calc_br = compute_output_voltages(vt, vb, cfg_for_calc)
                except Exception:
                    calc_tr = calc_br = None
                if out_tr is None and calc_tr is not None:
                    out_tr = calc_tr
                if out_br is None and calc_br is not None:
                    out_br = calc_br

            direct_vt = self._adc_direct_read(self.adc_throttle)
            direct_vb = self._adc_direct_read(self.adc_brake)
            if vt is None and direct_vt is not None:
                vt = direct_vt
            if vb is None and direct_vb is not None:
                vb = direct_vb

            for value, attr in ((vt, "throttle_v"), (vb, "brake_v"), (out_tr, "dac_throttle_v"), (out_br, "dac_brake_v")):
                if value is not None:
                    try:
                        setattr(self, attr, float(value))
                    except Exception:
                        pass
            return

        direct_vt = self._adc_direct_read(self.adc_throttle)
        direct_vb = self._adc_direct_read(self.adc_brake)
        if direct_vt is not None:
            self.throttle_v = direct_vt
        if direct_vb is not None:
            self.brake_v = direct_vb

        if direct_vt is not None and direct_vb is not None:
            try:
                out_tr, out_br = compute_output_voltages(direct_vt, direct_vb, MOTOR_DEFAULTS)
            except Exception:
                out_tr = out_br = None
            if out_tr is not None:
                self.dac_throttle_v = float(out_tr)
            if out_br is not None:
                self.dac_brake_v = float(out_br)

    def integrate(self):
        now_raw = ticks_ms()
        if now_raw is None:
            return
        try:
            now = int(now_raw)
        except Exception:
            return
        base_ms = self._last_int_ms
        if not isinstance(base_ms, int):
            self._last_int_ms = now
            return
        dt_ms = ticks_diff(now, base_ms)
        if dt_ms <= 0:
            return
        self._last_int_ms = now
        v = self.vehicle_speed()
        try:
            v_float = float(v)
        except Exception:
            v_float = 0.0
        self.km_total += v_float * (dt_ms / 3600000.0)
        p = self.get_pr("motor_input_power", (None, ""))[0]
        if p is None:
            bv = self.get_pr("battery_voltage", (None, ""))[0]
            bc = self.get_pr("battery_current", (None, ""))[0]
            if bv is None or bc is None:
                bv = self.get_pr("batt_voltage_calc", (None, ""))[0]
            if bv is not None and bc is not None:
                try:
                    p = float(bv) * float(bc)
                except Exception:
                    p = 0.0
            else:
                p = 0.0
        try:
            p_float = float(p)
        except Exception:
            p_float = 0.0
        self.wh_total += p_float * (dt_ms / 3600000.0)

    def battery_voltage(self):
        if self.battery_voltage_v:
            return float(self.battery_voltage_v)
        bv = self.get_pr("battery_voltage", (None, ""))[0]
        if bv is None:
            bv = self.get_pr("batt_voltage_calc", (None, ""))[0]
        try:
            value = float(bv)
        except Exception:
            value = 0.0
        self.battery_voltage_v = value
        return value

    def vehicle_speed(self):
        candidates = (
            getattr(self, "trip_speed_kmh", None),
            self.get_pr("vehicle_speed_PR", (None, ""))[0],
            self.get_pr("vehicle_speed", (None, ""))[0],
            getattr(self, "trip_speed_kmh", 0.0),
        )
        for value in candidates:
            if value is None:
                continue
            try:
                return float(value)
            except Exception:
                continue
        return 0.0

    def battery_percent(self, voltage=None):
        if voltage is None:
            voltage = self.battery_voltage()
        pack = self.battery_pack or bats.load_current_pack()
        return bats.compute_soc(pack, voltage)