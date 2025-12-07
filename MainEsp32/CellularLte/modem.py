# modem.py - Control básico del SIM7600 en LilyGO T-PCIE (UART1)

import _thread
import time

from machine import Pin, UART

try:
    import network  # type: ignore
except ImportError:  # pragma: no cover - host environments
    network = None



PIN_POWER  = 25
PIN_PWRKEY = 4
UART_TX = 27
UART_RX = 26

power_pin  = Pin(PIN_POWER, Pin.OUT)
pwrkey_pin = Pin(PIN_PWRKEY, Pin.OUT)
uart = UART(1, baudrate=115200, tx=UART_TX, rx=UART_RX)

_snapshot_powered = False

_rx_lines = []
_rx_lock = _thread.allocate_lock()
_reader_started = False

def modem_on():
    global _snapshot_powered
    print("Encendiendo SIM7600...")
    power_pin.value(1)
    time.sleep(0.1)
    pwrkey_pin.value(0); time.sleep(1.0); pwrkey_pin.value(1)
    time.sleep(5)
    print("SIM7600 listo.")
    _snapshot_powered = True

def modem_off():
    global _snapshot_powered
    print("Apagando SIM7600...")
    pwrkey_pin.value(0); time.sleep(1.0); pwrkey_pin.value(1)
    time.sleep(3)
    power_pin.value(0)
    print("SIM7600 apagado.")
    _snapshot_powered = False

def _append_rx_line(s):
    with _rx_lock:
        _rx_lines.append(s)

def _pop_all_rx_lines():
    with _rx_lock:
        items = _rx_lines[:]
        _rx_lines.clear()
        return items

def _reader_loop():
    global _reader_started
    try:
        buffer = b""
        while True:
            try:
                data = uart.read()
            except Exception as exc:
                print("[modem] UART read error:", exc)
                data = None
            if data:
                buffer += data
                while b"\r\n" in buffer:
                    idx = buffer.find(b"\r\n")
                    line = buffer[:idx]
                    buffer = buffer[idx + 2:]
                    if not line:
                        continue
                    try:
                        txt = line.decode('utf-8', 'ignore').strip()
                    except Exception:
                        txt = str(line)
                    if txt:
                        _append_rx_line(txt)
            else:
                time.sleep_ms(50)
    except Exception as exc:
        print("[modem] reader stopped:", exc)
    finally:
        _reader_started = False


def ensure_reader():
    global _reader_started
    if _reader_started:
        return
    _reader_started = True
    _thread.start_new_thread(_reader_loop, ())

def _wait_for_response(timeout_ms=2000):
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    collected = []
    while True:
        new = _pop_all_rx_lines()
        if new:
            collected.extend(new)
            return collected
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return collected
        time.sleep_ms(50)

def send_at(cmd, timeout_ms=2000):
    _pop_all_rx_lines()
    uart.write((cmd + "\r\n").encode())
    return _wait_for_response(timeout_ms)

def show_sim():
    print("-> AT+CPIN?"); print(send_at("AT+CPIN?"))
    print("-> AT+CSQ"); print(send_at("AT+CSQ"))
    print("-> AT+COPS?"); print(send_at("AT+COPS?"))


def get_imei():
    return send_at("AT+CGSN")


def get_imsi():
    return send_at("AT+CIMI")


def call_number(num):
    return send_at("ATD{};".format(num), timeout_ms=10000)


def send_sms(number, text):
    """Envía SMS en modo texto (configura CMGF cada vez)."""
    send_at("AT+CMGF=1")
    uart.write('AT+CMGS="{}"\r'.format(number).encode())
    time.sleep(0.5)
    uart.write(text.encode() + b"\x1A")
    return _wait_for_response(10000)


def connect_data(apn="datos.personal.com"):
    """Secuencia mínima para PDP context + NETOPEN."""
    send_at('AT+CGDCONT=1,"IP","{}"'.format(apn))
    send_at("AT+CGATT=1")
    send_at("AT+CGACT=1,1")
    print(send_at("AT+NETOPEN", timeout_ms=10000))
    return send_at("AT+IPADDR")


def http_get(host="example.com", path="/", port=80):
    send_at("AT+NETOPEN", timeout_ms=8000)
    print(send_at('AT+CIPOPEN=0,"TCP","{}",{}'.format(host, port), timeout_ms=10000))
    req = "GET {} HTTP/1.0\r\nHost: {}\r\n\r\n".format(path, host)
    send_at("AT+CIPSEND=0,{}".format(len(req)))
    uart.write(req.encode())
    resp = _wait_for_response(10000)
    send_at("AT+CIPCLOSE=0")
    return resp


def setup_ntp(server="pool.ntp.org", tz_hours=0):
    return send_at('AT+CNTP="{}",{}'.format(server, int(tz_hours)))


def trigger_ntp_sync(timeout_ms=30_000):
    return send_at("AT+CNTP", timeout_ms=timeout_ms)


def enable_nitz(save=False):
    """Activa CLTS (NITZ) para sincronizar hora desde la red."""
    resp = send_at("AT+CLTS=1")
    if save:
        send_at("AT&W")
    return resp


def disable_nitz(save=False):
    resp = send_at("AT+CLTS=0")
    if save:
        send_at("AT&W")
    return resp


def get_network_time():
    """Devuelve dict con la hora entregada por AT+CCLK? (NITZ)."""
    lines = send_at("AT+CCLK?", timeout_ms=3000)
    for line in lines:
        if line.startswith("+CCLK:"):
            raw = line.split(":", 1)[1].strip().strip('"')
            try:
                date_part, time_part = raw.split(",")
                year, month, day = [int(x) for x in date_part.split("/")]
                if year < 100:
                    year = 2000 + year if year < 70 else 1900 + year
                hh, mm, ss = [int(x) for x in time_part[:8].split(":")]
                tz = time_part[8:] if len(time_part) > 8 else "+00"
                tz_sign = 1 if tz[:1] == "+" else -1
                tz_quarters = int(tz[1:]) if len(tz) > 1 else 0
                tz_minutes = tz_sign * tz_quarters * 15
            except Exception as exc:
                print("[modem] CCLK parse error:", exc, raw)
                return {"raw": raw}
            return {
                "raw": raw,
                "year": year,
                "month": month,
                "day": day,
                "hour": hh,
                "minute": mm,
                "second": ss,
                "tz_minutes": tz_minutes,
            }
    return None


MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _clean_token(token):
    token = token.strip()
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        return token[1:-1]
    return token


def _maybe_plmn(token):
    stripped = _clean_token(token)
    if "-" not in stripped:
        return None
    parts = stripped.split("-", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return stripped


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value, base=10):
    try:
        return int(value, base)
    except Exception:
        return None


def _first_long_numeric(tokens, min_len=6):
    for token in tokens:
        raw = token.replace(" ", "")
        if raw.lower().startswith("0x"):
            number = _safe_int(raw, 16)
            if number is not None:
                return raw
            continue
        if raw.isdigit() and len(raw) >= min_len:
            return raw
    return None


def _first_negative_float(tokens, start_index=0):
    for token in tokens[start_index:]:
        value = _safe_float(token)
        if value is not None and value < 0:
            return value
    return None


def _parse_cced_segment(segment):
    raw_tokens = [part.strip() for part in segment.split(",") if part.strip()]
    if not raw_tokens:
        return None
    tokens = [_clean_token(tok) for tok in raw_tokens]
    entry = {"raw": segment.strip(), "tokens": tokens}
    if tokens and tokens[0].isalpha():
        entry["rat"] = tokens[0]
        tokens = tokens[1:]
    plmn = None
    for token in tokens:
        candidate = _maybe_plmn(token)
        if candidate:
            plmn = candidate
            break
    if plmn:
        entry["plmn"] = plmn
        try:
            entry["mcc"], entry["mnc"] = plmn.split("-", 1)
        except Exception:
            pass
    hex_tokens = [token for token in tokens if token.lower().startswith("0x")]
    if hex_tokens:
        entry["tac"] = hex_tokens[0]
    if len(hex_tokens) > 1:
        entry["cell_id"] = hex_tokens[1]
    else:
        fallback = _first_long_numeric(tokens)
        if fallback:
            entry["cell_id"] = fallback
    pci_candidate = None
    for token in tokens:
        if token.lower().startswith("0x"):
            continue
        try:
            value = int(token)
        except Exception:
            continue
        if 0 <= value <= 503:
            pci_candidate = value
            break
    if pci_candidate is not None:
        entry["pci"] = pci_candidate
    signal_dbm = _first_negative_float(tokens)
    if signal_dbm is not None:
        entry["signal_dbm"] = signal_dbm
        residual = []
        for token in tokens:
            val = _safe_float(token)
            if val is not None and val < 0 and val != signal_dbm:
                residual.append(val)
        if residual:
            entry["signal_aux"] = residual[:2]
    return entry


def _parse_cced_neighbors(lines):
    neighbors = []
    for line in lines or []:
        if not isinstance(line, str) or "+CCED:" not in line:
            continue
        try:
            _, payload = line.split(":", 1)
        except ValueError:
            continue
        portions = [part.strip() for part in payload.split(";") if part.strip()]
        for chunk in portions:
            entry = _parse_cced_segment(chunk)
            if entry:
                neighbors.append(entry)
    return neighbors


def _collect_neighbor_cells(limit=3):
    try:
        lines = send_at("AT+CCED=0,2", timeout_ms=5000)
    except Exception:
        return []
    neighbors = _parse_cced_neighbors(lines)
    if not neighbors:
        return []
    neighbors.sort(key=lambda item: item.get("signal_dbm", -200), reverse=True)
    if limit is None or limit <= 0:
        return neighbors
    return neighbors[:limit]


def _timestamp():
    now = time.localtime()
    try:
        month = MONTH_NAMES[now[1] - 1]
    except Exception:
        month = "???"
    return "{:02d}-{} {:02d}:{:02d}".format(now[2], month, now[3], now[4])


def _ensure_snapshot_power(force=False):
    global _snapshot_powered
    if _snapshot_powered and not force:
        return
    modem_on()
    ensure_reader()
    try:
        from . import gnss  # type: ignore
        gnss.gnss_on()
    except Exception:
        pass
    time.sleep(1.0)
    _snapshot_powered = True


def _snapshot_power_down():
    global _snapshot_powered
    try:
        from . import gnss  # type: ignore
        gnss.gnss_off()
    except Exception:
        pass
    modem_off()
    _snapshot_powered = False


def _parse_csq(lines):
    for line in lines or []:
        if line.startswith("+CSQ:"):
            try:
                payload = line.split(":", 1)[1].strip()
                rssi_code = int(payload.split(",")[0])
            except Exception:
                return None
            if rssi_code == 99:
                return {"raw": line, "csq": rssi_code, "rssi_dbm": None}
            return {
                "raw": line,
                "csq": rssi_code,
                "rssi_dbm": -113 + 2 * rssi_code,
            }
    return None


def _parse_cops(lines):
    for line in lines or []:
        if line.startswith("+COPS:"):
            try:
                values = [part.strip() for part in line.split(":", 1)[1].split(",")]
            except Exception:
                return None
            info = {"mode": values[0] if values else None}
            if len(values) >= 3:
                info["operator"] = values[2].strip('"')
            if len(values) >= 4:
                info["act"] = values[3]
            return info
    return None


def _parse_creg(lines):
    states = {
        "0": "not registered",
        "1": "home",
        "2": "searching",
        "3": "denied",
        "5": "roaming",
    }
    for line in lines or []:
        if line.startswith("+CREG:"):
            try:
                _, rest = line.split(":", 1)
                bits = [b.strip() for b in rest.split(",")]
            except Exception:
                continue
            stat = bits[1] if len(bits) > 1 else None
            return {"raw": line, "state": states.get(stat, "code {}".format(stat))}
    return None


def _parse_cpsi(lines):
    for line in lines or []:
        if line.startswith("+CPSI:"):
            return line.split(":", 1)[1].strip()
    return None


def _parse_cpsi_meta(lines):
    meta = {"raw": None}
    payload = _parse_cpsi(lines)
    if payload is None:
        return meta
    meta["raw"] = payload
    parts = [segment.strip() for segment in payload.split(",")]
    meta["parts"] = parts
    if not parts:
        return meta
    meta["rat"] = parts[0]
    if len(parts) > 1:
        meta["state"] = parts[1]
    if len(parts) > 2:
        plmn = parts[2]
        meta["plmn"] = plmn
        if plmn and "-" in plmn:
            meta["mcc"], meta["mnc"] = plmn.split("-", 1)
    if len(parts) > 3:
        meta["tac"] = parts[3]
    if len(parts) > 4:
        cell_id = parts[4]
        meta["cell_id"] = cell_id
        try:
            cid_int = int(cell_id, 0)
            meta["cell_id_int"] = cid_int
            meta["cell_id_hex"] = hex(cid_int)
        except Exception:
            pass
    if len(parts) > 5:
        meta["pci"] = parts[5]
    if len(parts) > 6:
        meta["band"] = parts[6]
    if len(parts) > 7:
        meta["earfcn_dl"] = parts[7]
    if len(parts) > 8:
        meta["earfcn_ul"] = parts[8]
    if len(parts) > 9:
        meta["bandwidth"] = parts[9]
    signal_values = []
    for idx, value in enumerate(parts):
        try:
            number = float(value)
        except Exception:
            continue
        signal_values.append((idx, number))
    negatives = [val for idx, val in signal_values if val < 0]
    if negatives:
        meta["signal_dbm"] = negatives[0]
    if len(negatives) > 1:
        meta["signal_aux"] = negatives[1:3]
    return meta


def _wifi_scan_top(limit=3):
    if network is None or limit <= 0:
        return []
    try:
        sta = network.WLAN(network.STA_IF)
    except Exception:
        return []
    try:
        sta.active(True)
        scan = sta.scan() or []
    except Exception as exc:
        print("[modem] wifi scan error:", exc)
        return []

    def _normalize(entry):
        if len(entry) < 4:
            return None
        rssi = entry[3]
        if not isinstance(rssi, int):
            return None
        raw_ssid = entry[0]
        if isinstance(raw_ssid, bytes):
            try:
                ssid_val = raw_ssid.decode("utf-8")
            except Exception:
                ssid_val = raw_ssid.decode("latin-1", "ignore")
        else:
            ssid_val = raw_ssid
        if len(entry) > 1 and isinstance(entry[1], (bytes, bytearray)):
            bssid_val = ":".join(["{:02X}".format(b) for b in entry[1]])
        else:
            bssid_val = None
        return {"ssid": ssid_val, "bssid": bssid_val, "rssi": rssi}

    normalized = []
    for row in scan:
        info = _normalize(row)
        if info is None:
            continue
        normalized.append(info)
    normalized.sort(key=lambda entry: entry.get("rssi") if isinstance(entry.get("rssi"), int) else -200, reverse=True)
    return normalized[:limit]


def _gnss_snapshot():
    try:
        from . import gnss  # type: ignore
    except Exception:
        return {}
    lines = send_at("AT+CGNSINF", timeout_ms=4000)
    data = gnss.parse_cgnsinf(lines)
    if data:
        return data.copy()
    fallback = gnss.read_once()
    if fallback:
        return fallback.copy()
    return gnss.GNSS_DATA.copy()


def collect_snapshot(*, wifi_limit=3, ensure_power=True, power_down=False):
    """Captura un snapshot de señal/celda/GNSS/Wi-Fi listo para telemetría."""

    if ensure_power:
        _ensure_snapshot_power()
    wifi_list = _wifi_scan_top(limit=wifi_limit)
    cpsi_lines = send_at("AT+CPSI?", timeout_ms=4000)
    cpsi_meta = _parse_cpsi_meta(cpsi_lines)
    neighbors = _collect_neighbor_cells(limit=3)
    if neighbors and isinstance(cpsi_meta, dict):
        neighbor_ids = []
        for entry in neighbors:
            cell_id = entry.get("cell_id")
            if cell_id:
                neighbor_ids.append(cell_id)
        if neighbor_ids:
            cpsi_meta.setdefault("neighbor_ids", neighbor_ids[:2])
    snapshot = {
        "timestamp": _timestamp(),
        "signal": _parse_csq(send_at("AT+CSQ")),
        "operator": _parse_cops(send_at("AT+COPS?")),
        "registration": _parse_creg(send_at("AT+CREG?")),
        "cell_info": cpsi_meta.get("raw"),
        "cell_info_lines": cpsi_lines,
        "cell_info_meta": cpsi_meta,
        "gnss": _gnss_snapshot(),
        "wifi": wifi_list[0] if wifi_list else None,
        "wifi_list": wifi_list,
        "cell_neighbors": neighbors,
    }
    if power_down:
        _snapshot_power_down()
    return snapshot


def print_snapshot(*, wifi_limit=3, ensure_power=True, power_down=False):
    snap = collect_snapshot(wifi_limit=wifi_limit, ensure_power=ensure_power, power_down=power_down)
    print("===== SIM7600 SNAPSHOT =====")
    print("Timestamp:", snap.get("timestamp"))
    signal = snap.get("signal") or {}
    if signal:
        rssi_dbm = signal.get("rssi_dbm")
        rssi_label = "{} dBm".format(rssi_dbm) if rssi_dbm is not None else "N/A"
        print("Signal CSQ:", signal.get("csq"), rssi_label)
    else:
        print("Signal: N/A")
    operator = snap.get("operator") or {}
    if operator:
        print("Operator:", operator.get("operator"), "ACT", operator.get("act"))
    registration = snap.get("registration")
    if registration:
        print("Network status:", registration.get("state"))
    cell_info = snap.get("cell_info")
    if cell_info:
        print("Cell info:", cell_info)
        meta = snap.get("cell_info_meta") or {}
        pieces = []
        if meta.get("mcc") or meta.get("mnc"):
            pieces.append("PLMN {}-{}".format(meta.get("mcc") or "?", meta.get("mnc") or "?"))
        if meta.get("tac"):
            pieces.append("TAC {}".format(meta.get("tac")))
        if meta.get("cell_id"):
            pieces.append("Cell {}".format(meta.get("cell_id")))
        if meta.get("pci"):
            pieces.append("PCI {}".format(meta.get("pci")))
        if meta.get("band"):
            pieces.append(meta.get("band"))
        if meta.get("signal_dbm") is not None:
            pieces.append("Sig {:.0f} dBm".format(meta.get("signal_dbm")))
        if pieces:
            print("Cell detail:", ", ".join(pieces))
    gps = snap.get("gnss") or {}
    if gps.get("lat") is not None and gps.get("lon") is not None:
        print(
            "GPS:",
            "fix" if gps.get("fix") else "no-fix",
            "lat={:.6f} lon={:.6f} alt={} sats={}".format(
                gps.get("lat"), gps.get("lon"), gps.get("alt"), gps.get("sats")
            ),
        )
    else:
        print("GPS: no data")
    wifi_entries = snap.get("wifi_list") or ([] if snap.get("wifi") is None else [snap.get("wifi")])
    if wifi_entries:
        for idx, wifi in enumerate(wifi_entries[:2], start=1):
            print(
                "WiFi #{}:".format(idx),
                wifi.get("bssid"),
                wifi.get("ssid"),
                "{} dBm".format(wifi.get("rssi")),
            )
    else:
        print("WiFi strongest: N/A")
    neighbors = snap.get("cell_neighbors") or []
    if neighbors:
        for idx, neighbor in enumerate(neighbors[:2], start=1):
            descr = neighbor.get("cell_id") or neighbor.get("tac") or neighbor.get("raw")
            signal = neighbor.get("signal_dbm")
            plmn = neighbor.get("plmn")
            label = descr or "?"
            extra = [label]
            if plmn:
                extra.append(plmn)
            if signal is not None:
                extra.append("{:.0f} dBm".format(signal))
            print("Neighbor #{}:".format(idx), ", ".join(extra))
    else:
        print("Neighbor cells: N/A")
    print("============================")
    return snap


def _format_sms_payload(snapshot):
    gps = snapshot.get("gnss") or {}
    wifi = snapshot.get("wifi") or {}
    lat = gps.get("lat")
    lon = gps.get("lon")
    sats = gps.get("sats")
    lat_txt = "{:.4f}".format(lat) if isinstance(lat, (int, float)) else "N/A"
    lon_txt = "{:.4f}".format(lon) if isinstance(lon, (int, float)) else "N/A"
    sats_txt = str(sats) if sats is not None else "?"
    signal = snapshot.get("signal") or {}
    rssi_dbm = signal.get("rssi_dbm")
    rssi_txt = "{}dBm".format(rssi_dbm) if rssi_dbm is not None else "N/A"
    bssid_txt = wifi.get("bssid") or "N/A"
    ssid_txt = wifi.get("ssid") or "?"
    return (
        "{} lat={} lon={} sats={} sig={} BSSID={} SSID={}".format(
            snapshot.get("timestamp"), lat_txt, lon_txt, sats_txt, rssi_txt, bssid_txt, ssid_txt
        )
    )


def send_status_sms(number, *, snapshot=None, power_down=False):
    if not number:
        raise ValueError("number is required for SMS")
    snap = snapshot or collect_snapshot(power_down=power_down)
    payload = _format_sms_payload(snap)
    print("[modem] SMS ->", number)
    print(payload)
    result = send_sms(number, payload)
    print("[modem] SMS resp:", result)
    return result


