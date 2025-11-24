"""Common helpers for dashboard screens."""

import fonts
from .writer import Writer

_DEFAULT_HEADER_FONT = "sevenSegment_20"
_DEFAULT_FG = 0xFFFF
_DEFAULT_BG = 0x0000
_HEADER_PAD_Y = 2


def _text_width(font_mod, text):
    width = 0
    for ch in text:
        try:
            _, _, adv = font_mod.get_ch(ch)
        except Exception:
            adv = 0
        width += adv
    return width


class DashboardBase:
    """Base class providing a common title header for dashboards."""

    def __init__(self, ui_display, title, *, fg=_DEFAULT_FG, bg=_DEFAULT_BG, font_name=_DEFAULT_HEADER_FONT, sep_color=None):
        self.ui = ui_display
        self.lcd = ui_display.display
        framebuf = self.lcd.framebuf

        self._header_font = fonts.load(font_name)
        self._header_writer = Writer(framebuf, self._header_font, verbose=False)
        self._header_writer.setcolor(fg, bg)
        self._header_writer.set_clip(col_clip=True, wrap=False)

        self._header_fg = fg
        self._header_bg = bg
        self._header_sep_color = sep_color if sep_color is not None else fg
        self._header_title = title
        self._screen_index = 0
        self._header_dirty = True
        self._header_text = self._compose_header_text()
        self._header_text_height = self._header_font.height() + (_HEADER_PAD_Y * 2)
        self._header_height = self._header_text_height + 3

    @property
    def header_height(self):
        return self._header_height

    @property
    def header_title(self):
        return self._header_title

    def set_header_title(self, title):
        if title != self._header_title:
            self._header_title = title
            self._header_text = self._compose_header_text()
            self._header_dirty = True

    def set_screen_index(self, index):
        try:
            idx = int(index)
        except Exception:
            idx = 0
        if idx != self._screen_index:
            self._screen_index = idx
            self._header_text = self._compose_header_text()
            self._header_dirty = True

    def ensure_header(self, force=False):
        if force:
            self._header_dirty = True
        if not self._header_dirty:
            return
        self._draw_header()
        self._header_dirty = False

    def request_full_refresh(self):
        self._header_dirty = True

    def handle_event(self, event, state, **kwargs):
        """Handle input events; return truthy if consumed."""
        return False

    def set_separator_color(self, color):
        try:
            value = int(color) & 0xFFFF
        except Exception:
            value = self._header_fg
        if value != self._header_sep_color:
            self._header_sep_color = value
            self._header_dirty = True

    def _compose_header_text(self):
        title = self._header_title or ""
        if not title:
            return str(self._screen_index)
        return "{}-{}".format(self._screen_index, title)

    def _draw_header(self):
        lcd = self.lcd
        header_text_height = self._header_text_height
        lcd.fill_rect(0, 0, lcd.width, header_text_height, self._header_bg)
        text = self._header_text
        width = _text_width(self._header_font, text)
        x = max(0, (lcd.width - width) // 2)
        Writer.set_textpos(lcd.framebuf, _HEADER_PAD_Y, x)
        self._header_writer.printstring(text)
        sep_y = header_text_height + 1
        if sep_y < self._header_height:
            lcd.fill_rect(0, sep_y, lcd.width, 1, self._header_sep_color)
            remainder = self._header_height - (sep_y + 1)
            if remainder > 0:
                lcd.fill_rect(0, sep_y + 1, lcd.width, remainder, self._header_bg)