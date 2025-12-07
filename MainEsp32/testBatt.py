"""Quick battery/PMIC probe for LilyGo T-PCIE (AXP192).

The ESP32 filesystem root is the `inDev/` folder, so copy this file and
`drivers/axp192.py` there and run `import testBatt; testBatt.probe()`.
"""

import time
from machine import I2C, Pin
from drivers.axp192 import AXP192

I2C_ID = 0
I2C_SCL_PIN = 22
I2C_SDA_PIN = 21


def _fmt_status(power_status, charge_status):
    status = {}
    if power_status:
        status.update(power_status)
    if charge_status:
        status.update(charge_status)
    flags = []
    if status.get("acin_present"):
        flags.append("AC")
    if status.get("vbus_present"):
        flags.append("VBUS")
    if status.get("battery_present"):
        flags.append("BAT")
    if status.get("charging"):
        flags.append("CHG")
    if status.get("charge_complete"):
        flags.append("FULL")
    if status.get("battery_overtemp"):
        flags.append("HOT")
    if not flags:
        flags.append("IDLE")
    return ",".join(flags)


def probe(delay_s=2.0):
    i2c = I2C(I2C_ID, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))
    pmu = AXP192(i2c)
    print("[testBatt] AXP192 detected at 0x{:02X}".format(pmu.addr))
    print("Press Ctrl+C to stop. Logging every {} s".format(delay_s))
    try:
        while True:
            vbus_v = pmu.read_vbus_voltage() / 1000.0
            vbus_i = pmu.read_vbus_current()
            vbat_v = pmu.read_vbat_voltage() / 1000.0
            ichg = pmu.read_battery_charge_current()
            idis = pmu.read_battery_discharge_current()
            power_status = pmu.get_power_status()
            charge_status = pmu.get_charge_status()
            flags = _fmt_status(power_status, charge_status)
            sys_i = None
            if not power_status.get("battery_present"):
                sys_i = vbus_i
            sys_str = "SYS={:.1f} mA | ".format(sys_i) if sys_i is not None else ""
            print(
                "VBUS={:.2f} V {:.1f} mA | {}VBAT={:.2f} V chg={:.1f} mA dis={:.1f} mA | {}".format(
                    vbus_v,
                    vbus_i,
                    sys_str,
                    vbat_v,
                    ichg,
                    idis,
                    flags,
                )
            )
            time.sleep(delay_s)
    except KeyboardInterrupt:
        print("\n[testBatt] Stopped")


if __name__ == "__main__":
    probe()
