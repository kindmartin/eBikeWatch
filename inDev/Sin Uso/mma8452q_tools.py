# mma8452q_tools.py
ACC_ADDR   = 0x1C
CTRL_REG1  = 0x2A
CTRL_REG3  = 0x2C
CTRL_REG4  = 0x2D
CTRL_REG5  = 0x2E
TRANSIENT_CFG   = 0x1D
TRANSIENT_THS   = 0x1F
TRANSIENT_COUNT = 0x20
HP_FILTER_CUTOFF= 0x0F

def _r(i2c, reg, n=1, addr=ACC_ADDR):
    return i2c.readfrom_mem(addr, reg, n)

def _w(i2c, reg, val, addr=ACC_ADDR):
    return i2c.writeto_mem(addr, reg, bytes([val & 0xFF]))

def read_regs(i2c, reg, n, addr=ACC_ADDR):
    return list(_r(i2c, reg, n, addr))

def set_ints_floating(i2c):
    v1 = _r(i2c, CTRL_REG1, 1)[0]
    _w(i2c, CTRL_REG1, v1 & ~0x01)
    _w(i2c, CTRL_REG3, 0x01)
    _w(i2c, CTRL_REG4, 0x00)
    _w(i2c, CTRL_REG5, 0x00)
    _w(i2c, CTRL_REG1, v1 | 0x01)

def config_motion_wake(i2c, sens_mg=150, debounce=4, route_to_int=1):
    v1 = _r(i2c, CTRL_REG1, 1)[0]
    _w(i2c, CTRL_REG1, v1 & ~0x01)
    _w(i2c, CTRL_REG3, 0x00)
    try:
        prev = _r(i2c, HP_FILTER_CUTOFF, 1)[0]
        _w(i2c, HP_FILTER_CUTOFF, prev | 0x10)
    except Exception:
        pass
    _w(i2c, TRANSIENT_CFG, 0xF8)
    ths_codes = int(max(1, min(127, sens_mg / 63.0)))
    _w(i2c, TRANSIENT_THS, ths_codes & 0x7F)
    _w(i2c, TRANSIENT_COUNT, int(max(0, min(255, debounce))))
    _w(i2c, CTRL_REG4, 0x20)
    if route_to_int == 1:
        _w(i2c, CTRL_REG5, 0x20)
    else:
        _w(i2c, CTRL_REG5, 0x00)
    _w(i2c, CTRL_REG1, v1 | 0x01)
