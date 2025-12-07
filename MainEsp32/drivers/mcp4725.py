"""Lightweight MCP4725 driver used by the eBike control loops."""

from machine import I2C

BUS_ADDRESS = [0x62, 0x63]
POWER_DOWN_MODE = {"Off": 0, "1k": 1, "100k": 2, "500k": 3}


class MCP4725:
    def __init__(self, i2c: I2C, address=BUS_ADDRESS[0]):
        self.i2c = i2c
        self.address = address
        self._write_buffer = bytearray(2)

    def write(self, value: int) -> bool:
        value = max(0, value & 0xFFF)
        self._write_buffer[0] = (value >> 8) & 0xFF
        self._write_buffer[1] = value & 0xFF
        return self.i2c.writeto(self.address, self._write_buffer) == 2

    def read(self):
        buf = bytearray(5)
        if self.i2c.readfrom_into(self.address, buf) != 5:
            return None
        eeprom_write_busy = (buf[0] & 0x80) == 0
        power_down = self._power_down_key((buf[0] >> 1) & 0x03)
        value = ((buf[1] << 8) | buf[2]) >> 4
        eeprom_power_down = self._power_down_key((buf[3] >> 5) & 0x03)
        eeprom_value = ((buf[3] & 0x0F) << 8) | buf[4]
        return (eeprom_write_busy, power_down, value, eeprom_power_down, eeprom_value)

    def config(self, power_down="Off", value=0, eeprom=False) -> bool:
        conf = 0x40 | (POWER_DOWN_MODE[power_down] << 1)
        if eeprom:
            conf |= 0x60
        value = max(0, value & 0xFFF)
        payload = bytearray((conf, value >> 4, (value & 0x0F) << 4))
        return self.i2c.writeto(self.address, payload) == 3

    def _power_down_key(self, value: int) -> str:
        for key, item in POWER_DOWN_MODE.items():
            if item == value:
                return key
        return "Off"
