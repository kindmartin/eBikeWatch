# phaserunner.py
from umodbus_simple import ModbusRTUMaster
from registers import PR_REGISTERS

class Phaserunner:
    def __init__(self, uart, slave_id=1):
        self.master = ModbusRTUMaster(uart)
        self.slave_id = slave_id

    def read_value(self, name):
        """Leer cualquier parámetro por nombre"""
        if name not in PR_REGISTERS:
            raise ValueError("Registro desconocido: {}".format(name))

        reg = PR_REGISTERS[name]
        raw = self.master.read_holding_registers(self.slave_id, reg["addr"], 1)[0]

        # signed conversion
        if reg["signed"] and raw > 0x7FFF:
            raw -= 0x10000

        return raw / reg["scale"]

    def get_all(self):
        """Leer todos los registros definidos y devolver dict con (valor, unidad)"""
        results = {}
        for name, reg in PR_REGISTERS.items():
            try:
                val = self.read_value(name)
                results[name] = (val, reg["unit"])
            except Exception:
                results[name] = (None, reg["unit"])
        return results
