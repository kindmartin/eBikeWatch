# alarm_mode.py (usa mma8452q_tools)
import ujson as json
from machine import Pin, deepsleep, reset_cause, DEEPSLEEP_RESET
import esp32
from HW import make_i2c, dacs_zero_both
import mma8452q_tools as mma

STATE_FILE = "alarm_state.json"

def _read_json(path, default):
    try:
        with open(path, "r") as f:
            return json.loads(f.read())
    except Exception:
        return default

def _write_json(path, data):
    try:
        with open(path, "w") as f:
            f.write(json.dumps(data))
    except Exception as e:
        print("[alarm] persist error:", e)

def load_state():
    return _read_json(STATE_FILE, {"armed": False, "phone": "", "sens_mg": 150})

def save_state(d):
    _write_json(STATE_FILE, d)

def clear_state():
    _write_json(STATE_FILE, {"armed": False, "phone": "", "sens_mg": 150})

def arm(phone: str, sens_mg: int = 150, wake_pin: int = 32):
    save_state({"armed": True, "phone": str(phone), "sens_mg": int(sens_mg)})
    i2c = make_i2c()
    mma.config_motion_wake(i2c=i2c, sens_mg=sens_mg, debounce=4, route_to_int=1)
    dacs_zero_both(i2c)
    pin = Pin(wake_pin, Pin.IN)
    esp32.wake_on_ext0(pin=pin, level=0)
    deepsleep()

def disarm():
    clear_state()

async def task_reporter(send_fn, phone, period_s=300, build_payload=None):
    from uasyncio import sleep
    if build_payload is None:
        def build_payload():
            return "eBike alarma: dispositivo activo."
    while True:
        try:
            msg = build_payload()
            send_fn(phone, msg)
        except Exception as e:
            print("[alarm] reporter error:", e)
        await sleep(period_s)

def try_resume_post_boot(asyncio, send_fn=None, build_payload=None):
    st = load_state()
    if not st.get("armed"):
        return False
    if reset_cause() != DEEPSLEEP_RESET:
        return False
    mma.set_ints_floating(make_i2c())
    if send_fn is None:
        def send_fn(phone, text):
            pass
    asyncio.create_task(task_reporter(send_fn, st.get("phone",""), 300, build_payload))
    return True
