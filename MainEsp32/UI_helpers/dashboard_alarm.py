"""Alarm telemetry dashboard for anti-theft mode."""

from time import ticks_ms, ticks_diff

import fonts

from .dashboard_base import DashboardBase
from .writer import Writer

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000
STATUS_ACTIVE = 0xFBE0
STATUS_IDLE = 0x07E0
STATUS_STALE = 0xF800
_CONTENT_X = 4
_ROW_GAP = 4
_MAX_WIFI = 3
_DEFAULT_TICK_MS = 500


def _ticks_ms_int():
    value = ticks_ms()
    if value is None:
        return 0
    try:
        return int(value)
    except Exception:
        return 0


class DashboardAlarm(DashboardBase):
    """Render alarm telemetry (GNSS, cell, Wi-Fi) for anti-theft mode."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="ALARM", sep_color=STATUS_ACTIVE)
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        self.font_main = fonts.load("sevenSegment_20")
        self.font_small = fonts.load("sevenSegment_16")
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
        active = bool(getattr(state, "alarm_active", False))
        mode = (getattr(state, "alarm_mode", "idle") or "idle").upper()
        last_ms = getattr(state, "alarm_last_update_ms", 0) or 0
        age_s = None
        if last_ms:
            now = _ticks_ms_int()
            try:
                age = ticks_diff(now, int(last_ms))
            except Exception:
                age = None
            if age is not None and age >= 0:
                age_s = age / 1000.0
        signal_csq = getattr(state, "alarm_signal_csq", None)
        signal_rssi = getattr(state, "alarm_signal_rssi_dbm", None)
        operator = getattr(state, "alarm_operator", "") or "N/A"
        cell_info = getattr(state, "alarm_cell_info", "") or ""
        registration = getattr(state, "alarm_registration", "") or ""
        gnss_fix = bool(getattr(state, "alarm_gnss_fix", False))
        gnss_lat = getattr(state, "alarm_gnss_lat", None)
        gnss_lon = getattr(state, "alarm_gnss_lon", None)
        gnss_alt = getattr(state, "alarm_gnss_alt", None)
        gnss_sats = getattr(state, "alarm_gnss_sats", 0)
        gnss_speed = getattr(state, "alarm_gnss_speed", None)
        wifi_entries = getattr(state, "alarm_wifi_list", None) or []
        wifi_compiled = []
        for item in wifi_entries:
            if isinstance(item, dict):
                wifi_compiled.append(
                    (
                        item.get("ssid") or "?",
                        item.get("bssid") or "--",
                        item.get("rssi"),
                    )
                )
            elif isinstance(item, (tuple, list)) and item:
                ssid = item[0] if len(item) > 0 else "?"
                bssid = item[1] if len(item) > 1 else "--"
                rssi = item[2] if len(item) > 2 else None
                wifi_compiled.append((ssid, bssid, rssi))
            if len(wifi_compiled) >= _MAX_WIFI:
                break
        while len(wifi_compiled) < _MAX_WIFI:
            wifi_compiled.append(("SSID?", "--", None))
        return (
            active,
            mode,
            None if age_s is None else round(age_s, 1),
            gnss_fix,
            gnss_lat,
            gnss_lon,
            gnss_alt,
            gnss_sats,
            gnss_speed,
            operator,
            cell_info,
            registration,
            signal_rssi,
            signal_csq,
            tuple(wifi_compiled),
        )

    def _draw_content(self, values):
        (
            active,
            mode,
            age_s,
            gnss_fix,
            gnss_lat,
            gnss_lon,
            gnss_alt,
            gnss_sats,
            gnss_speed,
            operator,
            cell_info,
            registration,
            signal_rssi,
            signal_csq,
            wifi_list,
        ) = values

        lcd = self.lcd
        width = lcd.width
        height = lcd.height
        content_top = self.header_height
        if content_top < height:
            lcd.fill_rect(0, content_top, width, height - content_top, BG_COLOR)

        y = content_top + 2
        status_color = STATUS_ACTIVE if active else STATUS_IDLE
        mode_text = "{} {}".format("ACTIVE" if active else "IDLE", mode)
        if age_s is not None and age_s > 10:
            status_color = STATUS_STALE
        self._draw_status_bar(mode_text, age_s, status_color, y)
        y += self.font_main.height() + _ROW_GAP + 2

        gps_lines = self._format_gps_lines(gnss_fix, gnss_lat, gnss_lon, gnss_alt, gnss_sats, gnss_speed)
        for text in gps_lines:
            self._draw_text(self.writer_small, self.font_small, text, y)
            y += self.font_small.height() + _ROW_GAP

        cell_lines = self._format_cell_lines(operator, cell_info, registration, signal_rssi, signal_csq)
        for text in cell_lines:
            self._draw_text(self.writer_small, self.font_small, text, y)
            y += self.font_small.height() + _ROW_GAP

        wifi_header = "Wi-Fi (top {}):".format(_MAX_WIFI)
        self._draw_text(self.writer_small, self.font_small, wifi_header, y)
        y += self.font_small.height() + _ROW_GAP
        for idx, (ssid, bssid, rssi) in enumerate(wifi_list, start=1):
            label = "{}.{:<15} {:>5}".format(idx, self._trim(ssid, 12), self._format_rssi(rssi))
            tail = bssid or "--"
            self._draw_text(self.writer_small, self.font_small, label, y)
            y += self.font_small.height()
            self._draw_text(self.writer_small, self.font_small, "    {}".format(tail), y)
            y += self.font_small.height() + _ROW_GAP
            if y >= height - self.font_small.height():
                break

    def _draw_status_bar(self, text, age_s, color, y):
        lcd = self.lcd
        height = self.font_main.height()
        lcd.fill_rect(0, y, lcd.width, height + 2, BG_COLOR)
        if age_s is None:
            age_txt = "AGE ?"
        else:
            age_txt = "AGE {:>4.1f}s".format(age_s)
        line = "{}  {}".format(text, age_txt)
        Writer.set_textpos(lcd.framebuf, y, _CONTENT_X)
        self.writer_main.setcolor(color, BG_COLOR)
        self.writer_main.printstring(line)
        self.writer_main.setcolor(FG_COLOR, BG_COLOR)

    def _draw_text(self, writer, font_mod, text, y):
        lcd = self.lcd
        height = font_mod.height()
        lcd.fill_rect(0, y, lcd.width, height, BG_COLOR)
        Writer.set_textpos(lcd.framebuf, y, _CONTENT_X)
        writer.printstring(text)

    @staticmethod
    def _trim(text, max_len):
        if text is None:
            return "?"
        try:
            string = str(text)
        except Exception:
            string = "?"
        if len(string) <= max_len:
            return string
        return string[: max_len - 1] + "…"

    @staticmethod
    def _format_rssi(value):
        if value is None:
            return "N/A"
        try:
            return "{:+d}dBm".format(int(value))
        except Exception:
            return "N/A"

    @staticmethod
    def _format_gps_lines(fix, lat, lon, alt, sats, speed):
        if not fix or lat is None or lon is None:
            return ["GPS NO-FIX", "SATS {:>2}  ALT N/A".format(int(sats) if sats is not None else 0)]
        try:
            lat_txt = "{:.5f}".format(float(lat))
        except Exception:
            lat_txt = str(lat)
        try:
            lon_txt = "{:.5f}".format(float(lon))
        except Exception:
            lon_txt = str(lon)
        alt_txt = "ALT {:>5}".format("{:.1f}m".format(float(alt))) if alt not in (None, "") else "ALT N/A"
        speed_txt = "SPD {:>5}".format("{:.1f}kmh".format(float(speed))) if speed not in (None, "") else "SPD N/A"
        sats_txt = "SATS {:>2}".format(int(sats) if sats is not None else 0)
        line1 = "LAT {}".format(lat_txt)
        line2 = "LON {}".format(lon_txt)
        line3 = "{} {} {}".format(sats_txt, alt_txt, speed_txt)
        return [line1, line2, line3]

    @staticmethod
    def _format_cell_lines(operator, cell_info, registration, rssi, csq):
        signal_txt = []
        if rssi is not None:
            try:
                signal_txt.append("RSSI {:+.0f}dBm".format(float(rssi)))
            except Exception:
                pass
        if csq is not None:
            try:
                signal_txt.append("CSQ {:>2}".format(int(csq)))
            except Exception:
                pass
        if not signal_txt:
            signal_txt.append("RSSI N/A")
        lines = ["NET {} ({})".format(operator, registration or "?")]
        if cell_info:
            lines.append("CELL {}".format(cell_info[:26]))
            if len(cell_info) > 26:
                lines.append("      {}".format(cell_info[26:52]))
        lines.append(" ".join(signal_txt))
        return lines
