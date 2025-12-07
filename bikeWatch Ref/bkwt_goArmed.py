print(' ############## Importing bkwt_goArmed from FS ############### ')

import lib_full as lib
import bkw
import fun

def Actioned2goArmed():  #entry function (no asyncio) 
    try:
        print('--->> init Standby-->> Armed / Vigilando fun.Actioned2goArmed(24*60)')
        print('')
        armedSelfWakeTimer_m = bkw.config['Timers']['armedSelfWakeTimer_m']
        fun.Actioned2goArmed(armedSelfWakeTimer_m)
    except Exception as err:
        print(err)
        
