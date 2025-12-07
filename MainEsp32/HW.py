
# HW.py
# Mapa de pines y utilidades para ESP32 (LilyGO T-PCIE v1.1) con MicroPython.

import machine  # type: ignore

# ── UART para Phaserunner (Modbus) y puente PR-offload
PR_UART_ID = 1
PR_UART_RX = 15
PR_UART_TX = 13
PR_UART_BAUD = 115200

"""
Wiring (ESP32 to ESP32):
- Main ESP32 GPIO 15 (UART RX) -> ESP32 GPIO 15 (UART TX)
- Main ESP32 GPIO 13 (UART TX) -> ESP32 GPIO 4 (UART RX)

"""

# ── SIM7600 (reservados, no usar)
SIM_PINS = (25, 26, 27, 4, 36)

# ── GPIO dedicado para despertar al PR-offload (lleva a ESP32 offload GPIO32)
PR_OFFLOAD_WAKE_PIN = 25

# ── ADC para 0-3V (Acelerador / Freno)
# Nota HW T-PCIE v1.1: GPIO33 comparte pista con RI del SIM7600. Solo usarlo para
# acelerador/fuente analógica si se aísla físicamente (buffer/transistor) el módem.
ADC_THROTTLE_PIN = 33   # 0..3 V
ADC_BRAKE_PIN    = 34   # 0..3 V

# ── Pin dedicado para wake-up principal (GPIO33 / ADC throttle)
MAIN_WAKE_PIN = 33

# ── Contador de pulsos de rueda
TRIP_COUNTER_ID = 0
TRIP_COUNTER_PIN = 32
TRIP_COUNTER_FILTER_NS = 50_000
TRIP_COUNTER_EDGE = "RISING"  # valor traducido a machine.Counter.<edge>
TRIP_COUNTER_INTERVAL_MS = 1000

# ── Botonería
PAGE_BTN_PIN = 0        # activo-bajo, pull-up EXTERNO
UPDOWN_ADC_PIN = 39     # 3.0V idle, 0V UP, intermedio DOWN (medir)

# ── I2C bus
I2C_ID = 0
I2C_SCL = 22
I2C_SDA = 21

# ----- DAC MCP4725 helpers -----
DAC0_ADDR = 0x60  # Throttle DAC
DAC1_ADDR = 0x61  # Brake DAC

# ----- 1.69 inch 240x280 ST7789 LCD
MOSI_PIN = 23
# MISO_PIN = 14
MISO_PIN = None
SCK_PIN = 19
CS_PIN = 18
DC_PIN = 5
RST_PIN = 2
BL_PIN = 12


SPI_ID = 2
SPI_BAUDRATE = 20_000_000

# ── Utilidades

def make_i2c(freq=400_000):
    return machine.I2C(I2C_ID, scl=machine.Pin(I2C_SCL), sda=machine.Pin(I2C_SDA), freq=freq)

def make_adc(pin_num, atten=machine.ADC.ATTN_6DB, width=machine.ADC.WIDTH_12BIT):
    adc = machine.ADC(machine.Pin(pin_num))
    try:
        adc.atten(atten)
        adc.width(width)
    except Exception:
        pass
    return adc

def make_input(pin_num, pull=None):
    # Nota: GPIO34/35/36/39 no tienen pull interno. GPIO0 tiene pull externo .
    return machine.Pin(pin_num, machine.Pin.IN, pull) if pull else machine.Pin(pin_num, machine.Pin.IN)

# ----- DAC MCP4725 helpers -----

def _dac_write_register(i2c, addr, code):
    code = max(0, min(4095, int(code)))
    hi = (code >> 4) & 0xFF
    lo = (code & 0x0F) << 4
    i2c.writeto(addr, bytes([0x40, hi, lo]))

def set_dac_volts(i2c, addr, volts, vref=3.3):
    v = max(0.0, min(float(volts), float(vref)))
    code = int(4095 * v / float(vref))
    _dac_write_register(i2c, addr, code)
    return code

def dacs_zero_both(i2c):
    _dac_write_register(i2c, DAC0_ADDR, 0)
    _dac_write_register(i2c, DAC1_ADDR, 0)

def adc_read_volts(adc, vref=3.3):
    try:
        return (adc.read() * (float(vref) / 4095.0))
    except Exception:
        return 0.0

def make_output(pin_num, *, value=1):
    pin = machine.Pin(pin_num, machine.Pin.OUT)
    pin.value(value)
    return pin