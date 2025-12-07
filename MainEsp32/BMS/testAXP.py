from machine import I2C, Pin
from drivers.axp192 import AXP192
import time

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
pmic = AXP192(i2c)

pmic.snapshot()
pmic.save_snapshot_to_file()
pmic.show_outputs()

# Leer tensiones
print("VBUS =", pmic.read_vbus_voltage(), "mV")
print("VBAT =", pmic.read_vbat_voltage(), "mV")

# Iniciar modo debug
pmic.debug_loop(1.0)   # actualiza cada 1 segundo
