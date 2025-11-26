"""Pin map for the PR-offload ESP32 (WROVER module)."""

# ── UART1: Phaserunner Modbus link (ESP32 perspective)
PR_UART_ID = 1
PR_UART_TX = 25  # Drives the Phaserunner RX line
PR_UART_RX = 27  # Reads from the Phaserunner TX line
PR_UART_BAUD = 115200

# ── UART2: bridge to the main ESP32 controller
MAIN_UART_ID = 2
MAIN_UART_TX = 4   # Connect this pin to the main ESP's RX
MAIN_UART_RX = 5   # Connect this pin to the main ESP's TX
MAIN_UART_BAUD = 115200