# axp192.py — Librería mejorada para PMIC AXP192 (T-PCIE v1.1)
# Compatible con ESP32 / MicroPython
# Incluye: snapshot/rollback persistente, lectura de ADC, y modo debug

from machine import I2C
import time, ujson

AXP192_ADDR = 0x34

# ---- Registros básicos ----
REG_POWER_STATUS       = 0x00
REG_CHARGE_STATUS      = 0x01
REG_DC1_VOLT           = 0x26
REG_DC2_VOLT           = 0x23
REG_DC3_VOLT           = 0x27
REG_LDO23OUT_VOL       = 0x28
REG_PEK_KEY            = 0x36
REG_IRQ_STATUS1        = 0x40
REG_IRQ_ENABLE1        = 0x44
REG_VBUS_CUR_H         = 0x5C
REG_VBUS_CUR_L         = 0x5D
REG_ADC_ENABLE1        = 0x82

ADC1_VBUS_VOLT_BIT     = 0x04
ADC1_VBUS_CUR_BIT      = 0x08
ADC1_BAT_VOLT_BIT      = 0x80
ADC1_BAT_CUR_BIT       = 0x40

# ---- ADC (tensiones de batería y VBUS) ----
REG_VBUS_VOLT_H        = 0x5A
REG_VBUS_VOLT_L        = 0x5B
REG_VBAT_VOLT_H        = 0x78
REG_VBAT_VOLT_L        = 0x79
REG_BAT_CHG_CUR_H      = 0x7A
REG_BAT_CHG_CUR_L      = 0x7B
REG_BAT_DISCHG_CUR_H   = 0x7C
REG_BAT_DISCHG_CUR_L   = 0x7D

class AXP192:
    def __init__(self, i2c):
        self.i2c = i2c
        self.addr = AXP192_ADDR
        self._snapshot = None
        self._adc_ready = False
        try:
            self.enable_vbus_adc(True)
            self.enable_battery_adc(True)
            self._adc_ready = True
        except Exception as exc:
            print("[AXP192] ADC enable failed:", exc)

    # ======= Básicos =======
    def read8(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def write8(self, reg, val):
        self.i2c.writeto_mem(self.addr, reg, bytes([val]))

    # ======= Snapshot / Rollback =======
    def snapshot(self):
        self._snapshot = [self.read8(r) for r in range(0x00, 0xFF)]
        print("Snapshot guardado ({} bytes)".format(len(self._snapshot)))

    def rollback(self):
        if not self._snapshot:
            print("No hay snapshot previo.")
            return
        for r, val in enumerate(self._snapshot):
            self.write8(r, val)
        print("Rollback completado.")

    def save_snapshot_to_file(self, filename="axp192_backup.json"):
        if not self._snapshot:
            print("No hay snapshot en RAM, ejecuta snapshot() primero.")
            return
        with open(filename, "w") as f:
            ujson.dump(self._snapshot, f)
        print("Snapshot guardado en", filename)

    def load_snapshot_from_file(self, filename="axp192_backup.json"):
        try:
            with open(filename, "r") as f:
                self._snapshot = ujson.load(f)
            print("Snapshot restaurado desde", filename)
        except Exception as e:
            print("Error al cargar snapshot:", e)

    # ======= Voltajes principales =======
    def get_voltage(self, reg, step_mV, offset_mV=700):
        val = self.read8(reg)
        return offset_mV + val * step_mV

    def show_outputs(self):
        print("---- AXP192 Salidas ----")
        print("DC1  =", self.get_voltage(REG_DC1_VOLT, 25), "mV")
        print("DC2  =", self.get_voltage(REG_DC2_VOLT, 25), "mV")
        print("DC3  =", self.get_voltage(REG_DC3_VOLT, 25), "mV")
        print("LDO2/3 =", self.get_voltage(REG_LDO23OUT_VOL, 100, 700), "mV")

    # ======= Lectura de ADC =======
    def read_vbus_voltage(self):
        """Lee tensión del puerto VBUS (en mV)"""
        raw = self._read12(REG_VBUS_VOLT_H, REG_VBUS_VOLT_L)
        return raw * 1.7  # según datasheet AXP192 (1 bit = 1.7 mV)

    def read_vbat_voltage(self):
        """Lee tensión de la batería (en mV)"""
        raw = self._read12(REG_VBAT_VOLT_H, REG_VBAT_VOLT_L)
        return raw * 1.1  # 1 bit = 1.1 mV

    def _read12(self, reg_h, reg_l):
        high = self.read8(reg_h)
        low = self.read8(reg_l)
        return (high << 4) | (low & 0x0F)

    def _set_adc_bits(self, mask, enable):
        val = self.read8(REG_ADC_ENABLE1)
        if enable:
            val |= mask
        else:
            val &= ~mask
        self.write8(REG_ADC_ENABLE1, val)

    def enable_vbus_adc(self, enable=True):
        """Toggle VBUS voltage/current ADC channels (register 0x82)."""
        self._set_adc_bits(ADC1_VBUS_VOLT_BIT | ADC1_VBUS_CUR_BIT, enable)

    def enable_battery_adc(self, enable=True):
        """Toggle battery voltage/current ADC channels (register 0x82)."""
        self._set_adc_bits(ADC1_BAT_VOLT_BIT | ADC1_BAT_CUR_BIT, enable)

    def read_vbus_current(self):
        """Corriente de entrada por VBUS (en mA)."""
        raw = self._read12(REG_VBUS_CUR_H, REG_VBUS_CUR_L)
        return raw * 0.375  # 1 bit = 0.375 mA

    def read_battery_charge_current(self):
        """Corriente de carga hacia la batería (en mA)."""
        high = self.read8(REG_BAT_CHG_CUR_H)
        low = self.read8(REG_BAT_CHG_CUR_L)
        raw = (high << 5) | (low & 0x1F)
        return raw * 0.5  # 1 bit = 0.5 mA

    def read_battery_discharge_current(self):
        """Corriente de descarga suministrada por la batería (en mA)."""
        high = self.read8(REG_BAT_DISCHG_CUR_H)
        low = self.read8(REG_BAT_DISCHG_CUR_L)
        raw = (high << 5) | (low & 0x1F)
        return raw * 0.5  # 1 bit = 0.5 mA

    # ======= Botón PWRON =======
    def configure_pwron(self, long_press_ms=1500, short_press_ms=128):
        """Configura tiempos de pulsación del botón PWRON"""
        val = self.read8(REG_PEK_KEY)
        long_sel = {1000:0, 1500:1, 2000:2, 2500:3}.get(long_press_ms, 1)
        short_sel = {64:0, 128:1, 256:2, 512:3}.get(short_press_ms, 1)
        val = (val & 0x3C) | (long_sel << 6) | (short_sel << 2)
        self.write8(REG_PEK_KEY, val)
        print("Botón PWRON: long={}ms short={}ms".format(long_press_ms, short_press_ms))

    def read_pwron_status(self):
        """Detecta pulsación del botón (bit 5 en IRQ_STATUS1)"""
        irq = self.read8(REG_IRQ_STATUS1)
        pressed = bool(irq & 0x20)
        if pressed:
            self.write8(REG_IRQ_STATUS1, 0x20)  # limpiar flag
        return pressed

    # ======= Modo debug =======
    def debug_loop(self, delay_s=0.5):
        """Loop de depuración: muestra actividad y tensiones"""
        print("Entrando en debug_loop (Ctrl+C para salir)")
        while True:
            try:
                vbus = self.read_vbus_voltage()
                vbat = self.read_vbat_voltage()
                print("VBUS={:.0f} mV  VBAT={:.0f} mV".format(vbus, vbat))
                if self.read_pwron_status():
                    print("Botón PWRON presionado!")
                time.sleep(delay_s)
            except KeyboardInterrupt:
                print("\n[SALIDA de debug_loop]")
                break

    # ======= Estado de energía =======
    def get_power_status(self):
        val = self.read8(REG_POWER_STATUS)
        return {
            "acin_present": bool(val & 0x80),
            "acin_usable": bool(val & 0x40),
            "vbus_present": bool(val & 0x20),
            "vbus_usable": bool(val & 0x10),
            "battery_present": bool(val & 0x08),
            "battery_active": bool(val & 0x04),
        }

    def get_charge_status(self):
        val = self.read8(REG_CHARGE_STATUS)
        return {
            "battery_overtemp": bool(val & 0x80),
            "charging": bool(val & 0x40),
            "charge_complete": bool(val & 0x20),
            "vbus_low": bool(val & 0x10),
        }
