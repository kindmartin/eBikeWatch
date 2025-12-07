    # pr_uart.py
# Utilidades UART para Phaserunner usando pines de HW.py.
# Permite crear el puerto y probar automáticamente ambas asignaciones TX/RX.
#
# API principal:
#   - make_uart(mapping='A', baudrate=115200, parity=None, stop=1, timeout=0, timeout_char=0)
#       mapping 'A': tx=HW.PR_UART_TX, rx=HW.PR_UART_RX
#   - reader_task(uart, label='A', silence_ms=20, each_ms=5)
#       traza paquetes separados por silencio (HEX + conteo)
#   - quick_probe(seconds=3, register='battery_voltage', ...)
#       realiza lecturas Modbus en el mapping configurado y devuelve (mapping, lecturas_ok, último_valor)
#
import uasyncio as asyncio
import machine, time
import HW
from .phaserunner import Phaserunner

def make_uart(mapping='A', baudrate=115200, bits=8, parity=None, stop=1, timeout=0, timeout_char=0):
    if mapping != 'A':
        print("[PR][UART] mapping '{}' no longer supported, defaulting to 'A'".format(mapping))
    tx_pin = HW.PR_UART_TX
    rx_pin = HW.PR_UART_RX
    uart = machine.UART(1,
                        baudrate=baudrate, bits=bits, parity=parity, stop=stop,
                        timeout=timeout, timeout_char=timeout_char,
                        tx=machine.Pin(tx_pin), rx=machine.Pin(rx_pin))
    return uart, tx_pin, rx_pin

def _hexline(buf):
    return ' '.join('{:02X}'.format(b) for b in buf)

async def reader_task(uart, label='A', silence_ms=20, each_ms=5, verbose=1):
    pkt = bytearray()
    last = time.ticks_ms()
    total = 0
    pkts = 0
    print("[PR][{}] RX start @{} baud (TX={}, RX={})".format(
        label, uart.baudrate(), uart.tx, uart.rx) if hasattr(uart,'tx') else "[PR][{}] RX start".format(label))
    while True:
        n = uart.any()
        now = time.ticks_ms()
        if n:
            data = uart.read(n) or b''
            if data:
                pkt.extend(data)
                total += len(data)
                last = now
        else:
            if pkt and time.ticks_diff(now, last) >= silence_ms:
                pkts += 1
                if verbose:
                    print("[PR][{}][PKT {:04d}] {}".format(label, pkts, _hexline(pkt)))
                pkt = bytearray()
        await asyncio.sleep_ms(each_ms)

async def _listen_for(uart, seconds=3):
    t0 = time.ticks_ms()
    total = 0
    last = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < int(seconds*1000):
        n = uart.any()
        if n:
            data = uart.read(n) or b''
            total += len(data)
            last = time.ticks_ms()
        await asyncio.sleep_ms(5)
    return total, time.ticks_diff(time.ticks_ms(), t0)

async def quick_probe(seconds=3, register="battery_voltage", baudrate=115200, parity=None, stop=1):
    """Realiza lecturas Modbus rápidas usando el mapping primario 'A'.

    Devuelve una tupla ("A", lecturas_ok, último_valor) o ``None`` si no pudo crear la UART.
    """

    ms_total = int(seconds * 1000)

    try:
        uart, txp, rxp = make_uart('A', baudrate=baudrate, parity=parity, stop=stop)
    except Exception as exc:
        print("[PR][probe] mapping A => error al crear UART: {}".format(exc))
        return None

    print("[PR][probe] mapping A => TX pin {}, RX pin {} — consultando {}s".format(txp, rxp, seconds))

    pr = Phaserunner(uart)
    ok = 0
    last_val = None
    deadline = time.ticks_add(time.ticks_ms(), ms_total)

    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        try:
            val = pr.read_value(register)
            ok += 1
            last_val = val
            print("[PR][probe][A] {} = {:.3f}".format(register, val))
        except Exception as exc:
            print("[PR][probe][A] fallo: {}".format(exc))
        await asyncio.sleep_ms(120)

    try:
        uart.deinit()
    except Exception:
        pass

    return ("A", ok, last_val)
