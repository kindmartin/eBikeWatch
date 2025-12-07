print(' ############## Importing bkwt_Armed from FS ############### ')

import lib_full as lib
import bkw
import fun



def wakeUpArmed():  
    print('--->> init wakeUpArmed, if ok -->> fun.goSleepArmed(sleepTimeout_m)')
    print('')
    try:
        print('chequeo bateria if low envio mensaje')
        print('verifico wifi disponible, sincronizo timer, calculo proximo sleepTimeout 9pm de aviso')
        print('despues sigo durmiendo por armedSelfWakeTimer_m')
        volts, charge = fun.battery() 
        if charge < 40:
            lowBatMsg = 'bateria menor a 40%, cargar para poder funcionar en forma efectiva, carga actual: {}%'.format(str(charge))
            fun.sendSMS(lowBatMsg)
        else:
            Msg = 'Sigo Vigilando, carga actual: {}%'.format(str(charge))
            fun.sendSMS(Msg)
        #To do: calcular sleepTimeout_m
        
        fun.goSleepArmed(bkw.config['Timers']['armedSelfWakeTimer_m'])

    except Exception as err:
        print(err)


        
