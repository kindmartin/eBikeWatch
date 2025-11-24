from machine import UART
import struct, time

class ModbusRTUMaster:
    def __init__(self, uart):
        self.uart = uart

    def _crc16(self, data):
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for i in range(8):
                if (crc & 1) != 0:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return struct.pack('<H', crc)

    def read_holding_registers(self, slave_addr, reg_addr, count):
        # Build request PDU
        pdu = bytearray([3, reg_addr >> 8, reg_addr & 0xFF,
                         count >> 8, count & 0xFF])

        # Build ADU
        adu = bytearray([slave_addr]) + pdu
        adu += self._crc16(adu)

        # Enviar
        self.uart.write(adu)

        # Esperar respuesta
        time.sleep_ms(200)
        resp = self.uart.read()
        if not resp:
            raise Exception("No response from slave")

        # Validar CRC
        if self._crc16(resp[:-2]) != resp[-2:]:
            raise Exception("CRC error")

        # Validar dirección y función
        if resp[0] != slave_addr or resp[1] != 3:
            raise Exception("Invalid response")

        length = resp[2]
        data = resp[3:3+length]

        # Decodificar registros (2 bytes cada uno)
        regs = []
        for i in range(0, len(data), 2):
            regs.append((data[i] << 8) + data[i+1])

        return regs