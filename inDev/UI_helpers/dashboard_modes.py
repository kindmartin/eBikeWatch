"""Throttle mode selection dashboard for the LCD UI."""

from time import ticks_diff, ticks_ms

import fonts

from .dashboard_base import DashboardBase
from .writer import Writer

_FG = 0xFFFF
_BG = 0x0000
_ROW_GAP = 8
_PADDING_Y = 10
_STATUS_GAP = 4
_CONFIRM_DISPLAY_MS = 1800


def _text_width(font_mod, text):
    width = 0
    for ch in text:
        try:
            _, _, advance = font_mod.get_ch(ch)
        except Exception:
            advance = 0
        width += advance
    return width


def _normalize(mode):
    try:
        name = str(mode or "").strip().lower()
    except Exception:
        return ""
    if name in {"open", "open_loop", "raw"}:
        return "direct"
    return name


def _mode_label(mode):
    name = _normalize(mode)
    if name in {"open", "open_loop", "direct", "raw"}:
        return "DIRECT"
    if name == "power":
        return "POWER"
    if name == "speed":
        return "SPEED"
    if name == "torque":
        return "TORQUE"
    if name == "mix":
        return "MIX"
    return name.upper() if name else "-"


class DashboardModes(DashboardBase):
    """Render a selectable list of throttle modes using seven-segment font."""

    def __init__(self, ui_display):
        super().__init__(ui_display, title="MODE", font_name="sevenSegment_20", sep_color=0xF800)
        framebuf = self.lcd.framebuf

        self.font_mode = fonts.load("sevenSegment_30")
        self.font_small = self._header_font

        self.writer_mode = Writer(framebuf, self.font_mode, verbose=False)
        self.writer_mode.setcolor(_FG, _BG)
        self.writer_mode.set_clip(col_clip=True, wrap=False)

        self.writer_small = Writer(framebuf, self.font_small, verbose=False)
        self.writer_small.setcolor(_FG, _BG)
        self.writer_small.set_clip(col_clip=True, wrap=False)

        self._snapshot = None
        self._needs_full_refresh = True
        self._entered = False
        self._move_handler = None
        self._confirm_handler = None

    def request_full_refresh(self):
        super().request_full_refresh()
        self._needs_full_refresh = True

    def set_handlers(self, *, on_move=None, on_confirm=None):
        self._move_handler = on_move
        self._confirm_handler = on_confirm

    def is_entered(self):
        return bool(self._entered)

    def draw(self, state):
        if self._needs_full_refresh:
            self.ensure_header(force=True)
        else:
            self.ensure_header()

        modes = list(getattr(state, "throttle_modes", []))
        if not modes:
            modes = ["direct", "power", "speed", "torque", "mix"]
        normalized_modes = [_normalize(m) or "direct" for m in modes]

        selection_idx = getattr(state, "throttle_mode_index", 0)
        try:
            selection_idx = int(selection_idx)
        except Exception:
            selection_idx = 0
        if selection_idx < 0 or selection_idx >= len(normalized_modes):
            selection_idx = 0

        candidate = _normalize(getattr(state, "throttle_mode_candidate", normalized_modes[selection_idx]))
        if candidate not in normalized_modes:
            candidate = normalized_modes[selection_idx]
        active = _normalize(getattr(state, "throttle_mode_active", candidate))

        try:
            confirmed_ms = int(getattr(state, "throttle_mode_confirmed_ms", 0) or 0)
        except Exception:
            confirmed_ms = 0
        now_raw = ticks_ms()
        try:
            now_ms = int(now_raw or 0)
        except Exception:
            now_ms = 0
        recent_confirm = False
        if confirmed_ms:
            try:
                recent_confirm = ticks_diff(now_ms, confirmed_ms) < _CONFIRM_DISPLAY_MS
            except Exception:
                recent_confirm = False

        snapshot = (tuple(normalized_modes), selection_idx, candidate, active, recent_confirm, self._entered)
        if not self._needs_full_refresh and snapshot == self._snapshot:
            return

        self._render(normalized_modes, selection_idx, candidate, active, recent_confirm)
        self._snapshot = snapshot
        self._needs_full_refresh = False
        self.lcd.show()

    def handle_event(self, event, state, **kwargs):
        if event == "page_short":
            self._entered = not self._entered
            if not self._entered:
                self._reset_pending(state)
            else:
                self._sync_with_active(state)
            self.request_full_refresh()
            return {"handled": True, "refresh_self": True}

        if not self._entered:
            return False

        if event == "up_short":
            self._invoke_move(-1)
            return {"handled": True}

        if event == "down_short":
            self._invoke_move(1)
            return {"handled": True}

        if event == "page_long":
            confirmed = self._invoke_confirm()
            self._entered = False
            if confirmed:
                self.request_full_refresh()
                return {"handled": True, "refresh_self": True}
            self._reset_pending(state)
            self.request_full_refresh()
            return {"handled": True}

        return False

    def _render(self, modes, selection_idx, candidate, active, recent_confirm):
        lcd = self.lcd
        top = self.header_height
        lcd.fill_rect(0, top, lcd.width, lcd.height - top, _BG)

        status_area_height = self.font_small.height() * 2 + _STATUS_GAP + 4
        status_y = lcd.height - status_area_height
        if status_y < top:
            status_y = top
        list_bottom = status_y - _STATUS_GAP

        y = top + _PADDING_Y
        for idx, mode in enumerate(modes):
            label = _mode_label(mode)
            if y + self.font_mode.height() > list_bottom:
                break
            width = _text_width(self.font_mode, label)
            x = max(0, (lcd.width - width) // 2)
            Writer.set_textpos(lcd.framebuf, y, x)
            if self._entered:
                invert = idx == selection_idx
            else:
                invert = _normalize(mode) == active
            self.writer_mode.printstring(label, invert=invert)
            y += self.font_mode.height() + _ROW_GAP

        lcd.fill_rect(0, status_y, lcd.width, lcd.height - status_y, _BG)
        if candidate == active:
            status_label = "ACTIVE {}".format(_mode_label(active))
        elif recent_confirm:
            status_label = "SAVED {}".format(_mode_label(active))
        else:
            status_label = "SELECT {}".format(_mode_label(candidate))

        if self._entered:
            instructions = "UP/DN SELECT  PAGE LONG CONFIRM  SH EXIT"
        else:
            instructions = "PAGE SHORT ENTER  UP NEXT  DOWN PREV"

        self._draw_small_line(status_label, status_y + 2)
        self._draw_small_line(instructions, status_y + 2 + self.font_small.height())

    def _draw_small_line(self, text, y):
        lcd = self.lcd
        width = _text_width(self.font_small, text)
        x = max(0, (lcd.width - width) // 2)
        Writer.set_textpos(lcd.framebuf, y, x)
        self.writer_small.printstring(text)

    def _invoke_move(self, delta):
        handler = self._move_handler
        if callable(handler):
            try:
                handler(delta)
            except Exception as exc:
                print("[Mode] move error:", exc)
        else:
            print("[Mode] move handler missing")

    def _invoke_confirm(self):
        handler = self._confirm_handler
        if callable(handler):
            try:
                result = handler()
                return bool(result)
            except Exception as exc:
                print("[Mode] confirm error:", exc)
        else:
            print("[Mode] confirm handler missing")
        return False

    def _reset_pending(self, state):
        active = _normalize(getattr(state, "throttle_mode_active", "direct"))
        modes = getattr(state, "throttle_modes", [])
        if active in modes:
            try:
                idx = modes.index(active)
            except Exception:
                idx = 0
        elif modes:
            idx = 0
            active = _normalize(modes[idx])
        else:
            idx = 0
            active = "direct"
        state.throttle_mode_index = idx
        state.throttle_mode_candidate = active
        state.throttle_mode_confirmed_ms = 0

    def _sync_with_active(self, state):
        active = _normalize(getattr(state, "throttle_mode_active", "direct"))
        modes = getattr(state, "throttle_modes", [])
        if active in modes:
            try:
                idx = modes.index(active)
            except Exception:
                idx = 0
        else:
            idx = getattr(state, "throttle_mode_index", 0) or 0
        state.throttle_mode_index = idx
        if modes:
            try:
                candidate = _normalize(modes[idx])
            except Exception:
                candidate = active
        else:
            candidate = active
        state.throttle_mode_candidate = candidate
