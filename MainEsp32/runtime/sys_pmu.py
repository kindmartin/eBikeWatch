"""Background task that samples the onboard AXP192 PMU and updates AppState."""

import uasyncio as asyncio
from time import ticks_ms

from HW import make_i2c

try:
    from drivers.axp192 import AXP192
except Exception as exc:  # pragma: no cover - import guard for unit tests
    AXP192 = None  # type: ignore
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


_MIN_INTERVAL_MS = 250
_REINIT_DELAY_MS = 2000


def _format_flags(power_status, charge_status, vbus_present, battery_present):
    labels = []
    if vbus_present:
        labels.append("VBUS")
    if battery_present:
        labels.append("BAT")
    if charge_status.get("charging"):
        labels.append("CHG")
    if charge_status.get("charge_complete"):
        labels.append("DONE")
    if charge_status.get("battery_overtemp"):
        labels.append("HOT")
    if charge_status.get("vbus_low"):
        labels.append("VBUSLOW")
    if not labels:
        labels.append("IDLE")
    return " ".join(labels)


def _update_state_from_readings(state, pmu):
    vbus_mv = pmu.read_vbus_voltage()
    vbat_mv = pmu.read_vbat_voltage()
    vbus_ma = pmu.read_vbus_current()
    ichg = pmu.read_battery_charge_current()
    idis = pmu.read_battery_discharge_current()
    power_status = pmu.get_power_status()
    charge_status = pmu.get_charge_status()

    vbus_v = vbus_mv / 1000.0 if vbus_mv else 0.0
    vbat_v = vbat_mv / 1000.0 if vbat_mv else 0.0
    vbus_present = bool(power_status.get("vbus_present")) or vbus_v > 0.1
    battery_present = bool(power_status.get("battery_present")) or vbat_v > 0.1

    if vbus_present:
        board_source = "VBUS"
        board_current = vbus_ma if vbus_ma > 0 else 0.0
    elif battery_present:
        board_source = "SYSBATT"
        board_current = idis if idis > 0 else 0.0
    else:
        board_source = "N/A"
        board_current = 0.0

    state.sys_pmu_available = True
    state.sys_pmu_addr = getattr(pmu, "addr", None)
    state.sys_vbus_v = round(vbus_v, 3)
    state.sys_vbus_ma = round(vbus_ma, 1)
    state.sys_vbat_v = round(vbat_v, 3)
    state.sys_batt_charge_ma = round(ichg, 1)
    state.sys_batt_discharge_ma = round(idis, 1)
    state.sys_board_current_ma = round(board_current, 1)
    state.sys_board_source = board_source
    state.sys_power_status = dict(power_status)
    state.sys_charge_status = dict(charge_status)
    state.sys_status_flags = _format_flags(power_status, charge_status, vbus_present, battery_present)
    state.sys_batt_last_update_ms = ticks_ms()


async def sys_pmu_task(state, *, interval_ms=500, reinit_delay_ms=_REINIT_DELAY_MS):
    if AXP192 is None:
        state.sys_pmu_available = False
        state.sys_status_flags = "PMU driver missing"
        print("[sys_pmu] drivers.axp192 unavailable:", _IMPORT_ERROR)
        return

    interval_ms = max(_MIN_INTERVAL_MS, int(interval_ms or _MIN_INTERVAL_MS))
    reinit_delay_ms = max(500, int(reinit_delay_ms or _REINIT_DELAY_MS))

    while True:
        try:
            i2c = make_i2c()
            pmu = AXP192(i2c)
            try:
                pmu.enable_vbus_adc(True)
                pmu.enable_battery_adc(True)
            except AttributeError:
                pass
            except Exception as exc:
                print("[sys_pmu] ADC enable error:", exc)
            state.sys_pmu_available = True
            state.sys_pmu_addr = getattr(pmu, "addr", None)
            failure_reason = None
        except Exception as exc:
            state.sys_pmu_available = False
            state.sys_status_flags = "PMU init error"
            failure_reason = exc
            pmu = None
        if pmu is None:
            await asyncio.sleep_ms(reinit_delay_ms)
            continue

        try:
            while True:
                try:
                    _update_state_from_readings(state, pmu)
                except Exception as exc:
                    failure_reason = exc
                    state.sys_pmu_available = False
                    state.sys_status_flags = "PMU read error"
                    break
                await asyncio.sleep_ms(interval_ms)
        finally:
            if failure_reason:
                print("[sys_pmu] restart due to:", failure_reason)
        await asyncio.sleep_ms(reinit_delay_ms)


__all__ = ["sys_pmu_task"]
