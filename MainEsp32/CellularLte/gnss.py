# gnss.py - GNSS con SIM7600
import uasyncio

try:
    from . import modem  # type: ignore
except ImportError:
    import modem  # type: ignore

# Diccionario global accesible desde REPL
GNSS_DATA = {
    "fix": 0,
    "sats": 0,
    "lat": None,
    "lon": None,
    "alt": None,
    "speed": None
}

def gnss_on():
    return modem.send_at("AT+CGPS=1")

def gnss_off():
    return modem.send_at("AT+CGPS=0")

def nmea_to_decimal(coord, hemi):
    """Convierte coordenada NMEA ddmm.mmmm + N/S/E/W a decimal."""
    if not coord or coord == "":
        return None
    try:
        # separar en grados y minutos
        if "." not in coord:
            return None
        dot_index = coord.index(".")
        deg_len = dot_index - 2  # todo menos 2 dígitos finales son grados
        deg = int(coord[:deg_len])
        minutes = float(coord[deg_len:])
        dec = deg + minutes / 60.0
        if hemi in ["S", "W"]:
            dec = -dec
        return dec
    except Exception as e:
        print("parse error:", e, coord, hemi)
        return None

def read_once():
    """Lee una vez las coordenadas con AT+CGPSINFO y actualiza GNSS_DATA."""
    lines = modem.send_at("AT+CGPSINFO", timeout_ms=2000)
    for l in lines:
        if l.startswith("+CGPSINFO:"):
            parts = l.replace("+CGPSINFO:","").split(",")
            if len(parts) >= 8 and parts[0].strip():
                lat = nmea_to_decimal(parts[0], parts[1])
                lon = nmea_to_decimal(parts[2], parts[3])
                date = parts[4]
                utc  = parts[5]
                alt  = float(parts[6]) if parts[6] else None
                spd  = float(parts[7]) if parts[7] else None
                GNSS_DATA.update({
                    "fix": 1,
                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "speed": spd,
                    "date": date,
                    "utc": utc
                })
                return GNSS_DATA
            else:
                GNSS_DATA.update({"fix":0})
    return None

def parse_cgnsinf(lines):
    """
    Parseo simple de AT+CGNSINF.
    Ejemplo: +CGNSINF: 1,1,20240609120000.000,40.4168,-3.7038,667.5,0.00,0.0,1
    """
    for l in lines:
        if l.startswith("+CGNSINF"):
            parts = l.split(",")
            if len(parts) >= 6:
                GNSS_DATA["fix"]   = int(parts[1])
                GNSS_DATA["sats"]  = int(parts[14]) if len(parts) > 14 and parts[14].isdigit() else 0
                GNSS_DATA["lat"]   = float(parts[3]) if parts[3] else None
                GNSS_DATA["lon"]   = float(parts[4]) if parts[4] else None
                GNSS_DATA["alt"]   = float(parts[5]) if parts[5] else None
                GNSS_DATA["speed"] = float(parts[6]) if parts[6] else None
                return GNSS_DATA
    return None


async def gnss_task(period_s=5):
    """Task periódica que actualiza GNSS_DATA cada period_s segundos."""
    gnss_on()
    await uasyncio.sleep(2)  # tiempo para inicializar
    while True:
        try:
            read_once()
            #print("GNSS:", GNSS_DATA)
        except Exception as e:
            print("GNSS task error:", e)
        await uasyncio.sleep(period_s)
