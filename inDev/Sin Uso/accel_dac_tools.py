# accel_dac_tools.py  (fix)
from machine import Pin, I2C, ADC
from time import sleep_ms
from HW import make_i2c

ACC_ADDR  = 0x1C
DAC0_ADDR = 0x60
DAC1_ADDR = 0x61

CTRL_REG1 = 0x2A
CTRL_REG3 = 0x2C
CTRL_REG4 = 0x2D
CTRL_REG5 = 0x2E

def set_input_pins(int1_pin=32, int2_pin=14):
    p1 = Pin(int1_pin, Pin.IN)
    p2 = Pin(int2_pin, Pin.IN)
    return p1, p2

_adc32 = None
def make_adc32(atten_11db=True):
    global _adc32
    if _adc32 is None:
        _adc32 = ADC(Pin(32))
        if atten_11db and hasattr(ADC, 'ATTN_11DB'):
            _adc32.atten(ADC.ATTN_11DB)
    return _adc32

def read_adc32_raw(samples=4):
    adc = make_adc32()
    tot = 0
    for _ in range(max(1, int(samples))):
        tot += adc.read()
        sleep_ms(2)
    return tot // max(1, int(samples))

def read_adc32_volts(vref=3.3, samples=4):
    raw = read_adc32_raw(samples)
    return raw * float(vref) / 4095.0

def _r(i2c, reg, n=1, addr=ACC_ADDR):
    return i2c.readfrom_mem(addr, reg, n)

def _w(i2c, reg, val, addr=ACC_ADDR):
    i2c.writeto_mem(addr, reg, bytes([val & 0xFF]))

def mma8452q_set_lines_floating(i2c=None, addr=ACC_ADDR):
    if i2c is None:
        i2c = make_i2c()
    v1 = _r(i2c, CTRL_REG1, 1, addr)[0]
    _w(i2c, CTRL_REG1, v1 & ~0x01, addr)
    _w(i2c, CTRL_REG3, 0x40, addr)
    _w(i2c, CTRL_REG4, 0x00, addr)
    _w(i2c, CTRL_REG5, 0x00, addr)
    _w(i2c, CTRL_REG1, v1 | 0x01, addr)

def _dac_write_register(i2c, addr, code):
    code = max(0, min(4095, int(code)))
    hi = (code >> 4) & 0xFF
    lo = (code & 0x0F) << 4
    i2c.writeto(addr, bytes([0x40, hi, lo]))

def _dac_write_fast(i2c, addr, code):
    code = max(0, min(4095, int(code)))
    b0 = (code >> 8) & 0x0F  # PD=00
    b1 = code & 0xFF
    i2c.writeto(addr, bytes([b0, b1]))

def dac_write_code(i2c, addr, code, mode='reg'):
    if mode == 'fast':
        _dac_write_fast(i2c, addr, code)
    else:
        _dac_write_register(i2c, addr, code)

def write_volts(vout, addr=DAC0_ADDR, vref=3.3, mode='reg'):
    i2c = make_i2c()
    vout = max(0.0, min(float(vout), float(vref)))
    code = int(4095 * vout / float(vref))
    dac_write_code(i2c, addr, code, mode=mode)
    return code

def set_both_volts(v0, v1, vref=3.3, mode='reg'):
    i2c = make_i2c()
    def _code(v):
        v = max(0.0, min(float(v), float(vref)))
        return int(4095 * v / float(vref))
    dac_write_code(i2c, DAC0_ADDR, _code(v0), mode=mode)
    dac_write_code(i2c, DAC1_ADDR, _code(v1), mode=mode)

def dac_zero_both(i2c=None, mode='reg'):
    if i2c is None:
        i2c = make_i2c()
    dac_write_code(i2c, DAC0_ADDR, 0, mode=mode)
    dac_write_code(i2c, DAC1_ADDR, 0, mode=mode)

def dac_read_code(i2c, addr):
    b = i2c.readfrom(addr, 5)
    return ((b[1] << 4) | (b[2] >> 4)) & 0x0FFF

def dac_read_volts(i2c, addr, vref=3.3):
    code = dac_read_code(i2c, addr)
    return code * float(vref) / 4095.0

def setup_accel_dacs(int1_pin=32, int2_pin=14, set_adc32=True):
    i2c = make_i2c()
    pins = {}
    pins['int1'], pins['int2'] = set_input_pins(int1_pin, int2_pin)
    mma8452q_set_lines_floating(i2c)
    dac_zero_both(i2c, mode='reg')
    if set_adc32:
        pins['adc32'] = make_adc32()
    return pins

def status(vref=3.3):
    i2c = make_i2c()
    try:
        c0 = dac_read_code(i2c, DAC0_ADDR); v0 = c0 * float(vref) / 4095.0
    except Exception:
        c0 = None; v0 = None
    try:
        c1 = dac_read_code(i2c, DAC1_ADDR); v1 = c1 * float(vref) / 4095.0
    except Exception:
        c1 = None; v1 = None
    p1 = Pin(32, Pin.IN); p2 = Pin(14, Pin.IN)
    print("DAC0:", c0, "V≈", v0, "| DAC1:", c1, "V≈", v1)
    print("INT1(GPIO32)=", p1.value(), " INT2(GPIO14)=", p2.value())

def check_adc32_follows_dac(addr=DAC0_ADDR, samples=(0.0, 1.0, 2.0), vref=3.3, tol=0.2, mode='reg'):
    res = []
    for v in samples:
        write_volts(v, addr=addr, vref=vref, mode=mode)
        sleep_ms(20)
        meas = read_adc32_volts(vref=vref, samples=8)
        ok = abs(meas - v) <= float(tol)
        res.append((v, meas, ok))
    return res
