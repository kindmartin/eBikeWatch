"""Local ESP32 PMU dashboard (AXP192 telemetry)."""

from time import ticks_ms, ticks_diff

import fonts

from .dashboard_base import DashboardBase
from .writer import Writer

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000
_PADDING_X = 6
_ROW_GAP = 6
_DEFAULT_TICK_MS = 500


def _ticks_ms_int():
    value = ticks_ms()
    if value is None:
        return 0
    try:
        return int(value)
    except Exception:
        return 0


class DashboardSysBatt(DashboardBase):
    """Render AXP192 board power measurements."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="SYS BATT", sep_color=0xFFFF)
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        self.font_main = fonts.load("sevenSegment_24")
        self.font_small = fonts.load("sevenSegment_20")
        self.writer_main = Writer(framebuf, self.font_main, verbose=False)
        self.writer_small = Writer(framebuf, self.font_small, verbose=False)
        for writer in (self.writer_main, self.writer_small):
            writer.setcolor(FG_COLOR, BG_COLOR)
            writer.set_clip(col_clip=True, wrap=False)

        self._tick_ms = _DEFAULT_TICK_MS
        self._last_tick = None
        self._last_values = None
        self._needs_full_refresh = True

    def request_full_refresh(self):
        super().request_full_refresh()
        self._needs_full_refresh = True
        self._last_tick = None
        self._last_values = None

    def set_tick_interval(self, interval_ms):
        try:
            value = int(interval_ms)
        except Exception:
            return False
        if value < 200:
            value = 200
        self._tick_ms = value
        self._last_tick = None
        self._needs_full_refresh = True
        return True

    def get_tick_interval(self):
        return int(self._tick_ms)

    def draw(self, state):
        now = _ticks_ms_int()
        if self._last_tick is not None:
            try:
                elapsed = ticks_diff(now, self._last_tick)
            except Exception:
                elapsed = self._tick_ms
            if elapsed < self._tick_ms:
                return
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

    def _values_equal(self, new_values):
        if self._last_values is None:
            return False
        return self._last_values == new_values

    def _collect_values(self, state):
        available = bool(getattr(state, "sys_pmu_available", False))
        vbus_v = float(getattr(state, "sys_vbus_v", 0.0) or 0.0)
        vbus_i = float(getattr(state, "sys_vbus_ma", 0.0) or 0.0)
        vbat_v = float(getattr(state, "sys_vbat_v", 0.0) or 0.0)
        ichg = float(getattr(state, "sys_batt_charge_ma", 0.0) or 0.0)
        idis = float(getattr(state, "sys_batt_discharge_ma", 0.0) or 0.0)
        sys_i = float(getattr(state, "sys_board_current_ma", 0.0) or 0.0)
        source = getattr(state, "sys_board_source", "") or "N/A"
        flags = getattr(state, "sys_status_flags", "") or "IDLE"
        addr = getattr(state, "sys_pmu_addr", None)
        updated_ms = getattr(state, "sys_batt_last_update_ms", 0)
        age_s = None
        if updated_ms:
            try:
                age = ticks_diff(_ticks_ms_int(), int(updated_ms))
            except Exception:
                age = None
            if age is not None and age >= 0:
                age_s = age / 1000.0
        return (
            available,
            round(vbus_v, 2),
            round(vbus_i, 1),
            round(vbat_v, 2),
            round(ichg, 1),
            round(idis, 1),
            round(sys_i, 1),
            source,
            flags,
            addr,
            None if age_s is None else round(age_s, 1),
        )

    def _draw_content(self, values):
        (
            available,
            vbus_v,
            vbus_i,
            vbat_v,
            ichg,
            idis,
            sys_i,
            source,
            flags,
            addr,
            age_s,
        ) = values

        lcd = self.lcd
        width = lcd.width
        height = lcd.height
        content_top = self.header_height
        if content_top < height:
            lcd.fill_rect(0, content_top, width, height - content_top, BG_COLOR)

        y = content_top + 4
        if not available:
            self._draw_text(self.writer_main, self.font_main, "PMU OFFLINE", _PADDING_X, y + 20)
            return

        lines = [
            "VBUS {:>4.2f}V {:>5.0f}mA".format(vbus_v, vbus_i),
            "VBAT {:>4.2f}V".format(vbat_v),
            "CHG {:>5.1f} DIS {:>5.1f}".format(ichg, idis),
            "SRC {:>4} {:>5.1f}mA".format(source, sys_i),
            flags,
        ]
        tail = []
        if addr is not None:
            tail.append("PMU 0x{:02X}".format(int(addr) & 0xFF))
        if age_s is not None:
            tail.append("AGE {:>4.1f}s".format(age_s))
        if tail:
            lines.append(" ".join(tail))

        for text in lines:
            self._draw_text(self.writer_small, self.font_small, text, _PADDING_X, y)
            y += self.font_small.height() + _ROW_GAP

    def _draw_text(self, writer, font_mod, text, x, y):
        width = self._text_width(font_mod, text)
        height = font_mod.height()
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
