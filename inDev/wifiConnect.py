import network
import time

try:
    import machine
except ImportError:  # pragma: no cover - optional on host
    machine = None

try:
    from wifi_config import NETWORKS as WIFI_NETWORKS
except ImportError:  # pragma: no cover - optional on device
    WIFI_NETWORKS = []

DEFAULT_WIFI = ('iot', 'frayjusto1960')
DEFAULT_IFCONFIG = ('192.168.0.11', '255.255.255.0', '192.168.0.1', '8.8.8.8')


def load_wifi_settings(path='/ipaddress.cfg'):
    """Load fallback Wi-Fi credentials and static IP info."""
    ssid, password = DEFAULT_WIFI
    ifconfig = DEFAULT_IFCONFIG
    found = False
    hostname = None
    try:
        with open(path) as cfg:
            lines = cfg.read().splitlines()
            found = True
    except OSError:
        return (ssid, password), ifconfig, hostname, False

    payload = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')]

    if payload:
        wifi_parts = [item.strip().strip("'\"") for item in payload[0].split(',') if item.strip()]
        if len(wifi_parts) >= 2:
            ssid, password = wifi_parts[0], wifi_parts[1]

    if len(payload) >= 2:
        ip_parts = [item.strip().strip("'\"") for item in payload[1].split(',') if item.strip()]
        if len(ip_parts) >= 4:
            ifconfig = tuple(ip_parts[:4])

    # hostname as third line (optional)
    if len(payload) >= 3:
        hostname = payload[2].strip().strip("'\"")

    return (ssid, password), ifconfig, hostname, found


def _wifi_config_networks():
    """Return networks defined in wifi_config.py."""
    cleaned = []
    for entry in WIFI_NETWORKS:
        if not isinstance(entry, dict):
            continue
        ssid = entry.get('ssid')
        if not ssid:
            continue

        config = {
            'ssid': ssid,
            'password': entry.get('password'),
        }
        static_ip = entry.get('ip')
        if isinstance(static_ip, str):
            static_ip = static_ip.strip()
        if static_ip:
            netmask = entry.get('netmask') or DEFAULT_IFCONFIG[1]
            gateway = entry.get('gateway') or DEFAULT_IFCONFIG[2]
            dns = entry.get('dns') or DEFAULT_IFCONFIG[3]
            config['ifconfig'] = (
                str(static_ip),
                str(netmask),
                str(gateway),
                str(dns),
            )
        # hostname support
        hostname = entry.get('hostname')
        if hostname:
            config['hostname'] = str(hostname)
        cleaned.append(config)
    return cleaned


def _prioritize_by_scan(wlan, networks):
    """Sort configured networks by RSSI descending based on scan results."""
    if wlan is None or not hasattr(wlan, 'scan'):
        return networks
    if not networks:
        return networks
    try:
        results = wlan.scan()
    except Exception as exc:
        print('[wifi] scan failed:', exc)
        return networks
    rssi_map = {}
    for entry in results or []:
        try:
            raw_ssid = entry[0]
        except (TypeError, IndexError):
            continue
        if isinstance(raw_ssid, bytes):
            try:
                ssid = raw_ssid.decode('utf-8')
            except Exception:
                ssid = raw_ssid.decode('latin-1', 'ignore')
        else:
            ssid = raw_ssid
        if not ssid:
            continue
        rssi = entry[3] if len(entry) > 3 else None
        if isinstance(rssi, int):
            previous = rssi_map.get(ssid)
            if previous is None or rssi > previous:
                rssi_map[ssid] = rssi
    if not rssi_map:
        return networks
    return sorted(
        networks,
        key=lambda item: rssi_map.get(item.get('ssid'), -200),
        reverse=True,
    )


def _attempt_connect(sta_if, ssid, password, attempts=20, wait_ms=500):
    if not ssid:
        return False
    print('[wifi] connecting to {}...'.format(ssid))
    try:
        sta_if.disconnect()
    except AttributeError:
        pass
    sta_if.connect(ssid, password)
    for _ in range(attempts):
        if sta_if.isconnected():
            return True
        time.sleep_ms(wait_ms)
    print('[wifi] timeout for {}'.format(ssid))
    return False



# --- STA_IF creation and hostname setup ---
sta_if = network.WLAN(network.STA_IF)

# Determine hostname from config (wifi_config or ipaddress.cfg)
hostname = None
wifi_networks = _wifi_config_networks()
fallback_wifi, fallback_ifconfig, fallback_hostname, ip_cfg_found = load_wifi_settings()

uid_hostname = None
if hasattr(network, 'hostname'):
    uid_suffix = '0000'
    if machine is not None and hasattr(machine, 'unique_id'):
        try:
            uid = machine.unique_id()
            if isinstance(uid, (bytes, bytearray)) and len(uid) >= 2:
                uid_suffix = '{:02X}{:02X}'.format(uid[-2], uid[-1])
        except Exception:
            uid_suffix = '0000'
    uid_hostname = 'ESP-{}'.format(uid_suffix)

# Prefer hostname from wifi_networks if present, else fallback_hostname, else ESP-UID
if wifi_networks:
    for net in wifi_networks:
        if 'hostname' in net and net['hostname']:
            hostname = net['hostname']
            break
if not hostname and fallback_hostname:
    hostname = fallback_hostname
if not hostname:
    hostname = uid_hostname

if hostname and hasattr(network, 'hostname'):
    try:
        network.hostname(str(hostname))
    except Exception as exc:
        print('[wifi] hostname setup failed:', exc)

sta_if.active(True)
try:
    time.sleep_ms(100)
except AttributeError:
    time.sleep(0.1)

connected = False
connected_ssid = None
connected_network = None
used_fallback_config = False

if wifi_networks:
    for round_idx in range(3):
        prioritized = _prioritize_by_scan(sta_if, wifi_networks)
        for creds in prioritized:
            if _attempt_connect(sta_if, creds.get('ssid'), creds.get('password')):
                connected = True
                connected_ssid = creds.get('ssid')
                connected_network = creds
                break
        if connected:
            break
        time.sleep(1)

if not connected and ip_cfg_found:
    ssid, password = fallback_wifi
    print('[wifi] attempting fallback config {}'.format(ssid))
    if _attempt_connect(sta_if, ssid, password, attempts=30):
        connected = True
        connected_ssid = ssid
        used_fallback_config = True
        connected_network = None

if not connected and not wifi_networks and not ip_cfg_found:
    print('[wifi] no wifi_config.py or ipaddress.cfg available; continuing without network')

if connected and connected_network and 'ifconfig' in connected_network:
    try:
        sta_if.ifconfig(connected_network['ifconfig'])
    except Exception as exc:
        print('[wifi] failed to set static IP for {}: {}'.format(connected_ssid, exc))
elif connected and used_fallback_config and ip_cfg_found:
    try:
        sta_if.ifconfig(fallback_ifconfig)
    except Exception as exc:
        print('[wifi] failed to set static IP:', exc)

if connected:
    ip, _, gw, _ = sta_if.ifconfig()
    if ip == '0.0.0.0':
        print('[waiting for an IP ]', end='')
        for _ in range(30):
            ip, _, gw, _ = sta_if.ifconfig()
            if ip != '0.0.0.0':
                break
            time.sleep(1)
            print('.', end='')
        print('')
else:
    print('[wifi] unable to establish Wi-Fi connection')

if connected:
    import webrepl
    webrepl.start()

    import netutils.ftp_thread as ftp_thread
    ftp = ftp_thread.FtpTiny()
    ftp.start()

    try:
        reported_ssid = sta_if.config('essid')
    except Exception:
        reported_ssid = connected_ssid or 'unknown'
    try:
        rssi = sta_if.status('rssi')
    except Exception:
        try:
            rssi = sta_if.config('rssi')
        except Exception:
            rssi = None
    ip, _, gw, _ = sta_if.ifconfig()
    rssi_label = '{} dBm'.format(rssi) if isinstance(rssi, int) else 'N/A'
    print('WIFI connected: ssid={} rssi={} ip={} gw={}'.format(reported_ssid, rssi_label, ip, gw))
else:
    print('[wifi] continuing offline mode')
