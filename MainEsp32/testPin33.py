# testPin33.py
# Lee el valor ADC presente en GPIO33 una vez por segundo.

import time
from machine import ADC, Pin  # type: ignore

PIN_NUM = 33

from machine import ADC, Pin
adc = adc = ADC(Pin(33))
adc.atten(ADC.ATTN_6DB)
adc.width(ADC.WIDTH_12BIT)
adc.read()

def _make_adc(pin_num: int):
    adc = ADC(Pin(pin_num))
    try:
        adc.atten(ADC.ATTN_6DB)
        adc.width(ADC.WIDTH_12BIT)
    except Exception:
        pass
    return adc


def loop():
    adc = _make_adc(PIN_NUM)
    print("[testPin33] GPIO{} configurado como ADC".format(PIN_NUM))
    try:
        while True:
            raw = adc.read()
            print("[testPin33] raw = {}".format(raw))
            time.sleep(1)
    except KeyboardInterrupt:
        print("[testPin33] detenido por usuario")


def main():
    loop()


if __name__ == "__main__":
    main()



