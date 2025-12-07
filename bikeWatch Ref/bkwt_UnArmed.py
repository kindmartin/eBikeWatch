print(' ############## Importing bkwt_Alarmed from FS ############### ')

import lib_full as lib
import bkw
import fun



def wakeUpUnArmed():  
    print('--->> init wakeUpUnArmed')
    print('')
    bkw.statusLed.init(period=30, mode=lib.machine.Timer.PERIODIC, callback=fun.toggle_led)
    try:
        print('chequeo bateria, if low envio mensaje')
        volts, charge = fun.battery() 
        if charge < 30:
            lowBatMsg = 'bateria menor a 30%!, cargame para ser util, carga actual: {}%'.format(str(charge))
            fun.sendSMS(lowBatMsg)
        i=1
        lib.time.sleep(3) # espero un poco para darle tiempo al A9G a bootear
        while fun.isA9Gconnected(5) is False:
            print('waiting for isA9Gconnected() is True, try#:', i+1)
            lib.time.sleep(1)
            i += 1
            if i > 20: #si no logro conectar en las 10x 20 intentos, activo loopblynk Monitor  5 min y luego voy a  dormir 60 y reintento
                #To do, instead break, think a better alternative goSleep for 5 min and continue ?
                fun.goSleepUnArmed(60) #60 minutos

        print('fun.sendLocationMsg() not Alarmed')
        fun.sendLocationMsg()
        lib.uasyncio.run(makeAsyncioLoop())
    
    except Exception as err:
        print(err)


async def makeAsyncioLoop():
    try:
        bkw.statusLed.init(period=300, mode=lib.machine.Timer.PERIODIC, callback=fun.toggle_led)
        print('--->> makeAsyncioLoop')
        print(
            '--->>look for home networks for Blynk monitoring, clock sync and check updates')

        fun.tryHomeWifi()
        if bkw.sta_if.isconnected():
            # estimo boot time dado un posible ajuste via ntp
            bkw.memory["ram"]["bootTime"] = lib.time.time() - 5
            print('Adding to asyncio loop >> loop_blynk,updateBlynkLoc,updateBlynkConfig')
            lib.uasyncio.create_task(loop_blynk(each_ms=200))
            lib.uasyncio.create_task(updateBlynkIds())
            lib.uasyncio.create_task(updateBlynkStatusESP(each_s=1))
            lib.uasyncio.create_task(updateBlynkStatusA9G(each_s=60))
            lib.uasyncio.create_task(updateBlynkLoc(each_s= bkw.config['Timers']['periodLocationR1_s']))
            lib.uasyncio.create_task(updateBlynkConfig(each_ms=1000))
        else:
            print('===>> No home wifi available')

        volts, charge = fun.battery()
        print('bkw ID {}| Apretar el boton para iniciar en bkw Armed, carga: {}% ({}v)'.format(
            bkw.uid, charge, volts))
        bkw.p39.irq(handler=p39int, trigger=lib.machine.Pin.IRQ_RISING)
        print(' Now running background tasks')
        #lib.uasyncio.create_task( loop_InboxSMS(each_ms=500) )

        # first task in n tasks, never terminates periodLocationR1_s
        lib.uasyncio.create_task(goSleepAfterReport(timeout_m = bkw.UnArmed_Timeout_m))
        await loop_garbageC(each_s=300)

    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


async def goSleepAfterReport(timeout_m=3):
    try:
        print('goSleepAfterReport in {}m'.format(timeout_m))
        timeout_s = timeout_m *60
        await lib.uasyncio.sleep(timeout_s)
        #Todo calcular sleepTimeout_m
        unArmedSelfWakeTimer_m = bkw.config['Timers']['unArmedSelfWakeTimer_m']
        fun.goSleepUnArmed(unArmedSelfWakeTimer_m)

    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)

async def loop_blynk(each_ms=500):
    try:
        while True:
            bkw.blynk.run()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


async def updateBlynkLoc(each_s=600):
    try:
        #bkw.blynk.virtual_write(101, "clr")  # limpio el mapa
        while True:
            print("updateBlynkLoc each {} seg".format(str(each_s)))
            fun.updateBlynkLoc()
            nextUpdateIn = int(each_s)
            print("updateBlynkLoc each {} secs".format(nextUpdateIn))
            await lib.uasyncio.sleep(nextUpdateIn)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


async def updateBlynkStatusESP(each_s=1):
    try:
        while True:
            fun.updateBlynkStatusESP()
            await lib.uasyncio.sleep(each_s)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


async def updateBlynkStatusA9G(each_s=60):
    try:
        while True:
            fun.updateBlynkStatusA9G()
            await lib.uasyncio.sleep(each_s)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)

async def updateBlynkIds():
    try:
        fun.updateBlynkIds()
        forever = 999999
        await lib.uasyncio.sleep(999999)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)  

async def updateBlynkConfig(each_ms=500):
    try:
        bkw.memory["ram"]["configChanged"] = 1
        while True:
            fun.updateBlynkConfig()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


async def loop_garbageC(each_s=60):
    try:
        while True:
            #print('async loop_garbageC')
            await lib.uasyncio.sleep(each_s)
            lib.gc.collect()
            print('mem free loop each {}s, now {} free:'.format(
                each_s, lib.gc.mem_free()))
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


async def loop_InboxSMS(each_ms=500):
    try:
        #print('async loop_InboxSMS')
        while True:
            fun.SMScheck()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as err:
        print(err)
        forever = 999999
        await lib.uasyncio.sleep(forever)


def p39int(Pin):  # solo util from PowerOn o un estado awake
    print('boton en Pin(39) accionado, preparo goSleepdArmed()')
    fun.buttonActioned(bkw.config['Timers']['armedSelfWakeTimer_m'])

        
