guidelines



Pautas del proyecto
Arquitectura y ejecución

- Arquitectura modular: separar por responsabilidades (HW, UI LCD, botones, tareas principales/secundarias).
- Entrypoint manual: `runbg.py` expone `start_background()` e importa `t.start()` (hay shim `maintest2o` para compatibilidad).
- Entrypoint estable: `main.py` debe delegar en `runbg.start_background()` cuando el flujo esté validado.
- Loop asíncrono: usar `uasyncio` en un hilo background (`_thread`) para mantener libre el REPL.
- Autoarranque: el módulo principal se autoarranca al importar, pero siempre en segundo plano.
- No bloquear: evitar llamadas bloqueantes dentro de tareas; si son inevitables, encapsularlas y espaciarlas.

Estilo de código

- Sin IRQs: manejar entradas con polling + debounce (ver `buttons.py`).
- Evitar lambdas y flujos complejos: preferir funciones con nombre y lógica clara.
- Simplicidad ante todo: no introducir capas/abstracciones innecesarias.
- Eficiencia: reutilizar helpers existentes en vez de duplicar lógica.
- Depuración simple: heartbeats/prints opcionales, fácilmente activables.

Módulos base (respetar y reutilizar)

- `HW.py`: fuente de verdad para pines, SPI/I2C, ADC, UART y helpers `make_*`.
- `drivers/`: contiene los controladores de hardware (p. ej. `lcd1p69.py`, `mcp4725.py`).
- `UI_helpers/`: fachada LCD (`ui_display.py`), demos (`maintest_lcd.py`) y helpers de dibujo.
- `fonts/`: utilidades de dibujo (`big_digits.py`, `sevenSegment_XX.py`).
- `bats.py`: metadatos de packs y cálculo lineal de SoC.
- `phaserunner/`: integración Modbus (core, UART probe, registros, monitores).
- `pic/`: sprites y bitmaps (`bat_chging.py`).
- `buttons.py`: semántica Page/Up/Down (`short/double/long/extra`).

Entradas / Botones

- Sin IRQs: la lectura se hace por polling (digital + ADC según `buttons.py`).
- Respetar callbacks existentes: mantener mapeo short/double/long/extra.
- Acciones configurables: el “page corto cambia pantalla” es el comportamiento por defecto.

LCD ST7789

- Todos los dibujos pasan por `DisplayUI`; evitar tocar el driver directamente.
- El framebuffer es RGB565 pero se usa como monocromo vía `_MonoAdapter`.
- Reutilizar `fonts.big_digits.draw_digit` para los números grandes (velocidad/potencia).




import machine, time; u = machine.UART(1, 115200, tx=13, rx=15, timeout=100)
import machine, time; u = machine.UART(1, 115200, tx=15, rx=13, timeout=100)

u.write(str(time.time()) + "\n")
print(u.readline())

main - off

RX 13 <-> 5 TX
TX 15 <-> 4 RX


import machine, time; u = machine.UART(1, 115200, tx=4, rx=5, timeout=100) #da perror
import machine, time; u = machine.UART(1, 115200, tx=5, rx=4, timeout=100) #da ok


u.write(str(time.time()) + "\n")
print(u.readline())


import machine, time; u = machine.UART(2, 115200, tx=25, rx=27, timeout=100)

import machine, time; u = machine.UART(2, 115200, tx=27, rx=25, timeout=100)

PR_UART_TX = 25  # Drives the Phaserunner RX line
PR_UART_RX = 27  # Reads from the Phaserunner TX line