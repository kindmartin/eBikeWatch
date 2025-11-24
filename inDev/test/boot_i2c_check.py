"""Pantalla de verificación rápida del bus I2C.

Escanea las direcciones presentes en el bus y las muestra con fuente
seven-segment de 30px. Cada pulsación del botón Page vuelve a escanear.
"""

from time import sleep_ms

import machine

import HW
from drivers.lcd1p69 import LCD1p69
from fonts import sevenSegment_30
from UI_helpers.writer import Writer


def _init_display():
    spi = machine.SPI(
        HW.SPI_ID,
        baudrate=HW.SPI_BAUDRATE,
        polarity=0,
        phase=0,
        sck=machine.Pin(HW.SCK_PIN),
        mosi=machine.Pin(HW.MOSI_PIN),
        miso=machine.Pin(HW.MISO_PIN) if getattr(HW, "MISO_PIN", None) is not None else None,
    )
    spi_baudrate = getattr(HW, "SPI_BAUDRATE", 20_000_000)
    display = LCD1p69(
        spi,
        dc=machine.Pin(HW.DC_PIN, machine.Pin.OUT),
        rst=machine.Pin(HW.RST_PIN, machine.Pin.OUT),
        cs=machine.Pin(HW.CS_PIN, machine.Pin.OUT),
        bl=machine.Pin(HW.BL_PIN, machine.Pin.OUT),
        baudrate=spi_baudrate,
    )
    if hasattr(display, "set_backlight"):
        display.set_backlight(True)
    display.fill(0)
    display.show()
    writer = Writer(display.framebuf, sevenSegment_30, verbose=False)
    writer.set_clip(col_clip=True, wrap=False)
    return display, writer


def _format_addresses(addresses, per_line=3):
    lines = []
    if not addresses:
        return ["--"]
    for idx in range(0, len(addresses), per_line):
        chunk = addresses[idx : idx + per_line]
        text = " ".join("{:02X}".format(addr) for addr in chunk)
        lines.append(text)
    return lines


def _render(display, writer, lines):
    display.fill(0)
    y = 20
    line_height = writer.height + 6
    for line in lines:
        Writer.set_textpos(display.framebuf, y, 8)
        writer.printstring(line)
        y += line_height
        if y >= display.height:
            break
    Writer.set_textpos(display.framebuf, 0, 0)
    display.show()


def _scan_bus():
    try:
        i2c = HW.make_i2c()
    except Exception as exc:
        print("[I2C] init error:", exc)
        return []
    try:
        return i2c.scan()
    except Exception as exc:
        print("[I2C] scan error:", exc)
        return []


def check():
    display, writer = _init_display()
    page_pin = HW.make_input(HW.PAGE_BTN_PIN)

    def refresh():
        addresses = _scan_bus() or []
        lines = _format_addresses(addresses)
        print("[I2C] devices:", ", ".join("0x{:02X}".format(addr) for addr in addresses) or "none")
        _render(display, writer, lines)

    refresh()
    last_state = page_pin.value()
    while True:
        state = page_pin.value()
        if state == 0 and last_state == 1:
            refresh()
            # Esperar a que se libere el botón
            while page_pin.value() == 0:
                sleep_ms(20)
        last_state = state
        sleep_ms(40)


check()