"""MicroPython driver for the 1.69 inch 240x280 ST7789 LCD.

Tested with MicroPython v1.27 on ESP32-WROVER.
"""

import time
from machine import Pin, SPI
import framebuf


class _FrameBuffer(framebuf.FrameBuffer):
    def __init__(self, buffer, width, height):
        super().__init__(buffer, width, height, framebuf.RGB565)
        self.width = width
        self.height = height


_CHUNK_SIZE = 4096


def rgb565(r: int, g: int, b: int) -> int:
    """Convert 8-bit RGB values to a 16-bit RGB565 color."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class _NullPin:
    """Placeholder when a CS pin is not provided."""

    def value(self, *_):
        return 0


class LCD1p69:
    """Driver for the 240x280 ST7789 display bundled with the 1.69 inch module."""

    raw_width = 240
    raw_height = 280
    _ROTATION = {
        0: {"madctl": 0x00, "width": 240, "height": 280, "x_offset": 0, "y_offset": 20},
        1: {"madctl": 0x70, "width": 280, "height": 240, "x_offset": 20, "y_offset": 0},
    }

    def __init__(
        self,
        spi: SPI,
        dc,
        rst,
        cs=None,
        bl=None,
        *,
        rotation: int = 0,
        baudrate: int = 40_000_000,
        backlight_on: bool = True,
    ) -> None:
        if rotation not in self._ROTATION:
            raise ValueError("rotation must be 0 or 1")
        self._spi = spi
        if hasattr(self._spi, "init"):
            self._spi.init(baudrate=baudrate, polarity=0, phase=0)
        self._dc = self._ensure_output(dc, 0)
        self._rst = self._ensure_output(rst, 1)
        self._cs = self._ensure_output(cs, 1) if cs is not None else _NullPin()
        self._bl = self._ensure_output(bl, 0) if bl is not None else None
        self._cmd_buf = bytearray(1)
        self.buffer = bytearray(self.raw_width * self.raw_height * 2)
        self.framebuf = None
        self._rotation = None
        self._config = None
        self._set_rotation(rotation)
        self.reset()
        self._init_display()
        self.fill(0x0000)
        self.show()
        if self._bl is not None:
            self.set_backlight(backlight_on)

    @staticmethod
    def _ensure_output(pin, initial: int) -> Pin:
        if isinstance(pin, Pin):
            pin.init(Pin.OUT, value=initial)
            return pin
        return Pin(pin, Pin.OUT, value=initial)

    def reset(self) -> None:
        self._rst.value(1)
        time.sleep_ms(10)
        self._rst.value(0)
        time.sleep_ms(10)
        self._rst.value(1)
        time.sleep_ms(10)

    def _write_cmd(self, value: int) -> None:
        self._cmd_buf[0] = value & 0xFF
        self._dc.value(0)
        self._cs.value(0)
        self._spi.write(self._cmd_buf)
        self._cs.value(1)

    def _write_data(self, data) -> None:
        self._dc.value(1)
        self._cs.value(0)
        self._spi.write(data)
        self._cs.value(1)

    def _write_u8(self, value: int) -> None:
        self._cmd_buf[0] = value & 0xFF
        self._write_data(self._cmd_buf)

    def _init_display(self) -> None:
        cfg = self._config
        self._write_cmd(0x36)
        self._write_u8(cfg["madctl"])

        self._write_cmd(0x3A)
        self._write_u8(0x05)

        self._write_cmd(0xB2)
        self._write_data(b"\x0B\x0B\x00\x33\x35")

        self._write_cmd(0xB7)
        self._write_u8(0x11)

        self._write_cmd(0xBB)
        self._write_u8(0x35)

        self._write_cmd(0xC0)
        self._write_u8(0x2C)

        self._write_cmd(0xC2)
        self._write_u8(0x01)

        self._write_cmd(0xC3)
        self._write_u8(0x0D)

        self._write_cmd(0xC4)
        self._write_u8(0x20)

        self._write_cmd(0xC6)
        self._write_u8(0x13)

        self._write_cmd(0xD0)
        self._write_data(b"\xA4\xA1")

        self._write_cmd(0xD6)
        self._write_u8(0xA1)

        self._write_cmd(0xE0)
        self._write_data(
            b"\xF0\x06\x0B\x0A\x09\x26\x29\x33\x41\x18\x16\x15\x29\x2D"
        )

        self._write_cmd(0xE1)
        self._write_data(
            b"\xF0\x04\x08\x08\x07\x03\x28\x32\x40\x3B\x19\x18\x2A\x2E"
        )

        self._write_cmd(0xE4)
        self._write_data(b"\x25\x00\x00")

        self._write_cmd(0x21)
        self._write_cmd(0x11)
        time.sleep_ms(120)
        self._write_cmd(0x29)

    def _set_rotation(self, rotation: int, *, send: bool = False) -> None:
        cfg = self._ROTATION[rotation]
        self._config = cfg
        self._rotation = rotation
        self.width = cfg["width"]
        self.height = cfg["height"]
        self._x_offset = cfg["x_offset"]
        self._y_offset = cfg["y_offset"]
        self.framebuf = _FrameBuffer(self.buffer, self.width, self.height)
        if send:
            self._write_cmd(0x36)
            self._write_u8(cfg["madctl"])

    def set_rotation(self, rotation: int) -> None:
        if rotation not in self._ROTATION:
            raise ValueError("rotation must be 0 or 1")
        if rotation == self._rotation:
            return
        self._set_rotation(rotation, send=True)

    def set_backlight(self, state: bool) -> None:
        if self._bl is None:
            return
        self._bl.value(1 if state else 0)

    def _set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        x0 += self._x_offset
        x1 += self._x_offset
        y0 += self._y_offset
        y1 += self._y_offset
        self._write_cmd(0x2A)
        self._write_data(bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self._write_cmd(0x2B)
        self._write_data(bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))
        self._write_cmd(0x2C)

    def show(self, *, x: int = 0, y: int = 0, width: int = None, height: int = None) -> None:
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        x1 = x + width - 1
        y1 = y + height - 1
        self._set_window(x, y, x1, y1)
        mv = memoryview(self.buffer)
        start = (y * self.width + x) * 2
        row_stride = self.width * 2
        if x == 0 and width == self.width:
            span = height * row_stride
            block = mv[start : start + span]
            for idx in range(0, len(block), _CHUNK_SIZE):
                self._write_data(block[idx : idx + _CHUNK_SIZE])
            return
        for row in range(height):
            offset = start + row * row_stride
            line = mv[offset : offset + width * 2]
            self._write_data(line)

    def write_rect(self, x: int, y: int, width: int, height: int, data) -> None:
        self._set_window(x, y, x + width - 1, y + height - 1)
        mv = memoryview(data)
        for idx in range(0, len(mv), _CHUNK_SIZE):
            self._write_data(mv[idx : idx + _CHUNK_SIZE])

    def fill(self, color: int) -> None:
        self.framebuf.fill(color)

    def pixel(self, x: int, y: int, color: int = None):
        if color is None:
            return self.framebuf.pixel(x, y)
        self.framebuf.pixel(x, y, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: int) -> None:
        self.framebuf.line(x0, y0, x1, y1, color)

    def rect(self, x: int, y: int, width: int, height: int, color: int) -> None:
        self.framebuf.rect(x, y, width, height, color)

    def fill_rect(self, x: int, y: int, width: int, height: int, color: int) -> None:
        self.framebuf.fill_rect(x, y, width, height, color)

    def text(self, string: str, x: int, y: int, color: int = 0xFFFF) -> None:
        self.framebuf.text(string, x, y, color)

    def blit(self, source, x: int, y: int) -> None:
        self.framebuf.blit(source, x, y)

    def blit_buffer(self, data, x: int, y: int, width: int, height: int) -> None:
        buf = data if isinstance(data, bytearray) else bytearray(data)
        tmp = framebuf.FrameBuffer(buf, width, height, framebuf.RGB565)
        self.framebuf.blit(tmp, x, y)

    def clear(self, color: int = 0x0000) -> None:
        self.fill(color)
        self.show()
