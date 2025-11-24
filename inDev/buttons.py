# buttons.py
import uasyncio as asyncio
import time

DEBUG = True

DEFAULT_THRESHOLDS = {"UP_MAX": 50, "DOWN_MAX": 1700}
DEFAULT_TIMINGS = {
    "DEBOUNCE_MS":   5,
    "RELEASE_MS":    40,
    "DOUBLE_MS":     280,
    "LONG_MS":       1200,
    "EXTRA_LONG_MS": 2500,
    "ADC_PERIOD_MS": 20,
}
PAGE_DEFAULTS = {
    "SHORT_MS": 420,
    "LONG_MS": 1200,
    "EXTRA_MS": 2200,
    "DOUBLE_MS": 320,
    "POLL_MS": 20,
}

IDLE, UP, DOWN = 0, 1, 2

def _ticks():
    return time.ticks_ms()

def _diff(a, b):
    return time.ticks_diff(a, b)

if hasattr(time, "ticks_add"):
    _TICKS_ADD = time.ticks_add
else:
    def _fallback_ticks_add(base, delta):
        return (base + delta) & 0x7FFFFFFF

    _TICKS_ADD = _fallback_ticks_add


def _ticks_add(base, delta):
    return _TICKS_ADD(base, delta)

class PageButton:
    def __init__(
        self,
        pin_in,
        *,
        short=lambda: None,
        double=lambda: None,
        long=lambda: None,
        extra=lambda: None,
        timings=None,
        label="Page",
    ):
        self.pin = pin_in
        self.cb_short = short
        self.cb_double = double
        self.cb_long = long
        self.cb_extra = extra
        self.t = PAGE_DEFAULTS.copy()
        self.t.update(timings or {})
        self.label = label

        self._is_pressed = False
        self._press_started = 0
        self._pending_clicks = 0
        self._pending_deadline = None

    def _fire(self, kind, callback):
        if DEBUG:
            now = _ticks()
            duration = 0
            if self._press_started:
                try:
                    duration = _diff(now, self._press_started)
                except Exception:
                    duration = 0
            print("[{}] {:>6}ms {}".format(self.label, duration, kind))
        else:
            print("[{}] {} pressed".format(self.label, kind))
        if callable(callback):
            callback()

    async def task(self):
        poll_ms = max(5, int(self.t.get("POLL_MS", 20)))
        double_ms = int(self.t.get("DOUBLE_MS", PAGE_DEFAULTS["DOUBLE_MS"]))
        short_ms = int(self.t.get("SHORT_MS", PAGE_DEFAULTS["SHORT_MS"]))
        long_ms = int(self.t.get("LONG_MS", PAGE_DEFAULTS["LONG_MS"]))
        extra_ms = int(self.t.get("EXTRA_MS", PAGE_DEFAULTS["EXTRA_MS"]))

        while True:
            now = _ticks()
            value = self.pin.value()

            if value == 0 and not self._is_pressed:
                self._is_pressed = True
                self._press_started = now

            if value == 1 and self._is_pressed:
                self._is_pressed = False
                duration = _diff(now, self._press_started)

                if duration >= extra_ms:
                    self._fire("extra", self.cb_extra)
                    self._pending_clicks = 0
                    self._pending_deadline = None
                elif duration >= long_ms:
                    self._fire("long", self.cb_long)
                    self._pending_clicks = 0
                    self._pending_deadline = None
                else:
                    self._pending_clicks += 1
                    if self._pending_clicks == 1:
                        self._pending_deadline = _ticks_add(now, double_ms)
                    else:
                        if self._pending_deadline is not None and _diff(self._pending_deadline, now) > 0:
                            self._fire("double", self.cb_double)
                            self._pending_clicks = 0
                            self._pending_deadline = None
                        else:
                            self._fire("short", self.cb_short)
                            self._pending_clicks = 1
                            self._pending_deadline = _ticks_add(now, double_ms)

            if self._pending_clicks == 1 and self._pending_deadline is not None:
                if _diff(now, self._pending_deadline) >= 0:
                    self._fire("short", self.cb_short)
                    self._pending_clicks = 0
                    self._pending_deadline = None

            await asyncio.sleep_ms(poll_ms)

class UpDownButtons:
    def __init__(self, adc,
                 *, up_short=lambda: None, up_double=lambda: None, up_long=lambda: None, up_extra=lambda: None,
                    down_short=lambda: None, down_double=lambda: None, down_long=lambda: None, down_extra=lambda: None,
                 thresholds=None, timings=None, label_up="Up", label_down="Down"):
        self.adc = adc

        th = DEFAULT_THRESHOLDS.copy(); th.update(thresholds or {})
        ti = DEFAULT_TIMINGS.copy(); ti.update(timings or {})

        self.UP_MAX        = th["UP_MAX"]
        self.DOWN_MAX      = th["DOWN_MAX"]
        self.DEBOUNCE_MS   = ti["DEBOUNCE_MS"]
        self.RELEASE_MS    = ti["RELEASE_MS"]
        self.DOUBLE_MS     = ti["DOUBLE_MS"]
        self.LONG_MS       = ti["LONG_MS"]
        self.EXTRA_LONG_MS = ti["EXTRA_LONG_MS"]
        self.ADC_PERIOD_MS = ti["ADC_PERIOD_MS"]

        self.cb_up_short   = up_short
        self.cb_up_double  = up_double
        self.cb_up_long    = up_long
        self.cb_up_extra   = up_extra
        self.cb_down_short  = down_short
        self.cb_down_double = down_double
        self.cb_down_long   = down_long
        self.cb_down_extra  = down_extra
        self.label_up = label_up
        self.label_down = label_down

    def _fire(self, label, kind, callback):
        if DEBUG:
            stamp = _ticks()
            print("[{}] {} @{}".format(label, kind, stamp))
        else:
            print("[{}] {} pressed".format(label, kind))
        if callable(callback):
            callback()

    def _get_state(self, raw):
        if raw <= self.UP_MAX:
            return UP
        if raw <= self.DOWN_MAX:
            return DOWN
        return IDLE

    async def _debounced_press(self, expect_state):
        t0 = _ticks()
        while _diff(_ticks(), t0) < self.DEBOUNCE_MS:
            if self._get_state(self.adc.read()) != expect_state:
                return False
            await asyncio.sleep_ms(self.ADC_PERIOD_MS)
        return True

    async def _measure_press(self, active_state):
        t0 = _ticks()
        while True:
            s = self._get_state(self.adc.read())
            if s == IDLE:
                t_rel = _ticks()
                ok = True
                while _diff(_ticks(), t_rel) < self.RELEASE_MS:
                    if self._get_state(self.adc.read()) != IDLE:
                        ok = False
                        break
                    await asyncio.sleep_ms(self.ADC_PERIOD_MS)
                if ok:
                    dur = _diff(_ticks(), t0)
                    return dur
            await asyncio.sleep_ms(self.ADC_PERIOD_MS)

    async def _double_window(self, same_state):
        t_rel = _ticks()
        while _diff(_ticks(), t_rel) < self.RELEASE_MS:
            if self._get_state(self.adc.read()) != IDLE:
                t_rel = _ticks()
            await asyncio.sleep_ms(self.ADC_PERIOD_MS)

        t0 = _ticks()
        while _diff(_ticks(), t0) < self.DOUBLE_MS:
            if self._get_state(self.adc.read()) == same_state:
                if not await self._debounced_press(same_state):
                    continue
                dur2 = await self._measure_press(same_state)
                if dur2 >= self.LONG_MS:
                    return 2
                return 1
            await asyncio.sleep_ms(self.ADC_PERIOD_MS)
        return 0

    async def task(self):
        while True:
            state = self._get_state(self.adc.read())

            if state == IDLE:
                await asyncio.sleep_ms(self.ADC_PERIOD_MS)
                continue

            if not await self._debounced_press(state):
                await asyncio.sleep_ms(self.ADC_PERIOD_MS)
                continue

            dur = await self._measure_press(state)

            label = self.label_up if state == UP else self.label_down
            if dur >= self.EXTRA_LONG_MS:
                cb = self.cb_up_extra if state == UP else self.cb_down_extra
                self._fire(label, "extra", cb)
            elif dur >= self.LONG_MS:
                cb = self.cb_up_long if state == UP else self.cb_down_long
                self._fire(label, "long", cb)
            else:
                res = await self._double_window(state)
                if res == 1:
                    cb = self.cb_up_double if state == UP else self.cb_down_double
                    self._fire(label, "double", cb)
                elif res == 2:
                    cb = self.cb_up_long if state == UP else self.cb_down_long
                    self._fire(label, "long", cb)
                else:
                    cb = self.cb_up_short if state == UP else self.cb_down_short
                    self._fire(label, "short", cb)
            await asyncio.sleep_ms(self.ADC_PERIOD_MS)
