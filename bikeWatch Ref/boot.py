# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(0)  # redirect vendor O/S debugging messages to UART(0) / None ::turn off 

print(' ############## Importing boot from FS ############### ')

import time, machine
A9G_power = machine.Pin(14, machine.Pin.OUT, machine.Pin.PULL_UP)
A9G_power.value(0)
time.sleep(3)
A9G_power.value(1)

import sys # sys.path ['', '/lib']
import lib_full as lib
import fun
import bkw


print('=====>>>> thisBootMode ::', bkw.memory["ram"]["thisBootMode"])

def boot(nextBootMode=None):
    if bkw.memory["ram"]["thisBootMode"] is None: # boot() -> normal
        nextBootMode ='normal'
        bootRTC_JSON = {'nextBootMode':'normal'}
        bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM
    else:
        nextBootMode = str(nextBootMode)
        if nextBootMode == 'skipMain' or nextBootMode == '0':
            nextBootMode ='skipMain(0)'
            bootRTC_JSON = {'nextBootMode':'skipMain'}
            bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM 
        if nextBootMode == 'reset' or nextBootMode == '1':
            print('==>> reboot {}  -->> machine.reset()'.format(nextBootMode))
            lib.time.sleep(2)
            lib.machine.reset()
        if nextBootMode == 'normal()':
            nextBootMode ='normal'
            bootRTC_JSON = {'nextBootMode':'normal'}
            bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM
        if nextBootMode == 'net' or nextBootMode == '2':
            nextBootMode ='net(2)'
            bootRTC_JSON = {'nextBootMode':'net0'}
            bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM    
 
    print('==>> Next boot -->> {}'.format(nextBootMode))
    lib.machine.deepsleep(10)

bkw.p39 = lib.machine.Pin(39, lib.machine.Pin.IN) #, lib.machine.Pin.DOWN) 
if bkw.p39.value() == 1:
    boot('net')

if  bkw.memory["ram"]["thisBootMode"] == 'normal':
    import postBoot

if  bkw.memory["ram"]["thisBootMode"]  == 'net0':
    import net

if  bkw.memory["ram"]["thisBootMode"]  == 'skipMain':
    import forceBootError
    

