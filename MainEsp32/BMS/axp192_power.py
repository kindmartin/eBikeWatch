# axp192_power.py — AXP192 PMU helper (ESP32 + MicroPython + uasyncio)
# V1.0 — eventos + IRQ física + ADC + API sync

from machine import I2C, Pin
import uasyncio as asyncio

AXP192_ADDR = 0x34

# ---- Registros usados ----
REG_POWER_STATUS   = 0x00
REG_CHARGE_STATUS  = 0x01
REG_EXTEN_DCDC2    = 0x10        # EXTEN/DCDC2 ctrl (no lo tocamos por defecto)
REG_DCDC13_LDO23   = 0x12        # en/ctrl DCDC1/3 y LDO2/3
REG_IRQ_STATUS1    = 0x40        # write-1-to-clear
REG_IRQ_ENABLE1    = 0x44        # bit5 = PowerKey IRQ enable
REG_ADC_ENABLE1    = 0x82
REG_ADC_ENABLE2    = 0x83
REG_ADC_RATE       = 0x84
REG_VBUS_V_H       = 0x5A
REG_VBUS_V_L       = 0x5B
REG_VBAT_V_H       = 0x78
REG_VBAT_V_L       = 0x79

def _r8(i2c, a): return i2c.readfrom_mem(AXP192_ADDR, a, 1)[0]
def _w8(i2c, a, v): i2c.writeto_mem(AXP192_ADDR, a, bytes([v & 0xFF]))

def _vbus_mv(i2c):
    h, l = _r8(i2c, REG_VBUS_V_H), _r8(i2c, REG_VBUS_V_L)
    return ((h << 4) | (l & 0x0F)) * 1.7  # mV por bit

def _vbat_mv(i2c):
    h, l = _r8(i2c, REG_VBAT_V_H), _r8(i2c, REG_VBAT_V_L)
    return ((h << 4) | (l & 0x0F)) * 1.1

class AXP192PMU:
    """
    Uso típico:
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        pmu = AXP192PMU(i2c)
        pmu.on_event(lambda e: print("[EVT]", e))
        asyncio.run(pmu.start(period=1.0))
    Eventos posibles:
        'PWRON_PRESS', 'VBUS_ON', 'VBUS_OFF', 'VBAT_ON', 'VBAT_OFF', 'VBAT_LOW'
    """
    def __init__(self, i2c: I2C, irq_pin: int = 35, vbat_low_mv: int = 3400):
        self.i2c = i2c
        self.irq_pin = Pin(irq_pin, Pin.IN)
        self.vbat_low_mv = vbat_low_mv

        self._callbacks = []
        self._queue = asyncio.Queue()
        self._flag = asyncio.ThreadSafeFlag()   # notifica desde ISR
        self._tasks = []
        self._running = False

        # estado actual (mV)
        self.vbus = 0.0
        self.vbat = 0.0
        self.vbus_present = False
        self.vbat_present = False

    # ---------- API pública (sync) ----------
    def read_vbus(self) -> float:
        return _vbus_mv(self.i2c)

    def read_vbat(self) -> float:
        return _vbat_mv(self.i2c)

    def battery_percent(self) -> int:
        # Mapeo simple 3.30–4.20V → 0–100% (ajusta si querés otra curva)
        v = self.vbat if self.vbat else self.read_vbat()
        pct = int(max(0, min(100, round((v - 3300) / (4200 - 3300) * 100))))
        return pct

    def on_event(self, cb):
        """Registra un callback: cb(evento_str)"""
        self._callbacks.append(cb)

    async def wait_event(self, name: str = None, timeout: float | None = None):
        """Espera el próximo evento (o uno con nombre concreto)."""
        if timeout is None:
            while True:
                evt = await self._queue.get()
                if (name is None) or (evt == name):
                    return evt
        else:
            try:
                while True:
                    evt = await asyncio.wait_for(self._queue.get(), timeout)
                    if (name is None) or (evt == name):
                        return evt
            except asyncio.TimeoutError:
                return None

    # ---------- ciclo de vida ----------
    async def start(self, period: float = 1.0):
        """Configura PMIC, activa IRQ, lanza monitor y manejador."""
        if self._running:
            return
        # Habilitar ADCs y rate
        _w8(self.i2c, REG_ADC_ENABLE1, 0xFF)
        _w8(self.i2c, REG_ADC_ENABLE2, 0xFF)
        _w8(self.i2c, REG_ADC_RATE,   0xF0)   # imprescindible para VBAT

        # Habilitar IRQ de PowerKey (bit5)
        _w8(self.i2c, REG_IRQ_ENABLE1, 0x20)
        # Limpiar flags previos
        _w8(self.i2c, REG_IRQ_STATUS1, 0xFF)

        # ISR física (no tocar I2C acá)
        def _isr(_):
            self._flag.set()
        self.irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=_isr)

        # Estado inicial
        self._update_measurements(emit_changes=True)

        # Lanzar tareas
        t1 = asyncio.create_task(self._irq_task())
        t2 = asyncio.create_task(self._monitor_task(period))
        self._tasks = [t1, t2]
        self._running = True
        return self

    async def stop(self):
        for t in self._tasks:
            t.cancel()
            try:
                await t
            except:
                pass
        self._tasks.clear()
        self._running = False
        # Deshabilitar IRQ si querés:
        # _w8(self.i2c, REG_IRQ_ENABLE1, 0x00)

    # ---------- internos ----------
    def _emit(self, evt: str):
        # encola y dispara callbacks
        try:
            self._queue.put_nowait(evt)
        except:
            pass
        for cb in self._callbacks:
            try:
                cb(evt)
            except Exception as e:
                # no romper por un callback
                print("[AXP192PMU] callback error:", e)

    def _update_measurements(self, emit_changes=False):
        vbus = _vbus_mv(self.i2c)
        vbat = _vbat_mv(self.i2c)

        # Presencia se decide con umbral >100 mV
        vbus_present = vbus > 100
        vbat_present = vbat > 100

        if emit_changes:
            if vbus_present != self.vbus_present:
                self._emit("VBUS_ON" if vbus_present else "VBUS_OFF")
            if vbat_present != self.vbat_present:
                self._emit("VBAT_ON" if vbat_present else "VBAT_OFF")
            if vbat_present and (vbat < self.vbat_low_mv) and (self.vbat >= self.vbat_low_mv or not self.vbat_present):
                self._emit("VBAT_LOW")

        self.vbus, self.vbat = vbus, vbat
        self.vbus_present, self.vbat_present = vbus_present, vbat_present

    async def _monitor_task(self, period: float):
        print("[AXP192] monitor_task ON (period =", period, "s)")
        try:
            while True:
                self._update_measurements(emit_changes=True)
                await asyncio.sleep(period)
        except asyncio.CancelledError:
            print("[AXP192] monitor_task OFF")

    async def _irq_task(self):
        print("[AXP192] irq_task ON (GPIO{})".format(self.irq_pin.id()))
        try:
            while True:
                await self._flag.wait()  # disparado por ISR física
                # leer/limpiar flags en contexto no-ISR
                irq = _r8(self.i2c, REG_IRQ_STATUS1)
                if irq:
                    # limpiar todo lo que vino
                    _w8(self.i2c, REG_IRQ_STATUS1, irq)
                    # bit5 = power key event (short/long según config de PEK)
                    if irq & 0x20:
                        self._emit("PWRON_PRESS")
        except asyncio.CancelledError:
            print("[AXP192] irq_task OFF")

    # ---------- utilidades opcionales ----------
    def outputs_state(self):
        """Devuelve tupla con registros de control de salidas (debug)."""
        return (_r8(self.i2c, REG_EXTEN_DCDC2), _r8(self.i2c, REG_DCDC13_LDO23))

    def soft_disable_ldo23(self):
        """Ejemplo: apaga LDO2/3 (no toca DCDC)."""
        v = _r8(self.i2c, REG_DCDC13_LDO23)
        # bits LDO2/3 enable suelen ser 2 y 3 en 0x12 (depende board)
        _w8(self.i2c, REG_DCDC13_LDO23, v & ~((1<<2) | (1<<3)))

    # NOTA: un "apagado total" por registro depende de cómo tu placa usa DCDC/EXTEN.
    # Para apagar el sistema preferí usar el botón (long press) o gestionar módulos
    # (pantallas, radios) y entrar a deep-sleep del ESP32.
