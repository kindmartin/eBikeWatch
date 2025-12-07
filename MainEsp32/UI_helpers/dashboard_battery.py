"""Battery status dashboard (live metrics for active pack)."""

from time import ticks_diff, ticks_ms

import fonts

from .dashboard_base import DashboardBase
from .writer import Writer

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000

_HEADER_MARGIN = 8
_DEFAULT_TICK_MS = 250
_PADDING_X = 8
_ROW_GAP = 8


def _ticks_ms_int():
    value = ticks_ms()
    if value is None:
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _safe_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


class DashboardBattStatus(DashboardBase):
    """Render live battery voltage, current, power, and energy stats."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="THIS BATT", sep_color=0x07FF)
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        self.font_large = fonts.load("sevenSegment_40")
        self.font_medium = fonts.load("sevenSegment_24")
        self.font_small = fonts.load("sevenSegment_20")

        self.writer_large = Writer(framebuf, self.font_large, verbose=False)
        self.writer_medium = Writer(framebuf, self.font_medium, verbose=False)
        self.writer_small = Writer(framebuf, self.font_small, verbose=False)

        for writer in (self.writer_large, self.writer_medium, self.writer_small):
            writer.setcolor(FG_COLOR, BG_COLOR)
            writer.set_clip(col_clip=True, wrap=False)

        self._tick_ms = int(_DEFAULT_TICK_MS)
        self._last_tick = None
        self._last_values = None
        self._needs_full_refresh = True

    def request_full_refresh(self):
        super().request_full_refresh()
        self._needs_full_refresh = True
        self._last_tick = None
        self._last_values = None

    def draw(self, state):
        now = _ticks_ms_int()
        if self._last_tick is not None:
            try:
                elapsed = ticks_diff(now, self._last_tick)
            except Exception:
                elapsed = self._tick_ms
            if elapsed < self._tick_ms:
                return
        else:
            elapsed = self._tick_ms

        values = self._collect_values(state)
        if not self._needs_full_refresh and self._values_equal(values):
            self._last_tick = now
            return

        if self._needs_full_refresh:
            self.lcd.fill(BG_COLOR)
            self.ensure_header(force=True)
            self._needs_full_refresh = False
        else:
            self.ensure_header()

        self._draw_content(values)

        self.lcd.show()
        self._last_tick = now
        self._last_values = values

    def set_tick_interval(self, interval_ms):
        try:
            value = int(interval_ms)
        except Exception:
            return False
        if value < 50:
            value = 50
        self._tick_ms = value
        self._last_tick = None
        self._needs_full_refresh = True
        return True

    def get_tick_interval(self):
        return int(self._tick_ms)

    def _collect_values(self, state):
        pack = getattr(state, "battery_pack", {}) or {}
        pack_name = getattr(state, "battery_pack_name", "") or pack.get("key", "")

        voltage = getattr(state, "battery_voltage_v", None)
        if not voltage:
            voltage = state.battery_voltage()
        current = getattr(state, "battery_current_a", None)
        if current is None:
            current = state.get_pr("battery_current", (None, "A"))[0]
        power = getattr(state, "battery_power_w", None)
        if power is None:
            power = state.get_pr("motor_input_power", (None, "W"))[0]
        if power is None and voltage is not None and current is not None:
            power = _safe_float(voltage, 0.0) * _safe_float(current, 0.0)

        soc = state.battery_percent(voltage)
        remaining_wh = getattr(state, "battery_remaining_wh", 0.0)
        max_wh = getattr(state, "battery_max_wh", pack.get("pack_capacity_Wh", 0.0))
        guard_active = bool(getattr(state, "battery_guard_active", False))
        guard_applied = bool(getattr(state, "battery_guard_applied", False))
        guard_throttle = getattr(state, "battery_guard_throttle_v", 0.0)
        cells_series = getattr(state, "battery_cells_series", pack.get("cells_series", 0))
        parallel = getattr(state, "battery_parallel", pack.get("parallel", 1))
        cell_avg = getattr(state, "cell_avg_voltage", 0.0)

        return (
            str(pack_name)[:24],
            int(round(_safe_float(soc, 0.0))),
            round(_safe_float(voltage, 0.0), 2),
            round(_safe_float(current, 0.0), 2),
            round(_safe_float(power, 0.0), 1),
            round(_safe_float(remaining_wh, 0.0), 1),
            round(_safe_float(max_wh, 0.0), 1),
            guard_active,
            guard_applied,
            round(_safe_float(guard_throttle, 0.0), 2),
            int(cells_series or 0),
            int(parallel or 1),
            round(_safe_float(cell_avg, 0.0), 3),
        )

    def _values_equal(self, new_values):
        if self._last_values is None:
            return False
        return self._last_values == new_values

    def _draw_content(self, values):
        (
            pack_name,
            percent,
            voltage,
            current,
            power,
            remaining_wh,
            max_wh,
            guard_active,
            guard_applied,
            guard_throttle,
            cells_series,
            parallel,
            cell_avg,
        ) = values

        lcd = self.lcd
        width = lcd.width
        height = lcd.height

        content_top = self.header_height
        if content_top < height:
            lcd.fill_rect(0, content_top, width, height - content_top, BG_COLOR)

        pack_label = (pack_name or "PACK").upper()
        pack_y = content_top + 2
        self._draw_text(self.writer_small, self.font_small, pack_label, _PADDING_X, pack_y)
        cells_text = f"{cells_series}s x{parallel}"
        self._draw_text(
            self.writer_small,
            self.font_small,
            cells_text,
            width - self._text_width(self.font_small, cells_text) - _PADDING_X,
            pack_y,
        )

        percent_text = f"{max(0, min(percent, 100)):03d}%"
        percent_width = self._text_width(self.font_large, percent_text)
        percent_x = max(0, (width - percent_width) // 2)
        percent_y = pack_y + self.font_small.height() + (_HEADER_MARGIN // 2)
        self._draw_text(self.writer_large, self.font_large, percent_text, percent_x, percent_y)

        rows_y = percent_y + self.font_large.height() + (_ROW_GAP * 2)
        col_split = width // 2
        col_gap = 6

        left_rows = (
            ("V", f"{voltage:0.2f}V"),
            ("I", f"{current:0.2f}A"),
            ("P", f"{power:0.0f}W"),
        )

        right_rows = (
            ("Wh", f"{remaining_wh:0.1f}/{max_wh:0.1f}"),
            ("Cell", f"{cell_avg:0.3f}V"),
            ("Pack", f"{cells_series:02d}s x{parallel:02d}"),
        )

        for (l_label, l_value), (r_label, r_value) in zip(left_rows, right_rows):
            left_value_x = col_split - col_gap - self._text_width(self.font_medium, l_value)
            self._draw_text(self.writer_small, self.font_small, l_label, _PADDING_X, rows_y)
            self._draw_text(self.writer_medium, self.font_medium, l_value, left_value_x, rows_y)

            right_label_x = col_split + col_gap
            self._draw_text(self.writer_small, self.font_small, r_label, right_label_x, rows_y)
            right_value_x = width - self._text_width(self.font_medium, r_value) - _PADDING_X
            self._draw_text(self.writer_medium, self.font_medium, r_value, right_value_x, rows_y)

            rows_y += self.font_medium.height() + _ROW_GAP

        status_y = rows_y + _ROW_GAP
        if status_y + self.font_small.height() > height:
            status_y = height - self.font_small.height() - 2
        if guard_active:
            if guard_applied and guard_throttle:
                status_text = f"GUARD DAC {guard_throttle:0.2f}V"
            else:
                status_text = "GUARD ACTIVE"
        else:
            status_text = "GUARD OK"
        self._draw_text(
            self.writer_small,
            self.font_small,
            status_text,
            _PADDING_X,
            status_y,
        )

    def _draw_text(self, writer, font_mod, text, x, y):
        height = font_mod.height()
        width = self._text_width(font_mod, text)
        self.lcd.fill_rect(x, y, width + 4, height, BG_COLOR)
        Writer.set_textpos(self.lcd.framebuf, y, x)
        writer.printstring(text)

    @staticmethod
    def _text_width(font_mod, text):
        total = 0
        for ch in text:
            try:
                _, _, adv = font_mod.get_ch(ch)
            except Exception:
                adv = 0
            total += adv
        return total
