print(' ############## Importing bkwt_Alarmed from FS ############### ')

import lib_full as lib
import bkw
import fun


def wakeUpAlarmed():  #entry function (no asyncio) to enter first asyncio one
    try:
        print('--->> init wakeUpAlarmed')
        
        print('calling owner and then start doing sms reports')
        fun.callOwner(callTimeOut_s=30)

        fun.setMotionDetection() #activo las stats de motion/no motion
        bkw.sta_if.active(True) # activo el radio wifi en modo station
        bkw.memory['ram']['lastWifis'] = fun.wifisOnAir(5) # capturo los wifis iniciales
        bkw.memory["ram"]["alarmedTimeZero"] = lib.time.time() # if alarmed, capture the alarmed T0 time
        bkw.memory["ram"]["smsPointIndex"] = 0
        bkw.memory["ram"]["awakeBlynkMsg"] = 1
        print('lanzo usyncio uasyncio.run(makeAsyncioLoopAlarmed())')
        lib.uasyncio.run(makeAsyncioLoopAlarmed())
    except Exception as ex:
        print("Mira el error wakeUpAlarmed()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        
async def makeAsyncioLoopAlarmed():
    try:
        print('Running Alarmed loop')
        bkw.memory["ram"]["bootStatus"] = 'Alarmed'
        bkw.memory["ram"]["wait2Call"] = 1
        for i in range(1000):
            if fun.isA9Gconnected() is not True:
                print('waiting for isA9Gconnected() is True, try#:', i)
            else:
                print('Connected in try#:', i)
                break
            if i== 200:  #si no logro conectar en las 200 intentos, activo loopblynk Monitor  2 min y luego voy a  dormir 5 y reintento
                        #To do, instead break, think a better alternative goSleep for 5 min and continue ?
                lib.uasyncio.create_task(loopBlynkMonitor(checkEach_s=5))
                lib.uasyncio.create_task(loopTrySMS(checkEach_s=5))
                await ActiveAlarmed(alarmedActive_m = 5, sleepAlarmed_m=2)
                
        # task scheduller
        lib.uasyncio.create_task(loop_garbageC(each_s=60))
        lib.uasyncio.create_task(loop_AlarmedLocation(periodLocation_s=bkw.config['Timers']['periodLocationA1_s']))
        lib.uasyncio.create_task(loop_CheckOwnerIsNear(each_s=1))
        await ActiveAlarmed(alarmedActive_m = bkw.config['Timers']['alarmedActive1_m'], sleepAlarmed_m=bkw.config['Timers']['alarmedSleep1_m'])   # when terminate async await goes sleep for SleepAlarmedTimer sleepTimeout_m
    except Exception as err:
        print(err)
        print("Hubo un error en makeAsyncioLoopAlarmed, voy a dormir un minuto y reinicio Alarmed2")
        sleepAlarmed_m = 1
        fun.goSleepAlarmed(sleepAlarmed_m)


async def loopTrySMS(checkEach_s=1): #en caso que no conecte la red movil en los intentos iniciales, me quedo intando de conectar y enviar un par de SMS y ir a dormir 1m
    try:
        while True:
            if fun.isA9Gconnected(1):
                fun.sendLocationMsg()
                lib.time.sleep(10)
                fun.sendLocationMsg()
                fun.goSleepAlarmed(1)
            await lib.uasyncio.sleep(checkEach_s)

       #do it again
    except Exception as ex:
        print("Mira el error loopTrySMS()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
                    
async def loop_AlarmedLocation(periodLocation_s=240):
    try:
        print('fun.sendLocationMsg() #0')
        fun.sendLocationMsg() # send first alarmed SMS 
        bkw.memory["ram"]["wait2Call"] = 0 # allow the callAfterSMS
        lib.uasyncio.create_task(loopBlynkMonitor(checkEach_s=5))
        await lib.uasyncio.sleep(30) # wait for 1 minute****************************
        while True:
            await lib.uasyncio.sleep(periodLocation_s)
            print('sendLocationMsg() each {}sec, #{}'.format(periodLocation_s, bkw.memory["ram"]["smsPointIndex"]) )
            fun.sendLocationMsg() # send n in loop alarmed SMS
            
        #do it again
    except Exception as ex:
        print("Mira el error loop_AlarmedLocation()")
        print("==>>>")
        print(ex) 
        print("^^^^^")  
        
async def callAfterSMS(callAfter_s=5):
    try:
        print('Waiting 1st SMS to call')
        while bkw.memory["ram"]["wait2Call"] == 1: #block calls loop until wait to call is 0
            await lib.uasyncio.sleep(1)
        await lib.uasyncio.sleep(callAfter_s)
        print('Calling Owner')
        fun.callOwner(callTimeOut_s=20)
        bkw.memory["ram"]["wait2Call"] =1 #block new calls
        forever=999999
        await lib.uasyncio.sleep(forever)
    except Exception as ex:
        print("Mira el error callAfterSMS()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def ActiveAlarmed(alarmedActive_m = 4, sleepAlarmed_m=15):
    try:
        print("Active Alarmed for {}min, then goSleepAlarmed for {}min".format(alarmedActive_m, sleepAlarmed_m))
        alarmedActive_s = alarmedActive_m *60
        await lib.uasyncio.sleep(alarmedActive_s)
        print("alarmedActive_s expire, now goSleepAlarmed for {}min".format(sleepAlarmed_m))
        bkw.memory["ram"]["awakeBlynkMsg"] = 0
        await lib.uasyncio.sleep(5) # le doy tiempo para actualizar el ultimo blynk
        fun.goSleepAlarmed(sleepAlarmed_m)
    except Exception as err:
        print(err)
        print("Hubo un error en ActiveAlarmed, voy a dormir un minuto y reinicio Alarmed2")
        sleepAlarmed_m = 1
        fun.goSleepAlarmed(sleepAlarmed_m)
        
async def loop_garbageC(each_s=60):
    try:
        #print('async loop_garbageC')
        while True:
            await lib.uasyncio.sleep(each_s)
            lib.gc.collect()
            print('mem free loop:',lib.gc.mem_free())
    except Exception as err:
        print(err)
        print("Hubo un error en loop_garbageC, voy a dormir un minuto y reinicio Alarmed2")
        sleepAlarmed_m = 1
        fun.goSleepAlarmed(sleepAlarmed_m)

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
                        lib.uasyncio.create_task( updateBlynkIds())
                        lib.uasyncio.create_task( updateBlynkLoc(each_s=60 ) )
                        lib.uasyncio.create_task( updateBlynkStatusA9G(each_s=60) )
                        lib.uasyncio.create_task( updateBlynkStatusESP(each_s=1) )
                        lib.uasyncio.create_task( updateBlynkConfig(each_s=5) )

            except Exception as err:
                print(err)
            
            await lib.uasyncio.sleep(checkEach_s)
    except Exception as ex:
        print("Mira el error loopBlynkMonitor()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loop_blynk(each_ms=500):
    try:
        while True:
            bkw.blynk.run()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as ex:
        print("Mira el error loop_blynk()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def updateBlynkLoc(each_s=60):
    try:
        while True:
            print("updateBlynkLoc now ")
            fun.updateBlynkLoc()
            nextUpdateIn = int(each_s)
            print("updateBlynkLoc each {} secs".format(nextUpdateIn))
            await lib.uasyncio.sleep(nextUpdateIn)
    except Exception as ex:
        print("Mira el error updateBlynkLoc()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        forever=999999
        await lib.uasyncio.sleep(forever)

async def updateBlynkStatusESP(each_s=1):
    try:
        while True:
            fun.updateBlynkStatusESP()
            await lib.uasyncio.sleep(each_s)
    except Exception as ex:
        print("Mira el error updateBlynkStatusESP()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        forever=999999
        await lib.uasyncio.sleep(forever)
        
async def updateBlynkStatusA9G(each_s=60):
    try:
        while True:
            fun.updateBlynkStatusA9G()
            await lib.uasyncio.sleep(each_s)
    except Exception as ex:
        print("Mira el error updateBlynkStatusA9G()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
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

async def updateBlynkConfig(each_s=60):
    bkw.memory["ram"]["configChanged"] = 1
    try:
        while True:
            fun.updateBlynkConfig()      
            await lib.uasyncio.sleep(each_s)
    except Exception as ex:
        print("Mira el error updateBlynkConfig()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        forever=999999
        await lib.uasyncio.sleep(forever)

async def loop_InboxSMS(each_ms=1000):
    try:
        #print('async loop_InboxSMS')
        while True:
            fun.SMScheck()
            await lib.uasyncio.sleep_ms(each_ms)
    except Exception as ex:
        print("Mira el error loop_InboxSMS()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        print("Hubo un error en loop_InboxSMS, voy a dormir un minuto y reinicio Alarmed2")
        sleepAlarmed_m = 1
        fun.goSleepAlarmed(sleepAlarmed_m)

async def loop_CheckOwnerIsNear(each_s=1):
    try:
        bkw.bikewatch_AP.active(True)   # activo y configuro el AP para desactivar si owner se conecta
        bkw.bikewatch_AP.config(essid=bkw.config['AP']['AP_name'], password=bkw.config['AP']['AP_pass'],authmode =3)
        print('checkOwnerIsNear() each',each_s,'seconds')
        while True:
            if fun.ownerIsNear():
                bkw.statusLed.init(period=500, mode=lib.machine.Timer.PERIODIC, callback=fun.toggle_led)
                volts, charge = fun.battery()
                msg = '{}| Bikewatch desactivado por presencia, carga: {}% ({}v)'.format(bkw.uid, charge, volts)
                print(msg)
                fun.sendSMS(msg)
                lib.time.sleep(5)
                fun.goSleepUnArmed(60*24)
            await lib.uasyncio.sleep(each_s)

    except Exception as ex:
        print("Mira el error loop_CheckOwnerIsNear()")
        print("==>>>")
        print(ex) 
        print("^^^^^")
        print("Hubo un error en loop_CheckOwnerIsNear, voy a dormir un minuto y reinicio Alarmed2")
        sleepAlarmed_m = 1
        fun.goSleepAlarmed(sleepAlarmed_m)
