# maintest_buttons.py
# Banco de pruebas para PageButton y UpDownButtons sin depender del display OLED.
# Tras hacer `import maintest_buttons`, el script arranca tareas uasyncio que
# registran cada evento (short/double/long/extra).

import _thread
import uasyncio as asyncio
from time import ticks_ms, sleep_ms

from HW import PAGE_BTN_PIN, UPDOWN_ADC_PIN, make_input, make_adc
from buttons import PageButton, UpDownButtons

AUTO_START = True


class _EventLog:
    def __init__(self):
        self.counts = {}

    def mark(self, name):
        n = self.counts.get(name, 0) + 1
        self.counts[name] = n
        print("[BTN] {:>12} #{:03d} @ {:d} ms".format(name, n, ticks_ms()))

    def snapshot(self):
        return dict(self.counts)


_log = _EventLog()
_loop_started = False


def _cb(name):
    def inner():
        _log.mark(name)
    return inner


async def _main_async():
    page_pin = make_input(PAGE_BTN_PIN)
    page_btn = PageButton(page_pin,
                          short=_cb("page_short"),
                          double=_cb("page_double"),
                          long=_cb("page_long"),
                          extra=_cb("page_extra"))
    asyncio.create_task(page_btn.task())

    adc_ud = make_adc(UPDOWN_ADC_PIN)
    ud_btns = UpDownButtons(
        adc_ud,
        up_short=_cb("up_short"),
        up_double=_cb("up_double"),
        up_long=_cb("up_long"),
        up_extra=_cb("up_extra"),
        down_short=_cb("down_short"),
        down_double=_cb("down_double"),
        down_long=_cb("down_long"),
        down_extra=_cb("down_extra"),
    )
    asyncio.create_task(ud_btns.task())

    print("[maintest_buttons] listo: prueba Page (short/doble/largo) y palanca UP/DOWN")
    while True:
        await asyncio.sleep(1)


def _bg():
    try:
        asyncio.run(_main_async())
    except Exception as exc:
        print("Loop error:", exc)
        sleep_ms(500)
    finally:
        global _loop_started
        _loop_started = False


def start():
    global _loop_started
    if _loop_started:
        print("[maintest_buttons] ya está en ejecución")
        return
    _loop_started = True
    _thread.start_new_thread(_bg, ())


def print_counts():
    snap = _log.snapshot()
    if not snap:
        print("[maintest_buttons] sin eventos aún")
        return
    for name in sorted(snap):
        print("[maintest_buttons] {:>12} => {:d}".format(name, snap[name]))


if AUTO_START:
    start()
