"""Signals dashboard rendering (screen 2)."""

from time import ticks_diff, ticks_ms

import fonts
from .writer import Writer

from .dashboard_base import DashboardBase
from .line_meter import HorizontalSegmentMeter

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000
_VALUE_TEMPLATE = "88.88"

_FONT_NAME_LABEL = "sevenSegment_20"
_FONT_NAME_VALUE = "sevenSegment_40"
_FONT_NAME_UNIT = "sevenSegment_20"

_EDGE_PADDING = 10
_ROW_GAP = 8
_SECTION_GAP = 18
_METER_LENGTH = 160
_METER_HEIGHT = 5
_DEFAULT_TICK_MS = 320

_LABELS = (
    ("ADC TR", "V"),
    ("ADC BR", "V"),
    ("OUT TR", "V"),
    ("OUT BR", "V"),
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
            unit_x = self._value_x - self._unit_area_width - 6
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
        self._draw_rows(values)
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

    def _draw_rows(self, values):
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
