from time import sleep_ms
from machine import UART
from HW import PR_UART_RX, PR_UART_TX
from phaserunner import Phaserunner  # usa PR_REGISTERS de registers.py

# Campos que querés ver en pantalla
FIELDS = [
    "battery_current",
    "motor_input_power",
    "vehicle_speed",
    "controller_temp",
    "motor_temp",
    "motor_rpm",
    "battery_voltage",
    "throttle_voltage",
    "brake_voltage_1",
    "digital_inputs",
    "warnings",
]

# UART según tu HW.py
uart = UART(1, baudrate=115200, tx=PR_UART_RX, rx=PR_UART_TX, timeout=300)
pr = Phaserunner(uart)

while True:
    line = []
    for name in FIELDS:
        try:
            val = pr.read_value(name)
            # manejo especial de bitmaps
            if name in ("digital_inputs", "warnings"):
                # mostrar en decimal y hex
                s = "{}={} (0x{:X})".format(name, int(val), int(val))
            else:
                s = "{}={:.3f}".format(name, val)
        except Exception as e:
            s = "{}=ERR".format(name)
        line.append(s)

    print(" | ".join(line))
    sleep_ms(500)
