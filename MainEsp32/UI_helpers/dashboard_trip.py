"""Trip pulse dashboard (screen 3)."""

from time import ticks_diff, ticks_ms

import fonts
from .writer import Writer
from .dashboard_base import DashboardBase

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000
_TOP_MARGIN = 20
_VALUE_FONT = "sevenSegment_30"
_SMALL_FONT = "sevenSegment_20"
_BOTTOM_FONT = "sevenSegment_24"
_PULSE_TO_METER = 0.1  # metres per pulse (10 pulses -> 1 m)
_DEFAULT_TICK_MS = 200


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


class DashboardTrip(DashboardBase):
    """Display trip metrics maintained by the shared AppState."""

    def __init__(self, ui_display, *, pulse_to_meter=None, **_unused):
        super().__init__(ui_display, title="TRIP", sep_color=0xF81F)
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        self.font_value = fonts.load(_VALUE_FONT)
        self.font_small = fonts.load(_SMALL_FONT)
        self.font_bottom = fonts.load(_BOTTOM_FONT)
        self.writer_value = Writer(framebuf, self.font_value, verbose=False)
        self.writer_small = Writer(framebuf, self.font_small, verbose=False)
        self.writer_bottom = Writer(framebuf, self.font_bottom, verbose=False)

        for writer in (self.writer_value, self.writer_small, self.writer_bottom):
            writer.setcolor(FG_COLOR, BG_COLOR)
            writer.set_clip(col_clip=True, wrap=False)

        self._pulse_to_meter = float(pulse_to_meter if pulse_to_meter is not None else _PULSE_TO_METER)
        self._needs_full_refresh = True
        self._last_tick = None
        self._last_drawn = None
        self._tick_ms = int(_DEFAULT_TICK_MS)

    def request_full_refresh(self):
        super().request_full_refresh()
        self._needs_full_refresh = True
        self._last_drawn = None

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

        pulses = getattr(state, "trip_pulses", 0) or 0
        distance_km = getattr(state, "trip_distance_km", None)
        if distance_km is None:
            meters = getattr(state, "trip_distance_m", None)
            if meters is None:
                meters = pulses * self._pulse_to_meter
            distance_km = meters / 1000.0
        distance_km = round(_safe_float(distance_km, 0.0), 3)

        trip_speed = _safe_float(getattr(state, "trip_speed_kmh", None), 0.0)
        pr_raw = state.get_pr("vehicle_speed_PR", (None, ""))[0]
        if pr_raw is None:
            pr_raw = state.get_pr("vehicle_speed", (None, ""))[0]
        pr_speed = _safe_float(pr_raw, 0.0)

        trip_speed_disp = round(min(max(trip_speed, 0.0), 199.9), 1)
        pr_speed_disp = round(min(max(pr_speed, 0.0), 199.9), 1)

        available = bool(getattr(state, "trip_counter_available", False))
        error_msg = getattr(state, "trip_counter_error", "") or ""

        data = (
            pulses,
            distance_km,
            trip_speed_disp,
            pr_speed_disp,
            available,
            error_msg,
        )
        if not self._needs_full_refresh and self._last_drawn == data:
            self._last_tick = now
            return

        if self._needs_full_refresh:
            self.ensure_header(force=True)
        else:
            self.ensure_header()

        if available:
            self._draw_trip(pulses, distance_km, trip_speed_disp, pr_speed_disp)
        else:
            message = (error_msg.upper() if isinstance(error_msg, str) else "CNT ERR")[:10] if error_msg else "WAIT CNT"
            self._draw_status(message)

        self.lcd.show()
        self._last_tick = now
        self._last_drawn = data
        self._needs_full_refresh = False

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

    def _draw_trip(self, pulses, distance_km, trip_speed_kmh, pr_speed_kmh):
        lcd = self.lcd
        width = lcd.width
        height = lcd.height
        margin = min(_TOP_MARGIN, max(0, height // 16))
        base_y = self.header_height
        if base_y < height:
            lcd.fill_rect(0, base_y, width, height - base_y, BG_COLOR)
        top = base_y + margin
        usable_height = max(0, height - top)

        pulses_text = f"{pulses:07d}" if pulses < 1_000_000 else f"{pulses:d}"
        km_text = f"{distance_km:07.3f}km"

        value_height = self.font_value.height()
        spacing = max(6, value_height // 4)
        line1_y = top + spacing
        line2_y = line1_y + value_height + spacing

        self._draw_centered(pulses_text, line1_y)
        self._draw_centered(km_text, line2_y)
        self._draw_bottom_speeds(trip_speed_kmh, pr_speed_kmh)

    def _draw_status(self, message):
        lcd = self.lcd
        lcd.fill_rect(0, self.header_height, lcd.width, lcd.height - self.header_height, BG_COLOR)

        message_y = max(self.header_height + _TOP_MARGIN, (lcd.height - self.font_value.height()) // 2)
        self._draw_centered(message, message_y)

    def _draw_bottom_speeds(self, trip_speed_kmh, pr_speed_kmh):
        lcd = self.lcd
        font = self.font_bottom
        writer = self.writer_bottom
        label_font = self.font_small
        label_writer = self.writer_small

        label_gap = 2
        padding = 4
        label_height = label_font.height()
        value_height = font.height()
        area_height = label_height + value_height + (padding * 2) + label_gap
        if area_height > lcd.height:
            area_height = lcd.height
        area_y = max(self.header_height, lcd.height - area_height)
        lcd.fill_rect(0, area_y, lcd.width, area_height, BG_COLOR)

        half_width = lcd.width // 2
        right_width = lcd.width - half_width

        label_y = area_y + padding
        trip_label = "TRIP"
        pr_label = "PR"
        trip_label_width = self._text_width(label_font, trip_label)
        pr_label_width = self._text_width(label_font, pr_label)
        trip_label_x = max(0, (half_width - trip_label_width) // 2)
        pr_label_x = half_width + max(0, (right_width - pr_label_width) // 2)

        Writer.set_textpos(lcd.framebuf, label_y, trip_label_x)
        label_writer.printstring(trip_label)
        Writer.set_textpos(lcd.framebuf, label_y, pr_label_x)
        label_writer.printstring(pr_label)

        value_y = label_y + label_height + label_gap
        trip_text = f"{trip_speed_kmh:05.1f}"
        pr_text = f"{pr_speed_kmh:05.1f}"
        trip_width = self._text_width(font, trip_text)
        pr_width = self._text_width(font, pr_text)
        trip_x = max(0, (half_width - trip_width) // 2)
        pr_x = half_width + max(0, (right_width - pr_width) // 2)

        Writer.set_textpos(lcd.framebuf, value_y, trip_x)
        writer.printstring(trip_text)
        Writer.set_textpos(lcd.framebuf, value_y, pr_x)
        writer.printstring(pr_text)

    def _draw_centered(self, text, y):
        font = self.font_value
        writer = self.writer_value
        width = self._text_width(font, text)
        area_width = width + 6
        x = max(0, (self.lcd.width - area_width) // 2)
        self.lcd.fill_rect(x, y, area_width, font.height(), BG_COLOR)
        Writer.set_textpos(self.lcd.framebuf, y, x)
        writer.printstring(text)

    def _draw_centered_small(self, text, y):
        font = self.font_small
        writer = self.writer_small
        width = self._text_width(font, text)
        area_width = width + 6
        x = max(0, (self.lcd.width - area_width) // 2)
        self.lcd.fill_rect(x, y, area_width, font.height(), BG_COLOR)
        Writer.set_textpos(self.lcd.framebuf, y, x)
        writer.printstring(text)

    @staticmethod
    def _text_width(font_mod, text):
        width = 0
        for ch in text:
            try:
                _, _, adv = font_mod.get_ch(ch)
            except Exception:
                adv = 0
            width += adv
        return width