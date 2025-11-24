"""UI facade for the ST7789 LCD display."""

import machine

import HW
from drivers.lcd1p69 import LCD1p69


class _MonoAdapter:
    """Adapts the RGB565 frame buffer to a 1-bit style interface."""

    def __init__(self, lcd):
        self._lcd = lcd
        self._fb = lcd.framebuf
        self.width = lcd.width
        self.height = lcd.height
        self._fg = 0xFFFF
        self._bg = 0x0000

    def _color(self, value):
        return self._fg if value else self._bg

    def set_colors(self, fg, bg):
        self._fg = int(fg) & 0xFFFF
        self._bg = int(bg) & 0xFFFF

    def fill(self, color):
        self._fb.fill(self._color(color))

    def text(self, msg, x, y, color=1):
        self._fb.text(msg, x, y, self._color(color))

    def fill_rect(self, x, y, w, h, color=1):
        self._fb.fill_rect(x, y, w, h, self._color(color))

    def pixel(self, x, y, color=1):
        self._fb.pixel(x, y, self._color(color))

    def show(self):
        self._lcd.show()


class DisplayUI:
    def __init__(self, rotation=0):
        spi = machine.SPI(
            HW.SPI_ID,
            baudrate=HW.SPI_BAUDRATE,
            polarity=0,
            phase=0,
            sck=machine.Pin(HW.SCK_PIN),
            mosi=machine.Pin(HW.MOSI_PIN),
            miso=machine.Pin(HW.MISO_PIN) if getattr(HW, "MISO_PIN", None) is not None else None,
        )
        self.display = LCD1p69(
            spi,
            dc=machine.Pin(HW.DC_PIN, machine.Pin.OUT),
            rst=machine.Pin(HW.RST_PIN, machine.Pin.OUT),
            cs=machine.Pin(HW.CS_PIN, machine.Pin.OUT),
            bl=machine.Pin(HW.BL_PIN, machine.Pin.OUT),
            rotation=rotation,
            baudrate=HW.SPI_BAUDRATE,
        )
        self.d = _MonoAdapter(self.display)
        self.width = self.display.width
        self.height = self.display.height
        self._fg_color = 0xFFFF
        self._bg_color = 0x0000
        self.set_colors(self._fg_color, self._bg_color)
        self.clear()

    def set_colors(self, fg=0xFFFF, bg=0x0000):
        self._fg_color = int(fg) & 0xFFFF
        self._bg_color = int(bg) & 0xFFFF
        self.d.set_colors(self._fg_color, self._bg_color)

    def clear(self):
        self.d.fill(0)
        self.display.show()

    def draw_boot(self, title="eBike Test"):
        self.d.fill(0)
        self.d.text(title, 0, 0, 1)
        self.d.text("uasyncio + _thread", 0, 16, 1)
        self.d.text("ST7789 OK", 0, 32, 1)
        self.display.show()

    def draw_i2c_scan(self):
        try:
            i2c = HW.make_i2c()
            addrs = [hex(a) for a in i2c.scan()]
        except Exception:
            addrs = []
        self.d.fill(0); self.d.text("I2C Scan:", 0, 0, 1)
        y = 16; line = ",".join(addrs)
        for i in range(0, len(line), 21):
            self.d.text(line[i:i+21], 0, y, 1); y += 12
            if y > 54: break
        self.d.show()

    def _draw_screen_number(self, n):
        self.d.fill_rect(120, 0, 8, 10, 0)
        self.d.text(str(n), 120, 0, 1)

    _DIGITS = {
        '0': (" XXXXX  ","XX   XX ","XX  XXX ","XX X XX ","XXX  XX ","XX   XX "," XXXXX  ","        "),
        '1': ("   XX   ","  XXX   ","   XX   ","   XX   ","   XX   ","   XX   "," XXXXXX ","        "),
        '2': (" XXXXX  ","XX   XX ","     XX ","    XX  ","   XX   ","  XX    ","XXXXXXX ","        "),
        '3': ("XXXXXX  ","     XX ","    XX  ","  XXXX  ","     XX ","     XX ","XXXXXX  ","        "),
        '4': ("   XXX  ","  XXXX  "," XX XX  ","XX  XX  ","XXXXXXX ","    XX  ","    XX  ","        "),
        '5': ("XXXXXXX ","XX      ","XXXXX   ","    XX  ","     XX ","XX   XX "," XXXXX  ","        "),
        '6': ("  XXXX  "," XX     ","XX      ","XXXXXX  ","XX   XX ","XX   XX "," XXXXX  ","        "),
        '7': ("XXXXXXX ","     XX ","    XX  ","   XX   ","  XX    ","  XX    ","  XX    ","        "),
        '8': (" XXXXX  ","XX   XX ","XX   XX "," XXXXX  ","XX   XX ","XX   XX "," XXXXX  ","        "),
        '9': (" XXXXX  ","XX   XX ","XX   XX "," XXXXXX ","     XX ","    XX  "," XXXX   ","        "),
    }
    def _draw_big_digit(self, ch, x, y):
        pat = self._DIGITS.get(ch, self._DIGITS['0'])
        for row in range(8):
            line = pat[row]
            for col in range(8):
                if line[col] != ' ':
                    px = x + col*2; py = y + row*2
                    self.d.pixel(px,py,1); self.d.pixel(px+1,py,1)
                    self.d.pixel(px,py+1,1); self.d.pixel(px+1,py+1,1)

    def draw_speed_big(self, value, unit_x=96, y=16):
        try:
            n = int(value) if value is not None else 0
            n = max(0, min(99, n))
        except Exception:
            n = 0
        s = str(n); total_w = 18 * len(s); start_x = unit_x - total_w - 4
        for i, ch in enumerate(s):
            self._draw_big_digit(ch, start_x + i*18, y)
        self.d.text("km/h", unit_x, y + 8, 1)

    def draw_screen_main(self, vbat, pin, spd, mins, km, wh, screen_idx=0):
        d = self.d
        d.fill(0)
        d.text("B:{:.1f}V  P:{:d}W".format(vbat or 0.0, int(pin or 0)), 0, 0, 1)
        self._draw_screen_number(screen_idx)
        self.draw_speed_big(spd or 0.0, unit_x=96, y=16)
        d.text("{}m  {}km  {}Wh".format(int(mins or 0), int(km or 0), int(wh or 0)), 0, 50, 1)
        d.show()

    def draw_screen_pr(self, mtemp, ctemp, vs, rpm, bv, bc, pin, screen_idx=1):
        d = self.d
        d.fill(0); d.text("Phaserunner", 0, 0, 1); self._draw_screen_number(screen_idx)
        d.text("M:{:>3}C  C:{:>3}C".format(int(mtemp or -1), int(ctemp or -1)), 0, 12, 1)
        d.text("v:{:>4}  rpm:{:>5}".format(int(vs or -1), int(rpm or -1)), 0, 24, 1)
        d.text("V:{:>5.1f} I:{:>5.1f}".format(bv or 0.0, bc or 0.0), 0, 36, 1)
        d.text("P:{:>6.0f} W".format(pin or 0.0), 0, 48, 1)
        d.show()

    def draw_screen_signals(self, throttle_v, brake_v1, din, warnings, screen_idx=2):
        d = self.d
        d.fill(0); d.text("Signals", 0, 0, 1); self._draw_screen_number(screen_idx)
        d.text("Th:{:>4.2f}V Br:{:>4.2f}V".format(throttle_v or 0.0, brake_v1 or 0.0), 0, 14, 1)
        d.text("DIn: {}".format(int(din or 0)), 0, 28, 1)
        d.text("Warn: {}".format(int(warnings or 0)), 0, 40, 1)
        d.show()
