"""Dashboard rendering helpers for the ``t`` main screen."""

from time import ticks_diff, ticks_ms

import fonts

from .dashboard_base import DashboardBase
from .writer import Writer

_HEADER_FONT = "sevenSegment_20"
_SMALL_FONT = "sevenSegment_20"
_LARGE_FONT = "sevenSegment_80"

_EDGE_PADDING = 6
_SECTION_GAP_Y = 12
_SPRITE_GAP = 12
_BOTTOM_MARGIN = 10
_VALUE_GAP = 8
_SPEED_MAX_VALUE = 99
_POWER_MAX_VALUE = 4000
_F1_INTERVAL_MS = 1000
_F2_INTERVAL_MS = 500
_TOP_OFFSET = 6
_FG = 0xFFFF
_BG = 0x0000


def _text_extent(font_mod, text):
    width = 0
    for ch in text:
        try:
            _, _, advance = font_mod.get_ch(ch)
        except Exception:
            advance = 0
        width += advance
    return width


def _recolor_region(lcd, x, y, width, height):
    if width <= 0 or height <= 0:
        return
    pixel = lcd.pixel
    x_end = min(lcd.width, x + width)
    y_end = min(lcd.height, y + height)
    for py in range(max(0, y), y_end):
        for px in range(max(0, x), x_end):
            pixel(px, py, _FG if pixel(px, py) else _BG)


def _render_text_block(lcd, writer, font_mod, text, x, y, area_width, bg_color):
    if area_width <= 0 or y >= lcd.height:
        return 0
    height = font_mod.height()
    if y + height > lcd.height:
        height = lcd.height - y
    if height <= 0:
        return 0
    x = max(0, x)
    area_width = min(area_width, lcd.width - x)
    if area_width <= 0:
        return 0
    lcd.fill_rect(x, y, area_width, height, bg_color)
    Writer.set_textpos(lcd.framebuf, y, x)
    writer.printstring(text)
    text_width = min(_text_extent(font_mod, text), area_width)
    _recolor_region(lcd, x, y, text_width, height)
    return text_width


class DashboardLayout(DashboardBase):
    """Render the main ride dashboard with staggered refresh rates."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="MAIN", font_name=_HEADER_FONT, sep_color=0x001F)

        framebuf = self.lcd.framebuf

        self.font_small = fonts.load(_SMALL_FONT)
        self.font_large = fonts.load(_LARGE_FONT)
        self.font_bottom = self._header_font

        self.writer_large = Writer(framebuf, self.font_large, verbose=False)
        self.writer_small = Writer(framebuf, self.font_small, verbose=False)
        self.writer_header = self._header_writer
        self.writer_bottom = Writer(framebuf, self.font_bottom, verbose=False)

        for writer in (self.writer_large, self.writer_small, self.writer_header, self.writer_bottom):
            writer.setcolor(_FG, _BG)
            writer.set_clip(col_clip=True, wrap=False)

        self.speed_max_value = _SPEED_MAX_VALUE
        self.power_max_value = _POWER_MAX_VALUE
        self._unit_text = "kmh"
        self._power_unit_text = "watts"

        self.edge_padding = _EDGE_PADDING
        self.value_gap = _VALUE_GAP

        self.top_offset = self.header_height + _TOP_OFFSET
        self.speed_y = self.top_offset + _SECTION_GAP_Y
        self.speed_unit_y = self.speed_y + self.font_large.height() - self.font_small.height()
        self.power_y = self.speed_y + self.font_large.height() + _SECTION_GAP_Y
        self.power_unit_y = self.power_y + self.font_large.height() - self.font_small.height()

        icon_h = self.font_bottom.height()
        try:
            from pic.bat_chging import HEIGHT as ICON_HEIGHT, WIDTH as ICON_WIDTH, DATA as ICON_DATA
        except Exception:
            self.icon = None
        else:
            self.icon = (ICON_WIDTH, ICON_HEIGHT, bytearray(ICON_DATA))
            icon_h = max(ICON_HEIGHT, self.font_bottom.height())

        self.bottom_area_height = max(icon_h, self.font_bottom.height())
        min_bottom_y = self.power_y + self.font_large.height() + _SECTION_GAP_Y
        desired_bottom = self.lcd.height - self.bottom_area_height - _BOTTOM_MARGIN
        self.bottom_y = max(min_bottom_y, desired_bottom)
        self.bottom_text_y = self.bottom_y + (self.bottom_area_height - self.font_bottom.height()) // 2

        if self.icon:
            icon_w, icon_h, _ = self.icon
            self.icon_x = self.edge_padding
            self.icon_y = self.bottom_y + (self.bottom_area_height - icon_h) // 2
        else:
            self.icon_x = self.edge_padding
            self.icon_y = self.bottom_y

        self._last_f1 = None
        self._last_f2 = None
        self._needs_full_refresh = True

        self._last_time_text = None
        self._last_km_text = None
        self._last_speed_text = None
        self._last_power_text = None
        self._last_voltage_text = None
        self._last_percent_text = None

    def draw(self, state):
        now = ticks_ms()

        trigger_f1 = self._needs_full_refresh or self._is_due(self._last_f1, _F1_INTERVAL_MS, now)
        trigger_f2 = self._needs_full_refresh or self._is_due(self._last_f2, _F2_INTERVAL_MS, now)

        if not (trigger_f1 or trigger_f2):
            return

        if self._needs_full_refresh:
            self.lcd.fill(_BG)
            self.ensure_header(force=True)
            self._last_time_text = None
            self._last_km_text = None
            self._last_speed_text = None
            self._last_power_text = None
            self._last_voltage_text = None
            self._last_percent_text = None
            trigger_f1 = True
            trigger_f2 = True
            self._needs_full_refresh = False
        else:
            self.ensure_header()

        if trigger_f1:
            self._last_f1 = now
        if trigger_f2:
            self._last_f2 = now

        updated = False
        if trigger_f1:
            if self._update_bottom_line(state):
                updated = True
        if trigger_f2:
            if self._update_speed(state):
                updated = True
            if self._update_power(state):
                updated = True

        if updated:
            self.lcd.show()

    def request_full_refresh(self):
        super().request_full_refresh()
        self._needs_full_refresh = True

    @staticmethod
    def _is_due(last, interval, now):
        if last is None:
            return True
        return ticks_diff(now, last) >= interval

    def _update_speed(self, state):
        speed_getter = getattr(state, "vehicle_speed", None)
        if callable(speed_getter):
            try:
                speed_val = speed_getter()
            except Exception:
                speed_val = None
        else:
            speed_val = None
        if speed_val is None:
            speed_val = getattr(state, "trip_speed_kmh", None)
        if speed_val is None:
            speed_val = state.get_pr("vehicle_speed_PR", (0.0, ""))[0]
        if speed_val is None:
            speed_val = state.get_pr("vehicle_speed", (0.0, ""))[0]
        if speed_val is None:
            speed_val = 0.0
        speed_int = max(0, min(int(round(speed_val)), self.speed_max_value))
        speed_text = f"{speed_int:02d}"

        now_raw = ticks_ms()
        if isinstance(now_raw, int):
            now = now_raw
        else:
            try:
                now = int(now_raw or 0)
            except Exception:
                now = 0

        base_raw = getattr(state, "boot_ms", 0)
        if isinstance(base_raw, int):
            base = base_raw
        else:
            try:
                base = int(base_raw or 0)
            except Exception:
                base = 0

        elapsed = ticks_diff(now, base)
        if elapsed < 0:
            elapsed = 0
        total_minutes = elapsed // 60000
        hours = total_minutes // 60
        minutes = total_minutes % 60
        time_text = f"{hours:02d}:{minutes:02d}"

        trip_km = getattr(state, "trip_distance_km", None)
        if trip_km is None:
            trip_m = getattr(state, "trip_distance_m", 0.0) or 0.0
            trip_km = trip_m / 1000.0
        trip_int = int(round(trip_km))
        if trip_int < 0:
            trip_int = 0
        trip_text = f"{trip_int:02d}km"

        if (
            speed_text == self._last_speed_text
            and time_text == self._last_time_text
            and trip_text == self._last_km_text
        ):
            return False

        self._last_speed_text = speed_text
        self._last_time_text = time_text
        self._last_km_text = trip_text

        lcd = self.lcd
        height = self.font_large.height()
        lcd.fill_rect(0, self.speed_y, lcd.width, height, _BG)

        digits_width = _text_extent(self.font_large, speed_text)
        unit_width = _text_extent(self.font_small, self._unit_text)
        info_width = max(
            _text_extent(self.font_small, time_text),
            _text_extent(self.font_small, trip_text),
        ) + 4

        unit_x = max(self.edge_padding, lcd.width - unit_width - self.edge_padding)
        digits_x = unit_x - self.value_gap - digits_width

        min_digits_x = self.edge_padding + info_width + self.value_gap
        if digits_x < min_digits_x:
            digits_x = min_digits_x
            unit_x = digits_x + digits_width + self.value_gap
            if unit_x + unit_width > lcd.width - self.edge_padding:
                unit_x = max(self.edge_padding, lcd.width - unit_width - self.edge_padding)
                digits_x = unit_x - self.value_gap - digits_width
                if digits_x < min_digits_x:
                    digits_x = min_digits_x

        info_x = self.edge_padding
        gap_y = 9
        info_block_height = (self.font_small.height() * 2) + gap_y
        info_y = self.speed_y + max(0, (height - info_block_height) // 2)

        _render_text_block(lcd, self.writer_small, self.font_small, time_text, info_x, info_y, info_width, _BG)
        second_y = info_y + self.font_small.height() + gap_y
        _render_text_block(lcd, self.writer_small, self.font_small, trip_text, info_x, second_y, info_width, _BG)

        _render_text_block(lcd, self.writer_large, self.font_large, speed_text, digits_x, self.speed_y, digits_width + 4, _BG)
        _render_text_block(lcd, self.writer_small, self.font_small, self._unit_text, unit_x, self.speed_unit_y, unit_width + 4, _BG)
        return True

    def _update_power(self, state):
        vbat = state.get_pr("battery_voltage", (None, ""))[0]
        if vbat is None:
            vbat = state.get_pr("batt_voltage_calc", (0.0, ""))[0]
        vbat = float(vbat) if vbat is not None else 0.0
        bc = state.get_pr("battery_current", (0.0, ""))[0]
        bc = float(bc) if bc is not None else 0.0
        power = state.get_pr("motor_input_power", (None, ""))[0]
        if power is None:
            power = vbat * bc
        try:
            power_val = float(power)
        except Exception:
            power_val = 0.0
        power_int = int(round(power_val))
        clamp = self.power_max_value
        if power_int > clamp:
            power_int = clamp
        if power_int < -clamp:
            power_int = -clamp
        power_text = str(power_int)

        updated = False
        if power_text != self._last_power_text:
            self._last_power_text = power_text

            lcd = self.lcd
            height = self.font_large.height()
            lcd.fill_rect(0, self.power_y, lcd.width, height, _BG)

            digits_width = _text_extent(self.font_large, power_text)
            unit_width = _text_extent(self.font_small, self._power_unit_text)
            unit_x = max(self.edge_padding, lcd.width - unit_width - self.edge_padding)
            digits_x = unit_x - self.value_gap - digits_width
            if digits_x < self.edge_padding:
                digits_x = self.edge_padding
                unit_x = digits_x + digits_width + self.value_gap

            _render_text_block(lcd, self.writer_large, self.font_large, power_text, digits_x, self.power_y, digits_width + 4, _BG)
            _render_text_block(lcd, self.writer_small, self.font_small, self._power_unit_text, unit_x, self.power_unit_y, unit_width + 4, _BG)
            updated = True

        return updated

    def _update_bottom_line(self, state):
        voltage = state.battery_voltage()
        soc = state.battery_percent(voltage)
        voltage_text = f"{voltage:5.1f}V"
        percent = int(round(soc))
        if percent < 0:
            percent = 0
        elif percent > 100:
            percent = 100
        percent_text = f"{percent}%"

        if voltage_text == self._last_voltage_text and percent_text == self._last_percent_text:
            return False

        self._last_voltage_text = voltage_text
        self._last_percent_text = percent_text

        lcd = self.lcd
        area_height = lcd.height - self.bottom_y
        lcd.fill_rect(0, self.bottom_y, lcd.width, area_height, _BG)

        text_start_x = self.edge_padding
        if self.icon:
            icon_w, icon_h, icon_data = self.icon
            lcd.blit_buffer(icon_data, self.icon_x, self.icon_y, icon_w, icon_h)
            text_start_x = self.icon_x + icon_w + _SPRITE_GAP

        volt_width = _text_extent(self.font_bottom, voltage_text)
        percent_width = _text_extent(self.font_bottom, percent_text)
        volt_x = text_start_x
        percent_x = max(self.edge_padding, lcd.width - percent_width - self.edge_padding)
        if percent_x <= volt_x + volt_width + 6:
            percent_x = volt_x + volt_width + 6
            if percent_x + percent_width > lcd.width:
                percent_x = max(self.edge_padding, lcd.width - percent_width - self.edge_padding)

        _render_text_block(lcd, self.writer_bottom, self.font_bottom, voltage_text, volt_x, self.bottom_text_y, volt_width + 4, _BG)
        _render_text_block(lcd, self.writer_bottom, self.font_bottom, percent_text, percent_x, self.bottom_text_y, percent_width + 4, _BG)
        return True

