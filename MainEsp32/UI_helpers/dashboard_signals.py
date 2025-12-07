"""Signals dashboard rendering (screen 2)."""

from time import ticks_diff, ticks_ms

import fonts
from .writer import Writer

from .dashboard_base import DashboardBase
from .line_meter import HorizontalSegmentMeter

try:
    from motor_control import DEFAULTS as MOTOR_DEFAULTS
except Exception:  # pragma: no cover - optional dependency during host tooling
    MOTOR_DEFAULTS = {}

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000
_VALUE_TEMPLATE = "88.88"

_FONT_NAME_LABEL = "sevenSegment_20"
_FONT_NAME_VALUE = "sevenSegment_40"
_FONT_NAME_UNIT = "sevenSegment_20"

_EDGE_PADDING = 10
_ROW_GAP = 3
_SECTION_GAP = 18
_METER_LENGTH = 160
_METER_HEIGHT = 5
_DEFAULT_TICK_MS = 320

_LABELS = (
    ("ADC TR", "Volts"),
    ("ADC BR", "Volts"),
    ("OUT TR", "Volts"),
    ("OUT BR", "Volts"),
)


class DashboardSignals(DashboardBase):
    """Render ADC and output throttle/brake signals."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="SIGNALS", sep_color=0xFFE0)
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        self.font_label = fonts.load(_FONT_NAME_LABEL)
        self.font_value = fonts.load(_FONT_NAME_VALUE)
        self.font_unit = fonts.load(_FONT_NAME_UNIT)

        self.writer_label = Writer(framebuf, self.font_label, verbose=False)
        self.writer_value = Writer(framebuf, self.font_value, verbose=False)
        self.writer_unit = Writer(framebuf, self.font_unit, verbose=False)

        for writer in (self.writer_label, self.writer_value, self.writer_unit):
            writer.setcolor(FG_COLOR, BG_COLOR)
            writer.set_clip(col_clip=True, wrap=False)

        self.meter_throttle = HorizontalSegmentMeter(
            self.lcd,
            length=_METER_LENGTH,
            height=_METER_HEIGHT,
            bg_color=BG_COLOR,
            tick_color=FG_COLOR,
            neutral_color=FG_COLOR,
            segments=((0.0, 1.0, FG_COLOR),),
        )

        self._last_values = None
        self._last_tick = None
        self._last_draw_ms = 0
        self._last_frame_interval_ms = 0
        self._needs_full_refresh = True
        self._meter_x = max(_EDGE_PADDING, (self.lcd.width - _METER_LENGTH) // 2)
        self._row_height = self.font_value.height()
        self._tick_ms = int(_DEFAULT_TICK_MS)
        self._debug_timing = False
        self._debug_threshold_ms = 60
        self._last_debug_stamp = 0

        self._label_width = max(self._text_width(self.font_label, label) for label, _ in _LABELS)
        self._label_area_width = self._label_width + 4
        self._value_width = self._text_width(self.font_value, _VALUE_TEMPLATE)
        self._value_area_width = self._value_width + 4
        self._unit_width = max((self._text_width(self.font_unit, unit) for _, unit in _LABELS if unit), default=0)
        self._unit_area_width = self._unit_width + 4 if self._unit_width else 0
        self._label_x = _EDGE_PADDING
        self._value_x = self.lcd.width - _EDGE_PADDING - self._value_area_width
        if self._unit_area_width:
            unit_x = self._value_x - self._unit_area_width - 12
            min_unit_x = self._label_x + self._label_area_width + 6
            if unit_x < min_unit_x:
                unit_x = min_unit_x
            if unit_x + self._unit_area_width > self._value_x - 2:
                unit_x = max(min_unit_x, self._value_x - self._unit_area_width - 2)
            self._unit_x = unit_x
        else:
            self._unit_x = None
        self._unit_y_offset = self.font_value.height() - self.font_unit.height()

    def request_full_refresh(self):
        super().request_full_refresh()
        self._last_tick = None
        self._last_values = None
        self._needs_full_refresh = True

    def draw(self, state):
        now = _ticks_ms_int()
        elapsed = 0
        if self._last_tick is not None:
            try:
                elapsed = ticks_diff(now, self._last_tick)
            except Exception:
                elapsed = self._tick_ms
            if elapsed < self._tick_ms:
                return
        values = self._collect_values(state)
        if not self._needs_full_refresh and not self._values_changed(values):
            if elapsed <= 0:
                elapsed = self._tick_ms
            self._last_frame_interval_ms = elapsed
            return

        start = _ticks_ms_int()
        if self._needs_full_refresh:
            self.lcd.fill(BG_COLOR)
            self.ensure_header(force=True)
            self._needs_full_refresh = False
        else:
            self.ensure_header()
        self._draw_rows(state, values)
        self.lcd.show()
        end = _ticks_ms_int()
        try:
            self._last_draw_ms = ticks_diff(end, start)
        except Exception:
            self._last_draw_ms = 0
        if elapsed <= 0:
            elapsed = self._tick_ms
        self._last_tick = now
        self._last_frame_interval_ms = elapsed
        self._last_values = values
        if self._debug_timing and self._last_draw_ms >= self._debug_threshold_ms:
            stamp = _ticks_ms_int()
            try:
                delta_dbg = ticks_diff(stamp, self._last_debug_stamp)
            except Exception:
                delta_dbg = self._debug_threshold_ms
            if delta_dbg >= self._debug_threshold_ms:
                print(
                    "[Signals] draw={:.0f}ms interval={:.0f}ms refresh={}".format(
                        self._last_draw_ms,
                        self._last_frame_interval_ms,
                        self._needs_full_refresh,
                    )
                )
                self._last_debug_stamp = stamp

    def set_tick_interval(self, interval_ms):
        try:
            value = int(interval_ms)
        except Exception:
            return False
        if value < 20:
            value = 20
        self._tick_ms = value
        self._last_tick = None
        self._needs_full_refresh = True
        return True

    def get_tick_interval(self):
        return int(self._tick_ms)

    def set_debug_timing(self, enabled=True, threshold_ms=None):
        self._debug_timing = bool(enabled)
        if threshold_ms is not None:
            try:
                value = int(threshold_ms)
            except Exception:
                value = None
            if value is not None and value > 0:
                self._debug_threshold_ms = value
        if not self._debug_timing:
            self._last_debug_stamp = 0
        return self._debug_timing

    def handle_event(self, event, state, **kwargs):
        if event != "page_extra":
            return False
        total = getattr(state, "total_dashboards", 0)
        try:
            total = int(total)
        except Exception:
            total = 0
        if total <= 0:
            total = self._screen_index + 1
        next_idx = self._screen_index + 1
        if total > 0:
            next_idx %= total
        else:
            next_idx = 0
        return {"handled": True, "switch_screen": next_idx}

    def _draw_rows(self, state, values):
        y = self.header_height + _EDGE_PADDING
        width = self.lcd.width

        for idx, (label, unit) in enumerate(_LABELS):
            value = values[idx]
            y = self._draw_row(width, y, label, value, unit)
            gap_mid = y + (_ROW_GAP // 2)

            if idx == 0:
                meter_y = max(self.header_height + _EDGE_PADDING, gap_mid - (_METER_HEIGHT // 2))
                self.meter_throttle.draw(
                    self._meter_x,
                    meter_y,
                    values[0],
                    min_value=0.0,
                    max_value=3.3,
                    neutral_range=(0.8, 1.2),
                )

            y += _ROW_GAP

        self._draw_mode_footer(state, y)

    def _draw_mode_footer(self, state, used_height):
        footer_lines = self._mode_footer_lines(state)
        if not footer_lines:
            return

        line1, line2_left, line2_right = footer_lines
        line_height = self.font_label.height()
        spacing = 2
        num_lines = 1 + (1 if line2_left and line2_right else 0)
        total_height = (line_height * num_lines) + (spacing if num_lines > 1 else 0)
        footer_top = used_height + max(_ROW_GAP, 4)
        lcd = self.lcd
        max_top = lcd.height - total_height - 1
        if footer_top > max_top:
            footer_top = max_top
        if footer_top < self.header_height:
            footer_top = self.header_height
        if footer_top >= lcd.height:
            return
        lcd.fill_rect(0, footer_top, lcd.width, lcd.height - footer_top, BG_COLOR)

        self._draw_footer_text(line1, footer_top, align="left")
        if num_lines > 1:
            line2_y = footer_top + line_height + spacing
            self._draw_footer_dual(line2_left, line2_right, line2_y)

    def _draw_footer_text(self, text, y, *, align="left"):
        if not text:
            return
        width = self._text_width(self.font_label, text)
        if align == "right":
            x = max(_EDGE_PADDING, self.lcd.width - width - _EDGE_PADDING)
        else:
            x = _EDGE_PADDING
        self.lcd.fill_rect(x, y, min(width + 4, self.lcd.width - x), self.font_label.height(), BG_COLOR)
        Writer.set_textpos(self.lcd.framebuf, y, x)
        self.writer_label.printstring(text)

    def _draw_footer_dual(self, left_text, right_text, y):
        if not left_text and not right_text:
            return
        height = self.font_label.height()
        lcd = self.lcd
        lcd.fill_rect(0, y, lcd.width, height, BG_COLOR)
        if left_text:
            Writer.set_textpos(lcd.framebuf, y, _EDGE_PADDING)
            self.writer_label.printstring(left_text)
        if right_text:
            width = self._text_width(self.font_label, right_text)
            x = max(_EDGE_PADDING, lcd.width - width - _EDGE_PADDING)
            Writer.set_textpos(lcd.framebuf, y, x)
            self.writer_label.printstring(right_text)

    def _mode_footer_lines(self, state):
        details = self._mode_metric_details(state)
        if not details:
            return None
        ratio = details.get("ratio")
        if ratio is None:
            ratio = 0.0
        try:
            ratio_pct = float(ratio) * 100.0
        except Exception:
            ratio_pct = 0.0
        ratio_pct = min(max(ratio_pct, 0.0), 100.0)
        label = str(details.get("label") or "MODE").upper()
        line1 = f"{label} {ratio_pct:>4.0f}%"

        cur_val, tgt_val = self._footer_numeric_values(details)
        if cur_val is None and tgt_val is None:
            return (line1, None, None)
        return (
            line1,
            f"CUR {self._format_gauge_value(cur_val)}",
            f"TGT {self._format_gauge_value(tgt_val)}",
        )

    def _footer_numeric_values(self, details):
        mode_key = details.get("mode_key", "direct")
        actual = details.get("actual")
        target = details.get("target")
        if mode_key == "direct":
            actual_pct = self._percent_from_voltage(
                actual,
                details.get("dac_min"),
                details.get("dac_max"),
            )
            target_pct = self._clamp_percent(details.get("ratio"))
            return actual_pct, target_pct
        actual_val = self._safe_float(actual)
        target_val = self._safe_float(target)
        return actual_val, target_val

    def _format_gauge_value(self, value):
        if value is None:
            return "----"
        try:
            val = int(round(float(value)))
        except Exception:
            return "----"
        if val > 9999:
            val = 9999
        if val < -999:
            val = -999
        return f"{val:>4}"

    @staticmethod
    def _percent_from_voltage(value, v_min, v_max):
        try:
            val = float(value)
            vmin = float(v_min)
            vmax = float(v_max)
        except Exception:
            return None
        if vmax <= vmin:
            return None
        pct = (val - vmin) / (vmax - vmin) * 100.0
        if pct < 0.0:
            pct = 0.0
        if pct > 100.0:
            pct = 100.0
        return pct

    def _clamp_percent(self, ratio):
        value = self._safe_float(ratio)
        if value is None:
            return None
        pct = value * 100.0
        if pct < 0.0:
            pct = 0.0
        if pct > 100.0:
            pct = 100.0
        return pct

    def _mode_metric_details(self, state):
        if state is None:
            return None
        mode = getattr(state, "throttle_mode_active", "direct") or "direct"
        try:
            mode_lower = str(mode).strip().lower()
        except Exception:
            mode_lower = "direct"
        raw_ratio = self._safe_float(getattr(state, "throttle_ratio_raw", None))
        if raw_ratio is None:
            raw_ratio = 0.0
        raw_ratio = max(0.0, min(raw_ratio, 1.0))

        mc = getattr(state, "motor_control", None)
        mix_speed = bool(getattr(mc, "_mix_use_speed", False)) if mc else False

        def _pack(label, units, target, actual, extra=None):
            payload = {
                "label": label,
                "units": units,
                "target": target,
                "actual": actual,
                "mode_key": mode_lower,
                "ratio": raw_ratio,
            }
            if extra:
                payload.update(extra)
            return payload

        if mode_lower == "power":
            max_value = self._safe_float(self._get_cfg_value(state, "throttle_power_max_w", 0.0))
            actual = self._safe_float(self._get_pr_value(state, "motor_input_power"))
            if actual is None:
                actual = self._safe_float(getattr(state, "battery_power_w", None))
            target = self._compute_target(raw_ratio, max_value)
            return _pack("Power", "W", target, actual)

        if mode_lower == "speed" or (mode_lower == "mix" and mix_speed):
            max_value = self._safe_float(self._get_cfg_value(state, "throttle_speed_max_kmh", 0.0))
            actual = self._safe_float(self._safe_vehicle_speed(state))
            target = self._compute_target(raw_ratio, max_value)
            return _pack("Speed", "km/h", target, actual)

        if mode_lower == "torque" or (mode_lower == "mix" and not mix_speed):
            power = self._safe_float(self._get_pr_value(state, "motor_input_power"))
            if power is None:
                power = self._safe_float(getattr(state, "battery_power_w", None))
            speed = self._safe_float(self._safe_vehicle_speed(state))
            torque = self._compute_torque(power, speed)
            max_power = self._safe_float(self._get_cfg_value(state, "throttle_power_max_w", 0.0))
            max_speed = self._safe_float(self._get_cfg_value(state, "throttle_speed_max_kmh", 0.0))
            ref_speed = self._safe_float(self._get_cfg_value(state, "throttle_torque_ref_speed_kmh", 10.0))
            speed_candidates = [v for v in (max_speed, ref_speed) if v is not None]
            speed_for_max = max(speed_candidates) if speed_candidates else 0.0
            torque_max = self._compute_torque(max_power, speed_for_max)
            target = self._compute_target(raw_ratio, torque_max)
            return _pack("Torque", "Nm", target, torque)

        # Default/direct mode: show DAC output vs target voltage
        dac_max = self._safe_float(self._get_cfg_value(state, "throttle_output_max", 3.3))
        dac_min = self._safe_float(self._get_cfg_value(state, "throttle_output_min", 1.4))
        actual = self._safe_float(getattr(state, "dac_throttle_v", None))
        span = None if dac_max is None or dac_min is None else max(0.0, dac_max - dac_min)
        target = None
        if span is not None:
            target = dac_min + raw_ratio * span
        return _pack("Direct", "V", target, actual, {"dac_min": dac_min, "dac_max": dac_max})

    def _get_cfg_value(self, state, key, default=None):
        mc = getattr(state, "motor_control", None)
        if mc is not None:
            cfg = getattr(mc, "cfg", None)
            if isinstance(cfg, dict) and key in cfg and cfg.get(key) is not None:
                return cfg.get(key)
        if key in MOTOR_DEFAULTS:
            return MOTOR_DEFAULTS.get(key)
        return default

    @staticmethod
    def _get_pr_value(state, name):
        getter = getattr(state, "get_pr", None)
        if not callable(getter):
            return None
        value, _unit = getter(name, (None, ""))
        return value

    def _safe_vehicle_speed(self, state):
        speed_getter = getattr(state, "vehicle_speed", None)
        if callable(speed_getter):
            try:
                return speed_getter()
            except Exception:
                pass
        return getattr(state, "trip_speed_kmh", None)

    @staticmethod
    def _compute_target(ratio, max_value):
        if max_value is None:
            return None
        try:
            mv = float(max_value)
        except Exception:
            return None
        return max(0.0, ratio) * mv

    @staticmethod
    def _compute_torque(power_w, speed_kmh):
        if power_w is None or speed_kmh is None:
            return None
        try:
            power = float(power_w)
            speed = float(speed_kmh)
        except Exception:
            return None
        speed_mps = max(speed / 3.6, 0.3)
        return power / speed_mps

    def _format_metric_value(self, value, units):
        if value is None:
            return "--"
        try:
            val = float(value)
        except Exception:
            return "--"
        if units == "W":
            fmt = "{:.0f}"
        elif units == "km/h":
            fmt = "{:.1f}" if abs(val) < 100 else "{:.0f}"
        elif units == "Nm":
            fmt = "{:.1f}" if abs(val) < 100 else "{:.0f}"
        else:
            fmt = "{:.2f}" if abs(val) < 10 else "{:.1f}"
        return fmt.format(val) + (units if units else "")

    @staticmethod
    def _format_metric_int(value):
        if value is None:
            return "--"
        try:
            return str(int(round(float(value))))
        except Exception:
            return "--"

    @staticmethod
    def _safe_float(value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _draw_row(self, width, y, label, value, unit):
        lcd = self.lcd
        lcd.fill_rect(self._label_x, y, min(self._label_area_width, width - self._label_x), self._row_height, BG_COLOR)
        Writer.set_textpos(lcd.framebuf, y, self._label_x)
        self.writer_label.printstring(label)

        value_text = self._format_value(value)
        value_width = self._text_width(self.font_value, value_text)
        area_width = min(self._value_area_width, width - self._value_x)
        lcd.fill_rect(self._value_x, y, area_width, self._row_height, BG_COLOR)
        value_x = self._value_x + area_width - value_width
        if value_x < self._value_x:
            value_x = self._value_x
        Writer.set_textpos(lcd.framebuf, y, value_x)
        self.writer_value.printstring(value_text)

        if unit and self._unit_x is not None:
            space = max(0, self._value_x - self._unit_x - 2)
            unit_area_width = min(self._unit_area_width, space, width - self._unit_x)
            if unit_area_width > 0:
                lcd.fill_rect(self._unit_x, y, unit_area_width, self._row_height, BG_COLOR)
                Writer.set_textpos(
                    lcd.framebuf,
                    y + self._unit_y_offset,
                    self._unit_x,
                )
                self.writer_unit.printstring(unit)

        return y + self._row_height

    def _text_width(self, font_mod, text):
        width = 0
        for ch in text:
            _, _, adv = font_mod.get_ch(ch)
            width += adv
        return width

    def _format_value(self, value):
        if value is None:
            return "--"
        try:
            return f"{float(value):4.2f}"
        except Exception:
            return "--"

    def _collect_values(self, state):
        try:
            state.update_local_voltages()
        except Exception:
            pass

        adc_tr = getattr(state, "throttle_v", None)
        adc_br = getattr(state, "brake_v", None)

        if adc_tr is None:
            adc_tr = state.get_pr("throttle_voltage", (None, "V"))[0]
        if adc_br is None:
            adc_br = state.get_pr("brake_voltage_1", (None, "V"))[0]

        out_tr = getattr(state, "dac_throttle_v", None)
        out_br = getattr(state, "dac_brake_v", None)

        return (adc_tr, adc_br, out_tr, out_br)

    def _values_changed(self, values):
        previous = self._last_values
        if previous is None:
            return True
        for before, after in zip(previous, values):
            if not self._nearly_equal(before, after):
                return True
        return False

    @staticmethod
    def _nearly_equal(a, b, eps=0.005):
        if a is None or b is None:
            return (a is None) != (b is None)
        try:
            return abs(float(a) - float(b)) <= eps
        except Exception:
            return True

    @property
    def last_draw_ms(self):
        return self._last_draw_ms

    @property
    def last_frame_interval_ms(self):
        return self._last_frame_interval_ms


def _ticks_ms_int():
    value = ticks_ms()
    if value is None:
        return 0
    try:
        return int(value)
    except Exception:
        return 0
