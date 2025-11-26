"""Minimal Modbus RTU helper used by the Phaserunner interface."""

import struct
from time import sleep_ms, ticks_diff, ticks_ms

class ModbusRTUMaster:
    def __init__(self, uart, timeout_ms=120):
        self.uart = uart
        try:
            self.timeout_ms = max(10, int(timeout_ms))
        except Exception:
            self.timeout_ms = 120

    def _crc16(self, data):
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for _ in range(8):
                if (crc & 1) != 0:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return struct.pack("<H", crc)

    def _read_exact(self, expected_len):
        if expected_len <= 0:
            return bytearray()
        buf = bytearray()
        start = ticks_ms()
        while len(buf) < expected_len:
            chunk = self.uart.read(expected_len - len(buf))
            if chunk:
                buf.extend(chunk)
                continue
            if ticks_diff(ticks_ms(), start) >= self.timeout_ms:
                raise Exception("Modbus timeout")
            sleep_ms(1)
        return buf

    def read_holding_registers(self, slave_addr, reg_addr, count):
        if count <= 0:
            return []

        pdu = bytearray([3, reg_addr >> 8, reg_addr & 0xFF, count >> 8, count & 0xFF])
        adu = bytearray([slave_addr]) + pdu
        adu += self._crc16(adu)

        self.uart.write(adu)

        expected_len = 3 + (count * 2) + 2
        resp = self._read_exact(expected_len)

        if self._crc16(resp[:-2]) != resp[-2:]:
            raise Exception("CRC error")

        if resp[0] != slave_addr or resp[1] != 3:
            raise Exception("Invalid response")

        length = resp[2]
        if length != count * 2:
            raise Exception("Unexpected payload length")
        data = resp[3 : 3 + length]

        regs = []
        for i in range(0, len(data), 2):
            regs.append((data[i] << 8) + data[i + 1])

        return regs
