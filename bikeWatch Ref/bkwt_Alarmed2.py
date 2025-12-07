print(' ############## Importing bkwt_Alarmed2 from FS ############### ')

import lib_full as lib
import bkw
import fun


def wakeUpAlarmed2():  #entry function (no asyncio) to enter first asyncio one
    try:
        print('--->> init wakeUpAlarmed 2')
        fun.setMotionDetection() #activo las stats de motion/no motion
        bkw.sta_if.active(True) # activo el radio wifi en modo station
        bkw.memory['ram']['lastWifis'] = fun.wifisOnAir(5) # capturo los wifis iniciales
        bkw.memory["ram"]["awakeBlynkMsg"] = 1
        print('lanzo usyncio uasyncio.run(makeAsyncioLoopAlarmed2())')
        lib.uasyncio.run(makeAsyncioLoopAlarmed2())
    except Exception as err:
        print(err)
     
async def makeAsyncioLoopAlarmed2():
    lib.time.sleep(3) # espero un poco para darle tiempo al A9G a bootear
    i=1
    try:
        while fun.isA9Gconnected(5) is False:
            print('waiting for isA9Gconnected() is True, try#:', i+1)
            i += 1
            if i > 3: #si no logro conectar en las 10x 20 intentos, activo loopblynk Monitor  5 min y luego voy a  dormir 5 y reintento
                #To do, instead break, think a better alternative goSleep for 5 min and continue ?
                lib.uasyncio.create_task(loopBlynkMonitor(checkEach_s=5))
                lib.uasyncio.create_task(loopTrySMS(checkEach_s=1))
                await ActiveAlarmed(alarmedActive_m = 3, sleepAlarmed_m=20)
                break
        # task scheduller          
        print("sending location Msg #0")
        fun.sendLocationMsg()
        print('Running Alarmed loop')
        bkw.memory["ram"]["bootStatus"] = 'Alarmed'
        # task scheduller

        #lib.uasyncio.create_task(AlarmedBattery())
        lib.uasyncio.create_task(loop_garbageC(each_s=60))
        
        lib.uasyncio.create_task(loop_CheckOwnerIsNear(each_s=1))
        lib.uasyncio.create_task(loop_AlarmedLocation(periodLocation_s=bkw.config['Timers']['periodLocationA2_s']))
        await ActiveAlarmed(alarmedActive_m = bkw.config['Timers']['alarmedActive2_m'], sleepAlarmed_m=bkw.config['Timers']['alarmedSleep2_m'])  # when terminate async await goes sleep for SleepAlarmedTimer sleepTimeout_m

    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loopTrySMS(checkEach_s=1): #en caso que no conecte la red movil en los intentos iniciales, me quedo intando de conectar y enviar un par de SMS y ir a dormir 30m
    try:
        while True:
            if fun.isA9Gconnected(1):
                fun.sendLocationMsg()
                lib.time.sleep(10)
                fun.sendLocationMsg()
                fun.goSleepAlarmed(30)
            await lib.uasyncio.sleep(checkEach_s)

       #do it again
    except Exception as ex:
        print("Mira el error loopTrySMS()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        
async def loop_AlarmedLocation(periodLocation_s=60):
    try:
        lib.uasyncio.create_task(loopBlynkMonitor(checkEach_s=5))
        while True:
            await lib.uasyncio.sleep(periodLocation_s)
            print('sendLocationMsg() each {}sec, #{}'.format(periodLocation_s, bkw.memory["ram"]["smsPointIndex"]) )
            fun.sendLocationMsg()
        #do it again
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def ActiveAlarmed(alarmedActive_m = 2, sleepAlarmed_m=10):
    try:
        print("Active Alarmed for {}min, then goSleepAlarmed for {}min".format(alarmedActive_m, sleepAlarmed_m))
        alarmedActive_s = alarmedActive_m *60
        await lib.uasyncio.sleep(alarmedActive_s)
        print(" goSleepAlarmed {} minutos".format(sleepAlarmed_m))
        fun.goSleepAlarmed(sleepAlarmed_m)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loop_garbageC(each_s=60):
    try:
        #print('async loop_garbageC')
        while True:
            await lib.uasyncio.sleep(each_s)
            lib.gc.collect()
            print('mem free loop:',lib.gc.mem_free())
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loop_InboxSMS(each_ms=1000):
    try:
        #print('async loop_InboxSMS')
        while True:
            fun.SMScheck()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loopBlynkMonitor(checkEach_s=5):
    try:
        print('--->>look for home networks to Alarmed Config monitoring')
        isFirstSetup = False
        while True:
            try:
                if not bkw.sta_if.isconnected():
                    fun.tryHomeWifi()
                    if bkw.sta_if.isconnected() and isFirstSetup is False:
                        isFirstSetup = True
                        print('--->> loop_blynk,updateBlynkLoc,updateParamTab')
                        lib.uasyncio.create_task( loop_blynk(each_ms=200) )
                        lib.uasyncio.create_task(updateBlynkIds())
                        lib.uasyncio.create_task( updateBlynkStatusESP(each_s=1) )
                        lib.uasyncio.create_task( updateBlynkLoc(each_s=60) )
                        lib.uasyncio.create_task( updateBlynkStatusA9G(each_s=60) )
                        lib.uasyncio.create_task( updateBlynkConfig(each_ms=1000) )
            
            except Exception as err:
                print(err)
            
            await lib.uasyncio.sleep(checkEach_s)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loop_blynk(each_ms=500):
    try:
        while True:
            bkw.blynk.run()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def updateBlynkLoc(each_s=60):
    try:
        while True:
            print("updateBlynkLoc each {} seg".format(str(each_s)))
            fun.updateBlynkLoc()
            nextUpdateIn = int(each_s)
            print("updateBlynkLoc each {} secs".format(nextUpdateIn))
            await lib.uasyncio.sleep(nextUpdateIn)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)

async def updateBlynkStatusESP(each_s=1):
    try:
        while True:
            fun.updateBlynkStatusESP()
            await lib.uasyncio.sleep(each_s)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def updateBlynkStatusA9G(each_s=60):
    try:
        while True:
            fun.updateBlynkStatusA9G()
            await lib.uasyncio.sleep(each_s)
    except Exception as err:
        print(err)
        forever=999999
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
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loop_InboxSMS(each_ms=1000):
    try:
        #print('async loop_InboxSMS')
        while True:
            fun.SMScheck()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def loop_CheckOwnerIsNear(each_s=1):
    try:
        bkw.bikewatch_AP.active(True)   # activo y configuro el AP para desactivar si owner se conecta
        bkw.bikewatch_AP.config(essid=bkw.config['AP']['AP_name'], password=bkw.config['AP']['AP_pass'],authmode =3)
        print('checkOwnerIsNear() each',each_s,'seconds')
        while True:
            if fun.ownerIsNear():
                bkw.statusLed.init(period=100, mode=lib.machine.Timer.PERIODIC, callback=fun.toggle_led)
                volts, charge = fun.battery()
                msg = '{}| Bikewatch desactivado por presencia, carga: {}% ({}v)'.format(bkw.uid, charge, volts)
                print(msg)
                fun.sendSMS(msg)
                lib.time.sleep(5)
                fun.goSleepUnArmed(60*24)
            await lib.uasyncio.sleep(each_s)

    except Exception as err:
        print(err)
        forever=999999
        await lib.uasyncio.sleep(forever)
    
