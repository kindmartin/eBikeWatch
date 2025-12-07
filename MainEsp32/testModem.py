# testModem.py
# Diagnóstico rápido del SIM7600 montado en la LilyGO T-PCIE v1.1.

import time

from CellularLte import gnss, modem
from machine import RTC  # type: ignore

DEFAULT_SMS_NUMBER = "+541131602601"
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MIN_VALID_YEAR = 2025
ARG_TZ_MINUTES = -180  # Argentina GMT-3

_powered = False

try:
    _ticks_ms = time.ticks_ms  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - CPython
    def _ticks_ms():
        return int(time.time() * 1000)

try:
    _ticks_add = time.ticks_add  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - CPython
    def _ticks_add(base, delta):
        return base + delta

try:
    _ticks_diff = time.ticks_diff  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - CPython
    def _ticks_diff(end, start):
        return end - start


    def power_on(force=False):
        """Enciende el módem, arranca el reader y habilita GNSS."""
        global _powered
        if _powered and not force:
            return
        modem.modem_on()
        modem.ensure_reader()
        gnss.gnss_on()
        time.sleep(1.0)
        _powered = True


    def power_off():
        """Apaga GNSS y el módem (libera el bus)."""
        global _powered
        if not _powered:
            return
        try:
            gnss.gnss_off()
        except Exception:
            pass
        modem.modem_off()
        _powered = False


    def collect_snapshot(*, power_down=False, wifi_limit=3, ensure_power=True):
        """Wrapper hacia CellularLte.modem.collect_snapshot."""

        global _powered
        if ensure_power:
            power_on()
        snapshot = modem.collect_snapshot(
            power_down=power_down,
            wifi_limit=wifi_limit,
            ensure_power=False,
        )
        if power_down:
            _powered = False
        return snapshot


    def print_snapshot(*, wifi_limit=3, ensure_power=True, power_down=False):
        """Proxy que reutiliza el print snapshot del módulo de módem."""

        global _powered
        if ensure_power:
            power_on()
        snap = modem.print_snapshot(
            wifi_limit=wifi_limit,
            ensure_power=False,
            power_down=power_down,
        )
        if power_down:
            _powered = False
        return snap


    def monitor_gnss(max_wait_s=180, interval_s=5, min_sats=1, verbose=True):
        """Encuesta el GNSS hasta lograr fix o agotar el tiempo máximo."""
        power_on()
        start_ms = _ticks_ms()
        deadline_ms = _ticks_add(start_ms, int(max_wait_s * 1000))
        if verbose:
            status = modem.send_at("AT+CGNSPWR?")
            print("[testModem] CGNSPWR?:", " ".join(status) if isinstance(status, list) else status)
        attempt = 0
        last = gnss.GNSS_DATA.copy()
        while True:
            attempt += 1
            lines = modem.send_at("AT+CGNSINF", timeout_ms=4000)
            raw_line = next((line for line in lines if line.startswith("+CGNSINF")), None)
            data = gnss.parse_cgnsinf(lines)
            if not data:
                data = gnss.read_once()
            if data:
                info = data.copy()
            else:
                info = gnss.GNSS_DATA.copy()
            if raw_line:
                info["raw"] = raw_line
            last = info
            sats = info.get("sats")
            fix = bool(info.get("fix"))
            lat = info.get("lat")
            lon = info.get("lon")
            alt = info.get("alt")
            speed = info.get("speed")
            elapsed_s = _ticks_diff(_ticks_ms(), start_ms) / 1000.0
            if verbose:
                print("[testModem] GNSS intento {} ({:.1f}s): fix={} sats={} lat={} lon={} alt={} speed={}".format(
                    attempt, elapsed_s, fix, sats, lat, lon, alt, speed))
            has_fix = fix and lat is not None and lon is not None
            sats_ok = True
            if isinstance(min_sats, (int, float)) and min_sats > 0:
                sats_ok = isinstance(sats, (int, float)) and sats >= min_sats
            if has_fix and sats_ok:
                if verbose:
                    print("[testModem] GNSS fix logrado con {} satélites en {:.1f}s".format(sats, elapsed_s))
                return info
            if _ticks_diff(deadline_ms, _ticks_ms()) <= 0:
                break
            time.sleep(interval_s)
        if verbose:
            print("[testModem] GNSS sin fix tras {}s. Último estado: {}".format(max_wait_s, last))
        return last


def _set_rtc_from_utc(year, month, day, hour, minute, second, *, label="RTC", tz_minutes=0):
    try:
        ts = time.mktime((year, month, day, hour, minute, second, 0, 0))
        ts = ts + (tz_minutes * 60)
        local_tuple = time.localtime(ts)
        weekday = local_tuple[6]
    except Exception:
        weekday = 0
        local_tuple = (year, month, day, hour, minute, second)
    rtc = RTC()
    rtc.datetime((
        local_tuple[0],
        local_tuple[1],
        local_tuple[2],
        weekday,
        local_tuple[3],
        local_tuple[4],
        local_tuple[5],
        0,
    ))
    offset_hours = tz_minutes / 60.0
    print("[testModem] {} ajustado a {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d} (UTC{:+.1f})".format(
        label,
        local_tuple[0],
        local_tuple[1],
        local_tuple[2],
        local_tuple[3],
        local_tuple[4],
        local_tuple[5],
        offset_hours,
    ))
    return True


def _extract_gnss_datetime(info):
    raw = info.get("raw")
    if isinstance(raw, str):
        try:
            payload = raw.split(":", 1)[1].strip()
            parts = payload.split(",")
            ts = parts[2].split(".")[0]
            if len(ts) >= 14:
                return (
                    int(ts[0:4]),
                    int(ts[4:6]),
                    int(ts[6:8]),
                    int(ts[8:10]),
                    int(ts[10:12]),
                    int(ts[12:14]),
                )
        except Exception:
            pass
    date = info.get("date")
    utc = info.get("utc")
    if isinstance(date, str) and len(date) >= 6 and isinstance(utc, str) and len(utc) >= 6:
        try:
            day = int(date[0:2])
            month = int(date[2:4])
            year = 2000 + int(date[4:6])
            hour = int(utc[0:2])
            minute = int(utc[2:4])
            second = int(float(utc[4:]))
            return (year, month, day, hour, minute, second)
        except Exception:
            return None
    return None


def sync_rtc_from_gnss(max_wait_s=300, interval_s=10, min_sats=4, verbose=True):
    """Intenta sincronizar el RTC usando la hora UTC del GNSS."""
    info = monitor_gnss(max_wait_s=max_wait_s, interval_s=interval_s,
                        min_sats=min_sats, verbose=verbose)
    dt = _extract_gnss_datetime(info)
    if not dt:
        print("[testModem] No se pudo extraer fecha/hora del GNSS.")
        return False
    if dt[0] < MIN_VALID_YEAR:
        print("[testModem] GNSS devolvió un año inválido:", dt[0])
        return False
    return _set_rtc_from_utc(
        dt[0], dt[1], dt[2], dt[3], dt[4], dt[5], label="RTC/GNSS",
        tz_minutes=ARG_TZ_MINUTES
    )


def send_status_sms(number=DEFAULT_SMS_NUMBER, *, power_down=False):
    global _powered
    if not number:
        raise ValueError("Se requiere un número para enviar SMS")
    result = modem.send_status_sms(number, power_down=power_down)
    if power_down:
        _powered = False
    return result


def _ensure_fresh_network_time(apn="datos.personal.com", ntp_server="pool.ntp.org", *, force_ntp=False):
    data = modem.get_network_time()
    if not force_ntp and data and data.get("year", 0) >= MIN_VALID_YEAR:
        return data
    if not apn:
        msg = "[testModem] CNTP requiere un APN configurado." if force_ntp else \
            "[testModem] Año inválido y no se especificó APN para CNTP."
        print(msg)
        return data
    print("[testModem] Ejecutando CNTP via", apn)
    modem.connect_data(apn)
    modem.setup_ntp(ntp_server, 0)
    modem.trigger_ntp_sync()
    return modem.get_network_time()


def _apply_network_time(data, *, label):
    try:
        ts_local = time.mktime((
            data["year"], data["month"], data["day"],
            data["hour"], data["minute"], data["second"],
            0, 0
        ))
        tz_minutes = data.get("tz_minutes", 0) or 0
        ts_utc = ts_local - (tz_minutes * 60)
        utc_tuple = time.localtime(ts_utc)
    except Exception as exc:
        print("[testModem] Error al interpretar hora de red:", exc, data)
        return False
    return _set_rtc_from_utc(
        utc_tuple[0], utc_tuple[1], utc_tuple[2],
        utc_tuple[3], utc_tuple[4], utc_tuple[5],
        label=label, tz_minutes=ARG_TZ_MINUTES
    )


def sync_rtc_from_modem(save_clts=False, *, apn="datos.personal.com", ntp_server="pool.ntp.org"):
    """Activa NITZ y usa la hora de la red si es válida (>2024)."""
    power_on()
    modem.enable_nitz(save=save_clts)
    data = _ensure_fresh_network_time(apn=apn, ntp_server=ntp_server)
    if not data or data.get("year", 0) < MIN_VALID_YEAR:
        print("[testModem] No se consiguió hora NITZ válida.")
        return False
    return _apply_network_time(data, label="RTC/NITZ")


def sync_rtc_from_ntp(*, apn="datos.personal.com", ntp_server="pool.ntp.org"):
    """Obtiene hora vía CNTP (NTP) y ajusta GMT-3."""
    if not apn:
        print("[testModem] Se requiere un APN para sincronizar por NTP.")
        return False
    power_on()
    data = _ensure_fresh_network_time(apn=apn, ntp_server=ntp_server, force_ntp=True)
    if not data or data.get("year", 0) < MIN_VALID_YEAR:
        print("[testModem] NTP no devolvió una hora válida.")
        return False
    return _apply_network_time(data, label="RTC/NTP")


def sync_rtc_auto(*, apn="datos.personal.com", ntp_server="pool.ntp.org",
                  gnss_wait_s=30, gnss_interval_s=5, gnss_min_sats=4,
                  save_clts=False, verbose=True):
    """Sincroniza el RTC con prioridad GNSS > NITZ > NTP."""
    if verbose:
        print("[testModem] Intentando sincronización via GNSS...")
    if sync_rtc_from_gnss(max_wait_s=gnss_wait_s, interval_s=gnss_interval_s,
                          min_sats=gnss_min_sats, verbose=verbose):
        return "gnss"
    if verbose:
        print("[testModem] GNSS no disponible. Probando NITZ...")
    if sync_rtc_from_modem(save_clts=save_clts, apn="datos.personal.com", ntp_server=ntp_server):
        return "nitz"
    if verbose:
        print("[testModem] NITZ no entregó hora válida. Probando NTP...")
    if apn and sync_rtc_from_ntp(apn=apn, ntp_server=ntp_server):
        return "ntp"
    if not apn:
        print("[testModem] No se configuró APN, imposible intentar NTP.")
    print("[testModem] No se pudo sincronizar el RTC con ninguna fuente.")
    return False


if __name__ == "__main__":
    print_snapshot()
