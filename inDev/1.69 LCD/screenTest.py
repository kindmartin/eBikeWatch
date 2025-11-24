"""Dashboard demo with animated speed, header, icon, and footer text."""

import time
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

SPI_ID = 2
SPI_BAUDRATE = 20_000_000

FG_COLOR = 0xFFFF
BG_COLOR = 0x0000
HEADER_TEXT = "01360 km - 25 chg"
UNIT_TEXT = "kmh"
POWER_UNIT_TEXT = "watts"
BOTTOM_TEXT = "32%  148wh"
GAP_PIXELS = 12
SPRITE_GAP = 12
BOTTOM_MARGIN = 10
POWER_MAX = 2400
POWER_STEP = 27
POWER_UPDATE_INTERVAL = 2
ROTATION = 0

ASCENT_DELAY_MS = 500  # 2 Hz updates while rising
DESCENT_DELAY_MS = 333  # ~3 Hz while falling


def text_extent(font_mod, text: str) -> int:
    width = 0
    for char in text:
        _, _, w = font_mod.get_ch(char)
        width += w
    return width


def recolor_region(lcd: LCD1p69, x: int, y: int, width: int, height: int) -> None:
    for row in range(height):
        py = y + row
        for col in range(width):
            px = x + col
            lcd.pixel(px, py, FG_COLOR if lcd.pixel(px, py) else BG_COLOR)


def power_value_generator():
    value = 0
    direction = 1
    while True:
        yield value
        value += POWER_STEP * direction
        if direction > 0 and value >= POWER_MAX:
            value = POWER_MAX
            direction = -1
        elif direction < 0 and value <= 0:
            value = 0
            direction = 1


def render_header(lcd: LCD1p69, writer: Writer, font_mod, y: int) -> None:
    header_width = text_extent(font_mod, HEADER_TEXT)
    x = (lcd.width - header_width) // 2 if header_width <= lcd.width else 0
    writer.set_clip(col_clip=True, wrap=False)
    Writer.set_textpos(lcd.framebuf, y, x)
    writer.printstring(HEADER_TEXT)
    region_width = min(header_width, lcd.width - x)
    recolor_region(lcd, x, y, region_width, font_mod.height())


def render_units(lcd: LCD1p69, writer: Writer, font_mod, x: int, y: int) -> None:
    writer.set_clip(col_clip=True, wrap=False)
    Writer.set_textpos(lcd.framebuf, y, x)
    writer.printstring(UNIT_TEXT)
    recolor_region(lcd, x, y, text_extent(font_mod, UNIT_TEXT), font_mod.height())


def render_secondary_units(lcd: LCD1p69, writer: Writer, font_mod, x: int, y: int) -> None:
    writer.set_clip(col_clip=True, wrap=False)
    Writer.set_textpos(lcd.framebuf, y, x)
    writer.printstring(POWER_UNIT_TEXT)
    recolor_region(lcd, x, y, text_extent(font_mod, POWER_UNIT_TEXT), font_mod.height())


def render_speed(
    lcd: LCD1p69,
    writer: Writer,
    font_mod,
    value: int,
    area_x: int,
    area_y: int,
    area_width: int,
) -> None:
    lcd.fill_rect(area_x, area_y, area_width, font_mod.height(), BG_COLOR)
    text = str(value)
    text_width = text_extent(font_mod, text)
    text_x = area_x + (area_width - text_width)
    Writer.set_textpos(lcd.framebuf, area_y, text_x)
    writer.printstring(text)
    recolor_region(lcd, area_x, area_y, area_width, font_mod.height())


def render_power(lcd: LCD1p69, writer: Writer, font_mod, value: int, area_x: int, area_y: int, area_width: int) -> None:
    lcd.fill_rect(area_x, area_y, area_width, font_mod.height(), BG_COLOR)
    text = str(value)
    text_width = text_extent(font_mod, text)
    text_x = area_x + (area_width - text_width)
    Writer.set_textpos(lcd.framebuf, area_y, text_x)
    writer.printstring(text)
    recolor_region(lcd, area_x, area_y, area_width, font_mod.height())


def main() -> None:
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
        rotation=ROTATION,
    )

    lcd.fill(BG_COLOR)

    writer_large = Writer(lcd.framebuf, font_large, verbose=False)
    writer_small = Writer(lcd.framebuf, font_small, verbose=False)
    writer_header = Writer(lcd.framebuf, font_header, verbose=False)
    writer_bottom = Writer(lcd.framebuf, font_bottom, verbose=False)
    for writer in (writer_large, writer_small, writer_header, writer_bottom):
        writer.set_clip(col_clip=True, wrap=False)

    header_y = 10
    render_header(lcd, writer_header, font_header, header_y)

    max_speed_width = max(text_extent(font_large, str(value)) for value in range(100))
    large_height = font_large.height()
    small_width = text_extent(font_small, UNIT_TEXT)
    small_height = font_small.height()

    total_width = max_speed_width + GAP_PIXELS + small_width
    speed_x = (lcd.width - total_width) // 2
    speed_y = header_y + font_header.height() + 16
    unit_x = speed_x + max_speed_width + GAP_PIXELS
    if unit_x + small_width > lcd.width:
        unit_x = max(0, lcd.width - small_width)
    unit_y = speed_y + (large_height - small_height)

    render_units(lcd, writer_small, font_small, unit_x, unit_y)
    render_speed(lcd, writer_large, font_large, 0, speed_x, speed_y, max_speed_width)

    power_samples = list(range(0, POWER_MAX, POWER_STEP))
    if POWER_MAX not in power_samples:
        power_samples.append(POWER_MAX)
    power_max_width = max(text_extent(font_large, str(value)) for value in power_samples)
    power_area_width = max(power_max_width, max_speed_width)
    power_y = speed_y + large_height + 12
    right_margin = speed_x
    power_unit_x = lcd.width - right_margin - small_width
    if power_unit_x < 0:
        power_unit_x = 0
    power_area_x = power_unit_x - GAP_PIXELS - power_area_width
    if power_area_x < 0:
        shift = -power_area_x
        power_area_x = 0
        power_unit_x = min(lcd.width - small_width, power_unit_x + shift)
    power_unit_y = power_y + (large_height - small_height)

    render_secondary_units(lcd, writer_small, font_small, power_unit_x, power_unit_y)
    power_gen = power_value_generator()
    current_power = next(power_gen)
    render_power(lcd, writer_large, font_large, current_power, power_area_x, power_y, power_area_width)

    bottom_text_width = text_extent(font_bottom, BOTTOM_TEXT)
    bottom_text_height = font_bottom.height()
    sprite_x = 10
    sprite_y = lcd.height - ICON_HEIGHT - BOTTOM_MARGIN
    lcd.blit_buffer(bytearray(ICON_DATA), sprite_x, sprite_y, ICON_WIDTH, ICON_HEIGHT)

    text_x = sprite_x + ICON_WIDTH + SPRITE_GAP
    if text_x + bottom_text_width > lcd.width:
        text_x = max(0, lcd.width - bottom_text_width)
    text_y = sprite_y + (ICON_HEIGHT - bottom_text_height) // 2

    Writer.set_textpos(lcd.framebuf, text_y, text_x)
    writer_bottom.printstring(BOTTOM_TEXT)
    recolor_region(lcd, text_x, text_y, bottom_text_width, bottom_text_height)

    lcd.show()

    speed_sequence = [(value, ASCENT_DELAY_MS) for value in range(0, 51)]
    speed_sequence.extend((value, DESCENT_DELAY_MS) for value in range(49, -1, -1))

    tick = 0
    while True:
        for speed_value, delay_ms in speed_sequence:
            render_speed(lcd, writer_large, font_large, speed_value, speed_x, speed_y, max_speed_width)
            tick += 1
            if tick % POWER_UPDATE_INTERVAL == 0:
                current_power = next(power_gen)
                render_power(lcd, writer_large, font_large, current_power, power_area_x, power_y, power_area_width)
            lcd.show()
            time.sleep_ms(delay_ms)


main()
