print(' ############## Importing postBoot from FS ############### ')
import lib_full as lib
import bkw
import fun

#lib.uos.dupterm(fun.logToFile())

# Initial sets
bkw.memory['ram']['lastWifis'] = fun.wifisOnAir(maxReturn_W=6)
#fun.motionDetection()

# extreme low battery check
if fun.battery()[0] < 3.5: #si hay menos de 3.5volts, aviso y apago
    print("Extreme low battery, {}v".format(fun.battery()[0]))
    print("trying to send SMS low batt and going Sleep until Touch")
    volts, charge = fun.battery()
    msg = '{}| Bikewatch desactivado por muy baja carga, {}% ({}v)'.format(bkw.uid, charge, volts)
    print(msg)
    fun.sendSMS(msg)
    fun.lib.time.sleep(5)
    fun.goSleepUnArmed(60*24*1)   #un dia

print( '' )

#bkw.statusLed.init(period=100, mode=lib.machine.Timer.PERIODIC, callback=fun.toggle_led)
lib._thread.stack_size(5*1024)
lib._thread.start_new_thread(fun.A9G_Serial,(1,)) #start_new_thread req tuple if functions needs argument/s, so if one, need follow to a ,
#lib._thread.start_new_thread(fun.A9G_EN,(1,))
print('--->> postBoot, enabling serial and booting A9G')
print( '' )
lib.time.sleep(1)

if lib.machine.wake_reason() == 0: #PowerOn
    print('lib.machine.wake_reason() == 0 --> PowerOn()')
    bkw.statusLed.init(period=30, mode=lib.machine.Timer.PERIODIC, callback=fun.toggle_led)
    import bkwt_PowerOn
    lib._thread.stack_size(10*1024)
    lib._thread.start_new_thread(bkwt_PowerOn.PowerOn,())    

if lib.machine.wake_reason() == 2: #ext0
    print('lib.machine.wake_reason() == 2 --> wakeUpBySensor()')
    print('bkwtAlarmed.wakeUpAlarmed')
    import bkwt_Alarmed
    lib._thread.stack_size(10*1024)
    lib._thread.start_new_thread(bkwt_Alarmed.wakeUpAlarmed,())

if lib.machine.wake_reason() == 3: #ext1 go2Armed (boton)
    print('lib.machine.wake_reason() == 3 --> buttonActioned()')

    if bkw.rtcmem['bootStatus'] == 'Alarmed' or bkw.rtcmem['bootStatus'] == 'Armed' :
        print('booted by buton and alarmed or Armed' )
        print('---->> bkwtAlarmed2.wakeUpAlarmed')
        import bkwt_Alarmed2
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_Alarmed2.wakeUpAlarmed2,())

    if bkw.rtcmem['bootStatus'] == 'UnArmed':
        print('booted by buton and UnArmed' )
        print('bkwt_UnArmed.Actioned2goArmed')
        import bkwt_goArmed
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_goArmed.Actioned2goArmed,())  

if lib.machine.wake_reason() == 5: #Touch makeReport and sleep
    print('lib.machine.wake_reason() == 5 --> touchActioned()')
    print('bkwtWatching.touchActioned')
    if bkw.rtcmem['bootStatus'] == 'Alarmed'  or bkw.rtcmem['bootStatus'] == 'Armed':
        print('boot by touch and alarmed/Armed' )
        print('bkwtAlarmed2.wakeUpAlarmed')
        import bkwt_Alarmed2
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_Alarmed2.wakeUpAlarmed2,())

    if bkw.rtcmem['bootStatus'] == 'UnArmed':
        print('boot by touch and UnArmed' )
        print('bkwt_UnArmed.wakeUpUnArmed')
        import bkwt_UnArmed
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_UnArmed.wakeUpUnArmed,())


if lib.machine.wake_reason() == 4: # Timer
    print('lib.machine.wake_reason() == 4, --> wakeUpByTimer()')
    #to do: diferenciate timerwakeup PowerOn vs daily check vs Alarmed bat Save
    if bkw.rtcmem['bootStatus'] == 'Alarmed':
        print('boot by timer and alarmed' )
        print('bkwtAlarmed2.wakeUpAlarmed')
        import bkwt_Alarmed2
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_Alarmed2.wakeUpAlarmed2,())

    if bkw.rtcmem['bootStatus'] == 'UnArmed':
        print('boot by timer and UnArmed' )
        print('bkwt_UnArmed.wakeUpUnArmed')
        import bkwt_UnArmed
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_UnArmed.wakeUpUnArmed,())

    if bkw.rtcmem['bootStatus'] == 'Armed':
        print('boot by timer and Armed' )
        print('bkwt_Armed.wakeUpArmed')
        import bkwt_Armed
        lib._thread.stack_size(10*1024)
        lib._thread.start_new_thread(bkwt_Armed.wakeUpArmed,())        
