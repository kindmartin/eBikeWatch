"""Async dashboard with screen management and theme toggle."""

import uasyncio as asyncio
from machine import Pin, SPI

try:
    from drivers.lcd1p69 import LCD1p69
except ImportError:  # fallback when drivers/ not on sys.path
    from lcd1p69 import LCD1p69
from UI_helpers.writer import Writer

LARGE_FONT_MODULE = "sevenSegment_80"
SMALL_FONT_MODULE = "sevenSegment_30"
HEADER_FONT_MODULE = "Font00_24"
BOTTOM_FONT_MODULE = "Font00_24"
SPRITE_MODULE = "pic.bat_chging"

try:
    font_large = __import__(LARGE_FONT_MODULE)
    font_small = __import__(SMALL_FONT_MODULE)
    font_header = __import__(HEADER_FONT_MODULE)
    font_bottom = __import__(BOTTOM_FONT_MODULE)
except ImportError:
    raise RuntimeError(
        "Upload writer.py plus sevenSegment_80.py, sevenSegment_30.py, Font00_24.py before running"
    )

try:
    from pic.bat_chging import WIDTH as ICON_WIDTH, HEIGHT as ICON_HEIGHT, DATA as ICON_DATA
except ImportError:
    raise RuntimeError("Upload pic/bat_chging.py (30x50 sprite) before running")

MOSI_PIN = 9
MISO_PIN = 10
SCK_PIN = 8
CS_PIN = 7
DC_PIN = 6
RST_PIN = 5
BL_PIN = 4
BUTTON_PIN = 0

SPI_ID = 2
SPI_BAUDRATE = 20_000_000

DEFAULT_HEADER_TEXT = "01360 km - 25 chg"
DEFAULT_UNIT_TEXT = "kmh"
DEFAULT_POWER_UNIT_TEXT = "watts"
DEFAULT_BOTTOM_TEXT = "32%  148wh"
DEFAULT_SPEED_MAX_VALUE = 99
DEFAULT_POWER_MAX_VALUE = 2400

HEADER_Y = 10
HEADER_TO_SPEED = 16
SPEED_TO_POWER = 12
GAP_PIXELS = 12
SPRITE_GAP = 12
BOTTOM_MARGIN = 10
RENDER_INTERVAL_MS = 100
BUTTON_POLL_MS = 40
BUTTON_DEBOUNCE_MS = 250


class Theme:
    def __init__(self, fg, bg):
        self.fg = fg
        self.bg = bg

    def as_tuple(self):
        return (self.fg, self.bg)


def text_extent(font_mod, text):
    width = 0
    for char in text:
        _, _, advance = font_mod.get_ch(char)
        width += advance
    return width


def recolor_region(lcd, theme, x, y, width, height):
    for row in range(height):
        py = y + row
        for col in range(width):
            px = x + col
            lcd.pixel(px, py, theme.fg if lcd.pixel(px, py) else theme.bg)


def render_text_block(lcd, writer, font_mod, theme, text, x, y, area_width):
    area_width = max(0, area_width)
    lcd.fill_rect(x, y, area_width, font_mod.height(), theme.bg)
    Writer.set_textpos(lcd.framebuf, y, x)
    writer.printstring(text)
    recolor_region(lcd, theme, x, y, area_width, font_mod.height())


class DashboardState:
    def __init__(self):
        self.speed = 0
        self.power = 0
        self.header_text = DEFAULT_HEADER_TEXT
        self.unit_text = DEFAULT_UNIT_TEXT
        self.power_unit_text = DEFAULT_POWER_UNIT_TEXT
        self.bottom_text = DEFAULT_BOTTOM_TEXT
        self.speed_max_value = DEFAULT_SPEED_MAX_VALUE
        self.power_max_value = DEFAULT_POWER_MAX_VALUE

    def snapshot(self):
        return (
            self.speed,
            self.power,
            self.header_text,
            self.unit_text,
            self.power_unit_text,
            self.bottom_text,
            self.speed_max_value,
            self.power_max_value,
        )

    def set_speed(self, value):
        self.speed = max(0, min(int(value), int(self.speed_max_value)))

    def set_power(self, value):
        self.power = max(0, min(int(value), int(self.power_max_value)))

    def set_header_text(self, text):
        self.header_text = str(text)

    def set_bottom_text(self, text):
        self.bottom_text = str(text)

    def set_unit_texts(self, speed_unit, power_unit):
        self.unit_text = str(speed_unit)
        self.power_unit_text = str(power_unit)

    def configure_limits(self, speed_max, power_max):
        self.speed_max_value = max(0, int(speed_max))
        self.power_max_value = max(0, int(power_max))


class DashboardRenderer:
    def __init__(self, lcd, state):
        self.lcd = lcd
        self.state = state
        self.writer_large = Writer(lcd.framebuf, font_large, verbose=False)
        self.writer_small = Writer(lcd.framebuf, font_small, verbose=False)
        self.writer_header = Writer(lcd.framebuf, font_header, verbose=False)
        self.writer_bottom = Writer(lcd.framebuf, font_bottom, verbose=False)
        for writer in (
            self.writer_large,
            self.writer_small,
            self.writer_header,
            self.writer_bottom,
        ):
            writer.set_clip(col_clip=True, wrap=False)
        self._theme_normal = Theme(0xFFFF, 0x0000)
        self._theme_inverted = Theme(0x0000, 0xFFFF)
        self.theme = self._theme_normal
        self.screen_index = 0
        self._screens = {}
        self.register_screen(0, self._draw_main_screen)
        self._last_snapshot = None
        self._sprite_x = 10
        self._sprite_y = lcd.height - ICON_HEIGHT - BOTTOM_MARGIN
        self._icon_buffer = bytearray(ICON_DATA)

    def register_screen(self, index, draw_callable):
        self._screens[index] = draw_callable

    def set_screen(self, index):
        if index not in self._screens:
            raise ValueError("Screen index {} not registered".format(index))
        if index != self.screen_index:
            self.screen_index = index
            self.mark_dirty()

    def mark_dirty(self):
        self._last_snapshot = None

    def set_theme(self, theme):
        self.theme = theme
        self.mark_dirty()

    def toggle_theme(self):
        self.theme = self._theme_inverted if self.theme is self._theme_normal else self._theme_normal
        self.mark_dirty()

    async def render_loop(self, interval_ms=RENDER_INTERVAL_MS):
        while True:
            await self._render_if_needed()
            await asyncio.sleep_ms(interval_ms)

    async def _render_if_needed(self):
        snapshot = (
            self.screen_index,
            self.theme.as_tuple(),
            self.state.snapshot(),
        )
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        self._draw_active_screen()
        self.lcd.show()

    def _draw_active_screen(self):
        draw_callable = self._screens.get(self.screen_index)
        if draw_callable is None:
            return
        draw_callable()

    def _draw_main_screen(self):
        lcd = self.lcd
        theme = self.theme
        state = self.state
        lcd.fill(theme.bg)

        header_text = state.header_text
        unit_text = state.unit_text
        power_unit_text = state.power_unit_text
        bottom_text = state.bottom_text

        header_width = text_extent(font_header, header_text)
        header_x = (lcd.width - header_width) // 2 if header_width <= lcd.width else 0
        render_text_block(
            lcd,
            self.writer_header,
            font_header,
            theme,
            header_text,
            header_x,
            HEADER_Y,
            max(0, min(header_width, lcd.width - header_x)),
        )

        speed_area_width = text_extent(font_large, str(state.speed_max_value))
        speed_text = str(state.speed)
        unit_width = text_extent(font_small, unit_text)
        large_height = font_large.height()
        small_height = font_small.height()

        total_width = speed_area_width + GAP_PIXELS + unit_width
        speed_x = (lcd.width - total_width) // 2
        speed_y = HEADER_Y + font_header.height() + HEADER_TO_SPEED
        unit_x = speed_x + speed_area_width + GAP_PIXELS
        if unit_x + unit_width > lcd.width:
            unit_x = max(0, lcd.width - unit_width)
        unit_y = speed_y + (large_height - small_height)

        render_text_block(lcd, self.writer_small, font_small, theme, unit_text, unit_x, unit_y, unit_width)
        render_text_block(lcd, self.writer_large, font_large, theme, speed_text, speed_x, speed_y, speed_area_width)

        power_area_width = text_extent(font_large, str(state.power_max_value))
        power_unit_width = text_extent(font_small, power_unit_text)
        power_text = str(state.power)
        right_margin = speed_x
        power_unit_x = lcd.width - right_margin - power_unit_width
        if power_unit_x < 0:
            power_unit_x = 0
        power_area_x = power_unit_x - GAP_PIXELS - power_area_width
        if power_area_x < 0:
            shift = -power_area_x
            power_area_x = 0
            power_unit_x = min(lcd.width - power_unit_width, power_unit_x + shift)
        power_y = speed_y + large_height + SPEED_TO_POWER
        power_unit_y = power_y + (large_height - small_height)

        render_text_block(lcd, self.writer_large, font_large, theme, power_text, power_area_x, power_y, power_area_width)
        render_text_block(
            lcd,
            self.writer_small,
            font_small,
            theme,
            power_unit_text,
            power_unit_x,
            power_unit_y,
            power_unit_width,
        )

        bottom_width = text_extent(font_bottom, bottom_text)
        bottom_height = font_bottom.height()
        text_x = self._sprite_x + ICON_WIDTH + SPRITE_GAP
        if text_x + bottom_width > lcd.width:
            text_x = max(0, lcd.width - bottom_width)
        text_y = self._sprite_y + (ICON_HEIGHT - bottom_height) // 2

        render_text_block(lcd, self.writer_bottom, font_bottom, theme, bottom_text, text_x, text_y, bottom_width)
        lcd.blit_buffer(self._icon_buffer, self._sprite_x, self._sprite_y, ICON_WIDTH, ICON_HEIGHT)


async def monitor_theme_button(renderer, pin):
    last_state = pin.value()
    while True:
        current = pin.value()
        if last_state == 1 and current == 0:
            renderer.toggle_theme()
            await asyncio.sleep_ms(BUTTON_DEBOUNCE_MS)
            current = pin.value()
        last_state = current
        await asyncio.sleep_ms(BUTTON_POLL_MS)


async def demo_state_driver(state):
    speed_direction = 1
    power_direction = 1
    while True:
        state.set_speed(state.speed + speed_direction)
        if state.speed in (0, state.speed_max_value):
            speed_direction *= -1
        if state.speed % 2 == 0:
            state.set_power(state.power + (27 * power_direction))
            if state.power >= state.power_max_value:
                state.set_power(state.power_max_value)
                power_direction = -1
            elif state.power <= 0:
                state.set_power(0)
                power_direction = 1
        await asyncio.sleep_ms(250)


STATE = DashboardState()
RENDERER = None


def get_state():
    return STATE


def get_renderer():
    return RENDERER


async def main():
    spi = SPI(
        SPI_ID,
        baudrate=SPI_BAUDRATE,
        polarity=0,
        phase=0,
        sck=Pin(SCK_PIN),
        mosi=Pin(MOSI_PIN),
        miso=Pin(MISO_PIN),
    )

    lcd = LCD1p69(
        spi,
        dc=Pin(DC_PIN, Pin.OUT),
        rst=Pin(RST_PIN, Pin.OUT),
        cs=Pin(CS_PIN, Pin.OUT),
        bl=Pin(BL_PIN, Pin.OUT),
        rotation=0,
    )

    global RENDERER

    state = STATE
    renderer = DashboardRenderer(lcd, state)
    RENDERER = renderer

    button_pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

    asyncio.create_task(renderer.render_loop())
    asyncio.create_task(monitor_theme_button(renderer, button_pin))
    asyncio.create_task(demo_state_driver(state))  # remove when integrating with real data

    while True:
        await asyncio.sleep(3600)


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
