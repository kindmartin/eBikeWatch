"""Pin map for the PR-offload ESP32 (WROVER module)."""

# ── UART1: Phaserunner Modbus link (ESP32 perspective)
PR_UART_ID = 1
PR_UART_TX = 25  # Drives the Phaserunner RX line
PR_UART_RX = 27  # Reads from the Phaserunner TX line
PR_UART_BAUD = 115200

# ── UART2: bridge to the main ESP32 controller
MAIN_UART_ID = 2
MAIN_UART_TX = 15  # main ESP's RX (GPIO 15)
MAIN_UART_RX = 4   # main ESP's TX (GPIO 13) / wake input
MAIN_UART_BAUD = 115200

# Pins that can wake the offload MCU from deep sleep.
# Dedicated wake wire: main ESP32 GPIO25 -> 10k -> offload GPIO32 (RTC capable).
WAKE_PIN = 32
WAKE_PINS = (WAKE_PIN,)

"""
Wiring (ESP32 to ESP32):
- Main ESP32 GPIO 15 (UART RX) -> ESP32 GPIO 15 (UART TX)
- Main ESP32 GPIO 13 (UART TX) -> ESP32 GPIO 4 (UART RX)

"""