print(' ############## Importing fun from FS ############### ')

import lib_full as lib
import bkw


#        lib._thread.stack_size(10*1024)
#        lib._thread.start_new_thread(fun.statusLed,())
#bkw.memory["ram"]["statusLed_Blinks"] = 3
#bkw.memory["ram"]["statusLed_Duration_ms"] = 2000
#bkw.memory["ram"]["statusLed_waits_ms"] = 1000

def statusLed():
    try:
        while True:
            blinkOnTime_ms = int(bkw.memory["ram"]["statusLed_Duration_ms"]/bkw.memory["ram"]["statusLed_Blinks"]) - 100
            for b in range(0, bkw.memory["ram"]["statusLed_Blinks"]):
                lib.time.sleep_ms(100)
                bkw.led(1)
                lib.time.sleep_ms(blinkOnTime_ms)
                bkw.led(0)
            lib.time.sleep_ms(bkw.memory["ram"]["statusLed_waits_ms"])   
    except KeyboardInterrupt:
        print('Got ctrl-c')
        raise
            
# log serial console to file. 
# starts           --> lib.uos.dupterm(logToFile())
# stops /close log --> lib.uos.dupterm(None)

class logToFile(lib.io.IOBase):
    def __init__(self):
        pass

    def write(self, data):
        with open("logfile.txt", mode="a") as f: #no buffer instead use f.flush()
            f.write(data)
            f.flush()
        return len(data)
         
## const
#regNames = ['bkw.A_STATUS_MMA8452Q','bkw.A_OUT_X_MSB','bkw.A_OUT_X_LSB','bkw.A_OUT_Y_MSB','bkw.A_OUT_Y_LSB','bkw.A_OUT_Z_MSB','bkw.A_OUT_Z_LSB','bkw.A_SYSMOD','bkw.A_INT_SOURCE','bkw.A_WHO_AM_I','bkw.A_XYZ_DATA_CFG','bkw.A_HP_FILTER_CUTOFF','bkw.A_PL_STATUS','bkw.A_PL_CFG','bkw.A_PL_COUNT','bkw.A_PL_BF_ZCOMP','bkw.A_P_L_THS_REG','bkw.A_FF_MT_CFG','bkw.A_FF_MT_SRC','bkw.A_FF_MT_THS','bkw.A_FF_MT_COUNT','bkw.A_TRANSIENT_CFG','bkw.A_TRANSIENT_SRC','bkw.A_TRANSIENT_THS','bkw.A_TRANSIENT_COUNT','bkw.A_PULSE_CFG','bkw.A_PULSE_SRC','bkw.A_PULSE_THSX','bkw.A_PULSE_THSY','bkw.A_PULSE_THSZ','bkw.A_PULSE_TMLT','bkw.A_PULSE_LTCY','bkw.A_PULSE_WIND','bkw.A_ASLP_COUNT','bkw.A_CTRL_REG1','bkw.A_CTRL_REG2','bkw.A_CTRL_REG3','bkw.A_CTRL_REG4','bkw.A_CTRL_REG5','bkw.A_OFF_X','bkw.A_OFF_Y','bkw.A_OFF_Z']
#regNum = ['0','1','2','3','4','5','6','11','12','13','14','15','16','17','18','19','20','21','22','23','24','29','30','31','32','33','34','35','36','37','38','39','40','41','42','43','44','45','46','47','48','49']
#bus = lib.machine.I2C(0)
#def regMMA():
#    for r in range(len(regNum)):
#        print('#{0:>2} REG {1:<18} {2:>4} ({3:>2}d) ==>> / 0x{5:>2} / {6:>10} / {4:>2}'.format(r+1, regNames[r], hex(int(regNum[r])), regNum[r], bkw.busI2C.readfrom_mem(bkw.A_ADDRESS,int(regNum[r]),1) , lib.ubinascii.hexlify(bkw.busI2C.readfrom_mem(bkw.A_ADDRESS,int(regNum[r]),1)), bin(int(lib.ubinascii.hexlify(bkw.busI2C.readfrom_mem(bkw.A_ADDRESS,int(regNum[r]),1)),16))  ))
#
#def hex2bin(hexa):
#    print('bit 76543210')
#    bits = bin(int(hexa,16))
#    byte = ''
#    for z in range( 10-len(bits)):
#        byte = byte + '0'
#    for b in range(len(bits)-2):
#        byte = byte + str(bits[2+b])
#    print('{:>12}'.format(byte))
#    print('')
#    print('')
#    return(bits)
#    
#def bin2hex(byte):
#    return(hex(int(byte)))
#def ISRhit(Pin):
#    print('sensor activado',Pin)
#i=0
#def ISRhit(Pin):
#    global i
#    i+=1
#    print('Int Hit at',Pin, '#:', i)
#
#prepareSensor(function='vibra15Int1')
#i=0
#def ISRhit(Pin):
#    global i
#    i+=1
#    print('Int Hit at',Pin, '#:', i)
#    if Pin == lib.machine.Pin(15):
#        print("start motion Timer reach")
#        i=0
#        setMotionDetection()
#       
#
#bkw.sensor1.irq(handler=ISRhit, trigger=lib.machine.Pin.IRQ_RISING)
#bkw.sensor2.irq(handler=ISRhit, trigger=lib.machine.Pin.IRQ_RISING)
#accelerationMag = lib.math.sqrt(acceleration[0]**2 + acceleration[1]**2 + acceleration[2]**2)

#def ledNotify(msgType=0):
    
    

def readSensorXYZsetup():
    bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1, lib.ubinascii.unhexlify(b'00')) #A_CTRL_REG1 0x2A 0x00(00)	StandBy mode
    bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1, lib.ubinascii.unhexlify(b'01')) #A_CTRL_REG1 0x2A 0x01(01)	Active mode
    bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG5, lib.ubinascii.unhexlify(b'00')) #A_CTRL_REG5 0x2A 0x00(00)  Set range to +/- 2g
    lib.time.sleep(0.3)

def readSensorXYZ():
    # Status register, X-Axis MSB, X-Axis LSB, Y-Axis MSB, Y-Axis LSB, Z-Axis MSB, Z-Axis LSB
    data = bkw.busI2C.readfrom_mem(bkw.A_ADDRESS, bkw.A_STATUS_MMA8452Q, 7)
    xAccl = (data[1] * 256 + data[2]) / 16
    if xAccl > 2047 :
        xAccl -= 4096
    yAccl = (data[3] * 256 + data[4]) / 16
    if yAccl > 2047 :
        yAccl -= 4096
    zAccl = (data[5] * 256 + data[6]) / 16
    if zAccl > 2047 :
        zAccl -= 4096
    return( xAccl, yAccl, zAccl )

def loopAcelerometer(L=1):
    for l in range(L):
        ( xAccl, yAccl, zAccl ) = readSensorXYZ()
        print(" X-Axis : {0:<10} / Y-Axis : {1:>10} / Z-Axis : {2:>10}".format( xAccl, yAccl, zAccl ))
        lib.time.sleep_ms(50)
       
def prepareSensor(function='vibra15Int1'):
    print('preparing sensor to {}'.format(function) )
    if function=='dTap02Int2': # sensor2 = p32 = int2
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG2, lib.ubinascii.unhexlify(b'40'))  # rst,normal mode 0x40 > 0b1000000
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_CFG , lib.ubinascii.unhexlify(b'2a')) # (0x20 0b00100000 just z), 2a Enable X, Y and Z Double Pulse with DPA = 0 no double pulse abort
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_THSX , lib.ubinascii.unhexlify(b'7f'))  # X 0x7f max, 0x10 minSet Threshold 3g on X and Y and 5g on Z
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_THSY , lib.ubinascii.unhexlify(b'7f'))  # Y
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_THSZ , lib.ubinascii.unhexlify(b'1a'))  # Z
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_TMLT , lib.ubinascii.unhexlify(b'60'))  # Set lib.time Limit for Tap Detection to 60 ms LP Mode
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_LTCY , lib.ubinascii.unhexlify(b'20'))  # Set Latency lib.time to 200 ms
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_WIND , lib.ubinascii.unhexlify(b'f0'))  # Set lib.time Window for second tap to 300 ms
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG3, lib.ubinascii.unhexlify(b'12'))  # 0b00010010 Pulse enabled wake up from auto-sleep, IPOL 1, rest low/active high
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG4 , lib.ubinascii.unhexlify(b'08'))  # Enable Pulse Interrupt in System CTRL_REG4
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG5 , lib.ubinascii.unhexlify(b'00'))  # ox00, route int2/ pin25, 0b00000100 Route Pulse Interrupt to INT1 25
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1 , lib.ubinascii.unhexlify(b'01'))  #  Set Active
        
    elif function=='vibra15Int1': # sensor1 = p35 = int1
        s = bkw.config['hardwareSettings']['vibraSensibility']
        s = '0'+str(s) if int(s) < 10 else str(s) 
        sensibilidad = lib.ubinascii.unhexlify(s)
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG2, lib.ubinascii.unhexlify(b'40')) # rst,normal mode 0x40 > 0b1000000
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1, lib.ubinascii.unhexlify(b'64')) # ODR=50,sleep ODR=12.5,enter standby mode
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG3, lib.ubinascii.unhexlify(b'42')) # transient enabled wake up, 0b1011010 IPOL active high, .
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG4, lib.ubinascii.unhexlify(b'a0')) # ASLP INT dissables, Transient INT enabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG5, lib.ubinascii.unhexlify(b'20'))  # INT_CFG_TRAN -> INT1, FF/motion -> INT2
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_TRANSIENT_CFG, lib.ubinascii.unhexlify(b'0e'))  #  TRANSIENT ELE latch disabled, HPF enable, transient x/y/z axes enabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_TRANSIENT_THS, sensibilidad)  # transient threshold=0.065g 1-60 max 
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1, lib.ubinascii.unhexlify(b'05'))  # active transition
         

def toggle_led(timer):
    bkw.led.value(not bkw.led.value())

def nowString(timeTuple = None):
    try:
        if timeTuple == None:
            (time_year, time_mon, time_day, time_hour, time_min, time_sec, time_wday, time_yday) = lib.time.localtime(lib.time.time()+bkw.TMZ)
        else:
            (time_year, time_mon, time_day, time_hour, time_min, time_sec, time_wday, time_yday) = timeTuple
        time_year = str(time_year)    
        time_mon = '0' + str(time_mon) if len(str(time_mon)) < 2 else str(time_mon)
        time_day = '0' + str(time_day) if len(str(time_day)) < 2 else str(time_day)
        time_hour = '0' + str(time_hour) if len(str(time_hour)) < 2 else str(time_hour)
        time_min = '0' + str(time_min) if len(str(time_min)) < 2 else str(time_min)
        time_sec = '0' + str(time_sec) if len(str(time_sec)) < 2 else str(time_sec)
        value2Return = time_year+time_mon+time_day+' '+time_hour+':'+time_min+':'+time_sec
        return(value2Return)

    except Exception as ex:
        print("Mira el error nowString()")
        print("==>>>")
        print(ex)
        print("^^^^^")

def DateTimeStringShort(timeStamp= None):
    try:
        if timeStamp == None:
            timeStamp = lib.time.time()+bkw.TMZ
        else:
            (time_year, time_mon, time_day, time_hour, time_min, time_sec, time_wday, time_yday) = lib.time.localtime(timeStamp+bkw.TMZ)
            time_year = str(time_year)    
            time_mon = '0' + str(time_mon) if len(str(time_mon)) < 2 else str(time_mon)
            time_day = '0' + str(time_day) if len(str(time_day)) < 2 else str(time_day)
            time_hour = '0' + str(time_hour) if len(str(time_hour)) < 2 else str(time_hour)
            time_min = '0' + str(time_min) if len(str(time_min)) < 2 else str(time_min)
            time_sec = '0' + str(time_sec) if len(str(time_sec)) < 2 else str(time_sec)
        value2Return = time_hour+'h'+time_min
        return(value2Return)

    except Exception as ex:
        print("Mira el error DateTimeStringShort()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        
def A9G_Serial(Serial_EN=1, tx=27, rx=26):
    if Serial_EN == 1:
        print('Enabling serial at ports TX:{} / RX:{}'.format(tx,rx))
        bkw.A9G_uart.init(115200,rx=rx, tx=tx, bits=8, parity=None, stop=1, timeout=1000)
        readAndCleanALL()
        
    if Serial_EN == 0:
        print('Disabling Serial at ports TX:{} / RX:{}'.format(tx,rx))
        lib.machine.Pin(tx, lib.machine.Pin.IN)
        lib.machine.Pin(rx, lib.machine.Pin.IN)

def readAndCleanALL():
    try:
        ans = bkw.A9G_uart.readline()
        while ans is not None:
            #print('R&C All A9G:', ans) #ans.decode('utf-8').rstrip())
            ans = bkw.A9G_uart.readline()    
    except Exception as ex:
        print("Mira el error readAndCleanALL()")
        print("==>>>")
        print(ex)
        print("^^^^^")

def readAndPrintALL():
    try:
        ans = bkw.A9G_uart.readline()
        while ans is not None:
            print('R&P All A9G:', ans) #ans.decode('utf-8').rstrip())
            ans = bkw.A9G_uart.readline()    

    except Exception as ex:
        print("Mira el error readAndPrintALL()")
        print("==>>>")
        print(ex)
        print("^^^^^")
    
def turnOnA9G():
    A9G_Serial(1)   # conecto el serial ESP32 al A9G A9G_Serial(1)   
    A9G_EN(1) #lib._thread.start_new_thread(A9G_EN,())  #A9G_EN(1)      # prendo el radio

def A9G_EN(ENABLE=None):
    bkw.A9G_power = lib.machine.Pin(14, lib.machine.Pin.OUT, lib.machine.Pin.PULL_UP)
    bkw.A9G_reset = lib.machine.Pin(12, lib.machine.Pin.OUT, lib.machine.Pin.PULL_UP)

    if ENABLE == 1:
        bkw.memory["ram"]["FlagA9GData"] = False
        print('A9G shutdown -> A9G_reset.value(1)') #si poweron, inicio desde apagado
        bkw.A9G_reset.value(0)
        lib.time.sleep_ms(100)
        bkw.A9G_reset.value(1)
        print('A9G power up -> A9G_power.value(0)')
        bkw.A9G_power.value(0)
        lib.time.sleep(4)
        bkw.A9G_power.value(1)
        #GPS_EN(1)
        bkw.memory["ram"]["FlagA9GENA"] = True
        bkw.memory["ram"]["A9GcomAvailable"] = True
        readAndCleanALL()
    if ENABLE == 0:
        bkw.memory["ram"]["FlagA9GENA"] = False
        bkw.memory["ram"]["FlagA9GData"] = False
        bkw.memory["ram"]["A9GcomAvailable"] = False
        print('A9G shutdown -> A9G_reset.value(1)')
        bkw.A9G_power.value(1) # me aseguro que no arranque.
        bkw.A9G_reset.value(0) # reseteo con low
        lib.time.sleep_ms(200)
        bkw.A9G_reset.value(1)

def isA9Gresponding():
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return(False)
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at isA9Gresponding, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break
        bkw.memory["ram"]["bloquedtask"] = 'isA9Gresponding' + " - " +str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False
        
        bkw.A9G_uart.write("print('A9G ack OK')\r\n")
        lib.time.sleep_ms(100)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        raw_ans = bkw.A9G_uart.readline()
        bkw.memory["ram"]["A9GcomAvailable"] = True
        if raw_ans is not None:
            ans = raw_ans.decode('utf-8').rstrip()
            return(True)
        else:
            A9G_EN(1)
            return(False)

    except Exception as ex:

        print("Mira el error isA9Gresponding()")

        print("==>>>")


        print(ex)
        print("^^^^^")
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(False)


def get_emei():
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at get_emei, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break

        bkw.memory["ram"]["bloquedtask"] = 'get_emei' + " - " +str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False
        readAndCleanALL()
        bkw.A9G_uart.write('cellular.get_imei()\r\n')
        lib.time.sleep_ms(500)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        raw_ans = bkw.A9G_uart.readline()
        bkw.memory["ram"]["A9GcomAvailable"] = True
        if raw_ans is not None:
            emei = raw_ans.decode('utf-8').rstrip().replace("'","")
            return(emei)
        else:
            return('')

    except Exception as ex:

        print("Mira el error get_emei()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(False)

def isA9GwithSIM(tries=1):
    readAndCleanALL()
    for w in range(60):
        if w == 14:
            A9G_EN(1)
            A9G_Serial(1)
            lib.time.sleep(5)
            bkw.memory["ram"]["A9GcomAvailable"] = True
            return(False,'')
        if bkw.memory["ram"]["A9GcomAvailable"] == False:
            print(" wait for A9GcomAvailable = True at isA9GwithSIM, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
            lib.time.sleep(1)
        else:
            break
    bkw.memory["ram"]["bloquedtask"] = 'isA9GwithSIM'  + " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])

    if isA9Gresponding() is False:
        print('A9G die ?')
        return(False,'')
    bkw.A9G_uart.write('cellular.is_sim_present()\r\n')
    lib.time.sleep_ms(100)
    cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
    #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
    ans = bkw.A9G_uart.readline()
    lib.time.sleep_ms(100)
    while ans is None:#leo hasta vaciar el buffer
        for i in range(111):
            ans = bkw.A9G_uart.readline()
            if ans is not None:
                break
            if i==40:# 40x50ms--> 2seg
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return(False,'')
            lib.time.sleep_ms(50)
    
    #print('A9G ans:', ans.decode('utf-8').rstrip()) # imprimo lo que leo
    if ans.decode('utf-8')[0:5] == 'False': # no tengo SIM
        print('---> no hay SIM !! ')
        return(False,'') # no tengo SIM
    if ans.decode('utf-8')[0:4] == 'True': # tengo SIM
        #print('---> SIM ok')
        bkw.A9G_uart.write('cellular.get_imsi()\r\n')
        lib.time.sleep_ms(100)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
        ans = bkw.A9G_uart.readline()
        lib.time.sleep_ms(100)
        while ans is None:#leo hasta vaciar el buffer
            for i in range(111):
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==100:
                    bkw.memory["ram"]["A9GcomAvailable"] = True
                    return(False,'')
                lib.time.sleep_ms(50)
        #print('SIM IMSI:', ans.decode('utf-8').rstrip()) # imprimo lo que leo
        IMSI = ans.decode('utf-8').rstrip().replace("'","")
        return(True, IMSI)

def isA9Gconnected(tries=1):
    try:
        readAndCleanALL()
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                bkw.memory["ram"]["A9GcomAvailable"] = True

            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at isA9Gconnected, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break
        bkw.memory["ram"]["bloquedtask"] = 'isA9Gconnected'+ " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False

        bkw.A9G_uart.write('cellular.is_network_registered()\r\n')
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        lib.time.sleep_ms(100)
        ans = bkw.A9G_uart.readline()
        lib.time.sleep_ms(100)
        while ans is None: #leo hasta vaciar el buffer
            for i in range(1000):
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==40:
                    bkw.memory["ram"]["A9GcomAvailable"] = True
                    return(False)
                lib.time.sleep_ms(50)
        if ans.decode('utf-8')[0:4] == 'True': # si
            #print('----> Network register was Ok')
            bkw.memory["ram"]["A9GcomAvailable"] = True
            return(True) # estoy conectado a la red movil
        bkw.A9G_uart.write('cellular.is_sim_present()\r\n')
        lib.time.sleep_ms(100)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
        ans = bkw.A9G_uart.readline()
        lib.time.sleep_ms(100)
        while ans is None:#leo hasta vaciar el buffer
            for i in range(100):
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==100:
                    bkw.memory["ram"]["A9GcomAvailable"] = True
                    return(False)
                lib.time.sleep_ms(50)
        #print('A9G ans:', ans.decode('utf-8').rstrip()) # imprimo lo que leo
        if ans.decode('utf-8')[0:5] == 'False': # no tengo SIM
            print('---> no hay SIM !! ')
            bkw.memory["ram"]["A9GcomAvailable"] = True
            return(False) # no tengo SIM
        if ans.decode('utf-8')[0:4] == 'True': # tengo SIM
            print('---> SIM ok')
        for t in range(tries):
            print('isA9Gconnected() = True ? trying #:',t)
            readAndCleanALL()
            bkw.A9G_uart.write('cellular.is_network_registered()\r\n')
            lib.time.sleep_ms(100)
            cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
            lib.time.sleep_ms(100)
            ans = bkw.A9G_uart.readline()
            lib.time.sleep_ms(100)
            while ans is None:#leo hasta vaciar el buffer
                for i in range(111):
                    ans = bkw.A9G_uart.readline()
                    if ans is not None:
                        break
                    if i==100:
                        bkw.memory["ram"]["A9GcomAvailable"] = True
                        return(False)
                    lib.time.sleep_ms(10)
            if ans.decode('utf-8')[0:4] == 'True': # si
                print('---> network register ok now')
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return(True) # estoy conectado a la red movil
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(False)

    except Exception as ex:
        print("Mira el error isA9Gconnected()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(False)

def GPS_EN(GPSENABLE=1):
    while bkw.memory["ram"]["A9GcomAvailable"] == False:
        print(" wait for A9GcomAvailable = True at GPS_EN, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
        lib.time.sleep(1)
    bkw.memory["ram"]["bloquedtask"] = 'GPS_EN' + " - " +str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        
    if GPSENABLE == 1:
        print('-----> GPS poweron')
        bkw.A9G_uart.write("gps.on()\r\n")
        readAndCleanALL()

    if GPSENABLE == 0:
        print('-----> GPS power off')
        bkw.A9G_uart.write("gps.off()\r\n")
        readAndCleanALL()
    bkw.memory["ram"]["A9GcomAvailable"] = True
        
def battery():
    vbat =  bkw.vbat36.read()/bkw.BatteryCalibration_A + 1/bkw.BatteryCalibration_B
    charge = 100 if vbat > 4.15 else (int((vbat - 3.15)/0.01) if vbat > 3.1 else 0)
    return(float('{:.1f}'.format(vbat)), charge)

def bat_calibrate():
    print('Old battery params A:{} & B:{} '.format(bkw.config['hardwareSettings']['BatteryCalibration_A'],bkw.config['hardwareSettings']['BatteryCalibration_B']))
    v1 = eval(input('Set Vin1 and press enter that value : '))
    r1 = bkw.vbat36.read()
    v2 = eval(input('Set Vin2 and press enter that value : '))
    r2 = bkw.vbat36.read()
    bkw.BatteryCalibration_A = ( r1 - r2 ) / ( v1 - v2 )
    bkw.BatteryCalibration_B = 1 / (v2 - r2 * (v1 -v2)/(r1-r2))
    bkw.config['hardwareSettings']['BatteryCalibration_A'] = bkw.BatteryCalibration_A
    bkw.config['hardwareSettings']['BatteryCalibration_B'] = bkw.BatteryCalibration_B
    print('New battery params A:{} & B:{} '.format(bkw.config['hardwareSettings']['BatteryCalibration_A'],bkw.config['hardwareSettings']['BatteryCalibration_B']))
    with open('bikewatch.cfg', 'w') as f:
        lib.json.dump(bkw.config,f)

def setLowPower():
    lib.machine.freq(40000000)
    
def setLowPowerforSleep():

    bkw.led.init(pull=None)  # Pin 13
    bkw.smsIn.init(pull=None)  # Pin 25
    bkw.smsOut.init(pull=None) # Pin 33
    bkw.A9G_power.init(pull=None) # Pin 14
    bkw.A9G_reset.init(pull=None) # Pin 12
    bkw.scl.init(pull=None) # Pin 18
    bkw.sda.init(pull=None) # Pin 19
    #RX / TX -- 26 /27
    #15 is INT1
    #2 is INT2 

def thread_touch():
    try:
        print('--->> def thread_touch')
        touchSensibility = int(bkw.config['hardwareSettings']['touchSensibility'])
        while True:
            if bkw.touch.read() < touchSensibility: #duplico para reconfirmar touch doble medicion
                print('touch activado, voy con goSleepUnArmed')
                touchActioned(bkw.config['Timers']['unArmedSelfWakeTimer_m'])
            lib.time.sleep_ms(300)

    except Exception as ex:
        print("Mira el error thread_touch()")
        print("==>>>")
        print(ex)
        print("lanzo==>>>thread_touch2()")
        thread_touch2()
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")        
        
def thread_touch2():
    try:
        print('--->> def thread_touch')
        touchSensibility = int(bkw.config['hardwareSettings']['touchSensibility'])
        while True:
            if bkw.touch.read() < touchSensibility: #duplico para reconfirmar touch doble medicion
                print('touch activado, voy con goSleepUnArmed')
                touchActioned(bkw.config['Timers']['unArmedSelfWakeTimer_m'])
            lib.time.sleep_ms(300)

    except Exception as ex:
        print("Mira el error thread_touch()")
        print("==>>>")
        print(ex)
        print("lanzo==>>>thread_touch1()")
        thread_touch()
        print("##############################")    

def touchActioned(sleepTimeout_m = 24*60):
    print('')
    print('--->> touchActioned, -->> goSleepUnArmed')
    print('')
    bkw.statusLed.init(period=100, mode=lib.machine.Timer.PERIODIC, callback=toggle_led)
    sendLocationMsg()
    print("espero 5 seg para enviar el sms")
    lib.time.sleep(7)
    goSleepUnArmed(sleepTimeout_m)

def buttonActioned(sleepTimeout_m = 24*60):
    print('')
    print('--->> buttonActioned, -->> goSleepArmed, report Armed each {}m'.format(sleepTimeout_m))
    print('')
    Actioned2goArmed(sleepTimeout_m)

               
def Actioned2goArmed(sleepTimeout_m = 24*60):
    bkw.statusLed.init(period=500, mode=lib.machine.Timer.PERIODIC, callback=toggle_led)
    readAndCleanALL()
    try:
        i = 0
        while isA9Gconnected(20) is False:
            print('waiting for isA9Gconnected() is True, tried#:', i+1)
            print("A9G reseted now to try reconnect")
            A9G_EN(1)
            A9G_Serial(1)
            i += 1
            if i > 1:
                #To do, instead break, think a better alternative goSleep for 5 min and continue ?
                break
        bkw.statusLed.init(period=500, mode=lib.machine.Timer.PERIODIC, callback=toggle_led)
        volts, charge = battery()
        msg = '{}/ bkw vigilando, carga: {}% ({}v)'.format(bkw.uid, charge, volts)
        sendSMS(msg)
        #lib.time.sleep(5)
        #sendLocationMsg()
        print('le doy tiempo para enviar el SMS, en 10s apago A9G')
        lib.time.sleep(10)
        print('{}/ Ahora a dormir bkw vigilando, goSleepArmed(24htimer)'.format(bkw.uid))
        goSleepArmed(sleepTimeout_m)

    except Exception as ex:
        print("Mira el error Actioned2goArmed()")
        print("==>>>")
        print(ex)
        print("^^^^^")    

def goSleepUnArmed(sleepTimeout_m=1440):
    try:
        A9G_EN(0) # Apago A9G
        lib.time.sleep(1)
        lib.esp32.wake_on_ext1(( lib.machine.Pin(39), lib.machine.Pin(39)), level = lib.esp32.WAKEUP_ANY_HIGH)
        bkw.touch.config(int(bkw.config['hardwareSettings']['touchSensibilitySleep']))
        lib.esp32.wake_on_touch(True) #Touch activa UnArmed y Pin39 activa bikewatch en modo vigia sensor 
        #ver como minimizar todo consumo Pins, bkw.rtc, etc
        print('going sleep UnArmed for {} min'.format(sleepTimeout_m) )
        volts, charge = battery()
        bkw.memory["ram"]["secondsAlarmed"] = 0
        bkw.memory["ram"]["lastTimestamp_s"] = lib.time.time() #- bkw.memory["ram"]["bootTime"]
        bkw.memory["ram"]["lastDeepSleep_s"] = sleepTimeout_m * 60
        setLowPowerforSleep()
        bkw.rtc = lib.machine.RTC()
        bootRTC_JSON = {'nextBootMode':'normal', 'bootStatus':'UnArmed','secondsAlarmed': 0,'lastDSBattery':charge, "lastTimestamp_s": bkw.memory["ram"]["lastTimestamp_s"],"lastDeepSleep_s": bkw.memory["ram"]["lastDeepSleep_s"], "lastLocationType": bkw.memory["ram"]["lastLocationType"], "lastLocationLat": bkw.memory["ram"]["lastLocationLat"], "lastLocationLon": bkw.memory["ram"]["lastLocationLon"],"smsPointIndex": bkw.memory["ram"]["smsPointIndex"],"blynkPointIndex": bkw.memory["ram"]["blynkPointIndex"]}
        bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM

        print('closing logFile before goSleepUnArmed at {}'.format(lib.time.localtime(lib.time.time())))
        lib.uos.dupterm(None)
        #f.close()
        unArmedSleep_ms = sleepTimeout_m * 60000 # de minutos a milisegundos
        lib.machine.deepsleep(unArmedSleep_ms)
        #lib.machine.deepsleep(2*60000)

    except Exception as ex:
        print("Mira el error goSleepUnArmed()")
        print("==>>>")
        print(ex)
        print("^^^^^")   

def goSleepArmed(sleepTimeout_m=1440):
    try:
        setMotionDetection()
        #prepareSensor(function='vibra15Int1') #prepareSensor(function='vibra2Int2')        prepareSensor(function='dTap2Int2')
        lib.time.sleep(1)
        sensor1 = lib.machine.Pin(15, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # sensor INT1
        sensor2 = lib.machine.Pin(2, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # sensor INT2 
#        bkw.touch.config(int(bkw.config['hardwareSettings']['touchSensibilitySleep']))
#        lib.esp32.wake_on_touch(True)
        print('going sleep Armed for {} Min'.format(sleepTimeout_m) )
        volts, charge = battery()
        bkw.memory["ram"]["secondsAlarmed"] = 0
        bkw.memory["ram"]["lastTimestamp_s"] = lib.time.time()
        bkw.memory["ram"]["lastDeepSleep_s"] = sleepTimeout_m * 60
        A9G_EN(0) # Apago A9G
        setLowPowerforSleep()
        bkw.rtc = lib.machine.RTC()
        bootRTC_JSON = {'nextBootMode':'normal', 'bootStatus':'Armed','secondsAlarmed': bkw.memory["ram"]["secondsAlarmed"],'lastDSBattery':charge, "lastTimestamp_s": bkw.memory["ram"]["lastTimestamp_s"],"lastDeepSleep_s": bkw.memory["ram"]["lastDeepSleep_s"], "lastLocationType": bkw.memory["ram"]["lastLocationType"], "lastLocationLat": bkw.memory["ram"]["lastLocationLat"], "lastLocationLon": bkw.memory["ram"]["lastLocationLon"],"smsPointIndex": bkw.memory["ram"]["smsPointIndex"],"blynkPointIndex": bkw.memory["ram"]["blynkPointIndex"]}
        bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM
        lib.esp32.wake_on_ext0( lib.machine.Pin(2), level = lib.esp32.WAKEUP_ANY_HIGH) #if sensor pressed, next boot is Alarmed
        print('closing logFile before goSleepArmed at {}'.format(lib.time.localtime(lib.time.time())))
        lib.uos.dupterm(None)
        #f.close()
        sleepTimeout_ms = sleepTimeout_m * 60000
        lib.machine.deepsleep(sleepTimeout_ms)
    
    except Exception as ex:
        print("Mira el error goSleepArmed()")
        print("==>>>")
        print(ex)
        print("^^^^^")   

def goSleepAlarmed(sleepTimeout_m=10):
    try:
        
        print('@goSleepAlarmed(), going sleep Alarmed for {} Min'.format(sleepTimeout_m) )
        volts, charge = battery()
        bkw.memory["ram"]["secondsAlarmed"] = lib.time.time() - bkw.memory["ram"]["alarmedTimeZero"]
        bkw.memory["ram"]["lastTimestamp_s"] = lib.time.time()
        bkw.memory["ram"]["lastDeepSleep_s"] = sleepTimeout_m * 60
        bkw.memory["ram"]["lastDSBattery"] = charge
        setLowPowerforSleep()
        sensor1 = lib.machine.Pin(15, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # sensor INT1
        sensor2 = lib.machine.Pin(2, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # sensor INT2 
#        bkw.touch.config(int(bkw.config['hardwareSettings']['touchSensibilitySleep']))
#        lib.esp32.wake_on_touch(True)        
        print('closing logFile before goSleepAlarmed at {}'.format(lib.time.localtime(lib.time.time())))
        lib.uos.dupterm(None)
        lib.esp32.wake_on_ext1(( lib.machine.Pin(39), lib.machine.Pin(39)), level = lib.esp32.WAKEUP_ANY_HIGH)
#        lib.esp32.wake_on_touch(True) #Touch activa UnArmed y Pin39 activa bikewatch en modo vigia sensor 

        bkw.rtc = lib.machine.RTC()
        bootRTC_JSON = {'nextBootMode':'normal', 'bootStatus':'Alarmed','secondsAlarmed': bkw.memory["ram"]["secondsAlarmed"],'lastDSBattery':charge, "lastTimestamp_s": bkw.memory["ram"]["lastTimestamp_s"],"lastDeepSleep_s": bkw.memory["ram"]["lastDeepSleep_s"], "lastLocationType": bkw.memory["ram"]["lastLocationType"], "lastLocationLat": bkw.memory["ram"]["lastLocationLat"], "lastLocationLon": bkw.memory["ram"]["lastLocationLon"], "smsPointIndex": bkw.memory["ram"]["smsPointIndex"],"blynkPointIndex": bkw.memory["ram"]["blynkPointIndex"], "lastStopedHits": bkw.memory["ram"]["lastStopedHits"], "lastStopedTime": bkw.memory["ram"]["lastStopedTime"], "lastMovingHits": bkw.memory["ram"]["lastMovingHits"], "lastMovingTime": bkw.memory["ram"]["lastMovingTime"], "alarmedTimeZero": bkw.memory["ram"]["alarmedTimeZero"]}
        bkw.rtc.memory(lib.json.dumps(bootRTC_JSON))  # Save status in RTC RAM
        sleep_ms = sleepTimeout_m * 60000
        A9G_EN(0) # Apago A9G
        lib.machine.deepsleep(sleep_ms)
    except Exception as ex:
        print("Mira el error goSleepAlarmed()")
        print("==>>>")
        print(ex)
        print("^^^^^")   

def thread_checkOwnerIsNear(each_s=2):
    try:
        bkw.bikewatch_AP.active(True)   # activo y configuro el AP para desactivar si owner se conecta
        bkw.bikewatch_AP.config(essid=bkw.config['AP']['AP_name'], password=bkw.config['AP']['AP_pass'],authmode =3)
        print('checkOwnerIsNear() each',each_s,'seconds')
        while True:
            if ownerIsNear():
                bkw.statusLed.init(period=100, mode=lib.machine.Timer.PERIODIC, callback=toggle_led)
                volts, charge = battery()
                msg = '{}/ Bikewatch desactivado por presencia, carga: {}% ({}v)'.format(bkw.uid, charge, volts)
                print(msg)
                sendSMS(msg)
                lib.time.sleep(5)
                goSleepUnArmed(60*24)
            lib.time.sleep_ms(each_s)
    except Exception as err:
        print(err)
     
def ownerIsNear():
    try:
        connected_sta = bkw.bikewatch_AP.status('stations')
        #To do remove from connected_sta list those monitoring stations
        
        #print("bikewatch_AP.status('stations')",connected_sta)
        if connected_sta != []:
            return(True) ## no valido MAC
            if connected_sta[0][0] == bkw.config['AP']['registered_device']: # valido MAC
                return(True)
            else:
                return(False)
        return(False)
    except Exception as err:
        print(err)

def sendSMS(msg):
    #print('sending msg: ', msg)
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at sendSMS, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break  
        bkw.memory["ram"]["bloquedtask"] = 'sendSMS'+ " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False

        #envio 1er sms al owner_phone
        print('sending msg owner_phone: {}'.format(bkw.owner_phone))        
        print('msg is: ', msg)
        bkw.A9G_uart.write("cellular.SMS('{}', '{}').send()\r\n".format(bkw.owner_phone, msg))
        lib.time.sleep(8)
        readAndCleanALL()
        
        #envio 2do sms al SMs gateway
        #print('sending msg smsServer_phone: {}'.format(bkw.smsServer_phone))
        #bkw.A9G_uart.write("cellular.SMS('{}', '{}').send()\r\n".format(bkw.smsServer_phone, msg))
        #lib.time.sleep(2)
        #readAndPrintALL()

        bkw.memory["ram"]["A9GcomAvailable"] = True

    except Exception as err:
        bkw.memory["ram"]["A9GcomAvailable"] = True
        print(err)

 
def getSMS():
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at getSMS, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break
        bkw.memory["ram"]["bloquedtask"] = 'getSMS'+ " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False
        readAndCleanALL()
        bkw.A9G_uart.write('lastSMS\r\n') 
        cmd = bkw.A9G_uart.readline()#leo respuesta, la primera es el comando
        ans = bkw.A9G_uart.readline()
        if ans.decode('utf-8')[0] == '(':
            print('A9G ans:', ans) #ans.decode('utf-8').rstrip())
            lastSMS = ans.decode('utf-8').replace("\r\n","").replace("(","").replace(")","").split(', ')
            lib.timeStamp = eval(lastSMS[0])
            sender = eval(lastSMS[1])
            RcvMsg = eval(lastSMS[2])
            bkw.A9G_uart.write('lib.time.time()\r\n')  # confirmo la hora
            cmd = bkw.A9G_uart.readline()#leo respuesta, la primera es el comando
            raw_ans = bkw.A9G_uart.readline()
            lib.timetime = eval(raw_ans.decode('utf-8').rstrip())
            elapsed = lib.timetime - lib.timeStamp
            lastSMS = (elapsed,sender,RcvMsg)
    
            bkw.A9G_uart.write('smsRp30.value(0)\r\n') #reseteo el pin NewRcv => bkw.smsIn @esp32
            cmd = bkw.A9G_uart.readline()#leo respuesta, la primera es el comando
            bkw.memory["ram"]["A9GcomAvailable"] = True
            return(lastSMS)
        
        print('getSMS error ?')
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(None)  

    except Exception as err:
        print(err)
    bkw.memory["ram"]["A9GcomAvailable"] = True

def SMScheck():
    try:
        if bkw.smsIn.value() == 0: # si no hay mensajes, devuelvo rapido False, si el A9G esta apagado tambien False
            #print('No Message Flag bkw.smsIn')
            return(False)
        msg = getSMS()
        if msg is None:
            print('SMScheck() error')
            return(False)
        ArrivedSecs = msg[0]
        sender = msg[1]
        text = msg[2]
        text = text.split(' ')
        if bkw.config["Secrets"]["SMScode"] != text[1]:
            print('bkw invalid code', text[1])
            return(False)
        else:
            print('from', sender)
            print('since', ArrivedSecs)
            print('bkw code ok', text[1])
            if text[2].upper() == 'SET':
                print('command SET, parameter: {}, Value: {}'.format(text[3], text[4]))
                if text[3].upper() == 'CODE'.upper():
                    bkw.config["Secrets"]["SMScode"] = text[4]
                    msg = bkw.uid +'/'+'bkw NEWCODE {}, please send "bkw OLDCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                if text[3].upper() == 'SELFWAKETIMER':
                    bkw.config["Timers"]["unArmedSelfWakeTimer_m"] = eval(text[4])
                    msg = bkw.uid +'/'+'bkw unArmedSelfWakeTimer_m {}, please send "bkw YOURCODE save" to confirm update'.format(text[4])
                    sendSMS(msg)
                if text[3].upper() == 'STATUS':
                    if text[4].upper() == 'ALARMED':
                        volts, charge = battery()
                        status_msg = bkw.uid +'/'+'bkw Alarmed by SMS, carga: {}% ({}v)'.format(charge, volts)
                        sendSMS(status_msg)
                        goSleepAlarmed(sleepTimeout_m = 1*60)                         
                    if text[4].upper() == 'ARMED':
                        buttonActioned(sleepTimeout_m = 24*60)
                    if text[4].upper() == 'UNARMED':
                        volts, charge = battery()
                        status_msg = bkw.uid +'/'+'bkw unArmed by SMS, carga: {}% ({}v)'.format(charge, volts)
                        sendSMS(status_msg)
                        goSleepUnArmed(sleepTimeout_m = 24*60)                
                    
                if text[3].upper() == 'WIFIPASS':
                    bkw.config["AP"]["AP_pass"] = text[4]
                    msg = bkw.uid +'/'+'bkw WIFIPASS {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                    
                if text[3].upper() == 'APNNAME':
                    bkw.config["APN"]["APN_NAME"] = text[4]
                    msg = bkw.uid +'/'+'bkw APNNAME {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                    
                if text[3].upper() == 'APNUSER':
                    bkw.config["APN"]["APN_USER"] = text[4]
                    msg = bkw.uid +'/'+'bkw APNUSER {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                    
                if text[3].upper() == 'APNPASS':
                    bkw.config["APN"]["APN_PASS"] = text[4]
                    msg = bkw.uid +'/'+'bkw APNPASS {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                    
                if text[3].upper() == 'REPORTTO':
                    bkw.config["reportTo"]["owner_phone"] = eval(text[4])
                    msg = bkw.uid +'/'+'bkw REPORTTO {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
    
                if text[3].upper() == 'bkw.USE_DATA':
                    bkw.config["Flags"]["bkw.USE_DATA"] = eval(text[4])
                    msg = bkw.uid +'/'+'bkw bkw.USE_DATA {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
    
                if text[3].upper() == 'bkw.USE_Google':
                    bkw.config["Flags"]["bkw.USE_Google"] = eval(text[4])
                    msg = bkw.uid +'/'+'bkw bkw.USE_Google {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                if text[3].upper() == 'SENDMAPS':
                    bkw.config["Flags"]["SendMaps"] = eval(text[4])
                    msg = bkw.uid +'/'+'bkw SENDMAPS {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
                if text[3].upper() == 'SENDRAW':
                    bkw.config["Flags"]["SendRAW"] = eval(text[4])
                    msg = bkw.uid +'/'+'bkw SENDMAPS {}, please send "bkw YOURCODE save confirm" to confirm update'.format(text[4])
                    sendSMS(msg)
            
            if text[2].upper() == 'SAVE':
                print('command SAVE')
                with open('bikewatch.cfg', 'w') as f:
                    lib.json.dump(bkw.config,f)
                f.close()
                msg = bkw.uid +'/'+'bkw Updated'
                sendSMS(msg)

            return(True)

    except Exception as err:
        print(err)



def A9G_connectData(TRIES=4):
    readAndCleanALL()
    try:
        if bkw.config['Flags']['USE_DATA'] is False:
            print("bkw.config['Flags']['USE_DATA'] is False !")
            IPaddress = ''
            return(bkw.config['Flags']['USE_DATA'], IPaddress)
        if bkw.memory["ram"]["FlagA9GData"] is True:
            print('bkw.memory["ram"]["FlagA9GData"] true, data was already setup')
            IPaddress = ''
            bkw.A9G_uart.write('socket.get_local_ip()\r\n')
            cmd = bkw.A9G_uart.readline()#leo respuesta, la primera es el comando
            raw_ans = bkw.A9G_uart.readline()#leo respuesta,
            ans = raw_ans.decode('utf-8').rstrip()
            IPaddress = ans[1:len(ans)-1]
            return(True, IPaddress)
        for t in range(TRIES):
            print('Connecting MobileNet try #', t+1, 'of', TRIES ,'tries')
            if isA9Gresponding() is False:
                break
            if isA9Gconnected() is False: ### mejorar la logica en caso no este registrado en la red
                lib.time.sleep(10)
                break
            bkw.A9G_uart.write("gprsSetup('{}','{}','{}')\r\n".format(bkw.APN_NAME, bkw.APN_USER, bkw.APN_PASS))
            cmd = bkw.A9G_uart.readline()#leo respuesta, la primera es el comando
            lib.time.sleep_ms(100)
            if cmd is None: # si aun no hay confirmacion de comando, reseteo A9G
                print('cmd is None for too long, break')
                A9G_EN(1)
                readAndCleanALL()
                lib.time.sleep(3)
                return(False, '')
            raw_ans = bkw.A9G_uart.readline()
            lib.time.sleep_ms(100)
            while raw_ans is None: #leo hasta que caiga algo
                for i in range(500):
                    raw_ans = bkw.A9G_uart.readline()
                    if raw_ans is not None:
                        break
                    if i==500:
                        return(False, '')
                    lib.time.sleep_ms(10)
            print('A9G response to gprsSetup():', raw_ans) # tuve esta respueta
            if raw_ans[0:24] == b'Network is not available' or raw_ans == b'[Errno 110] ETIMEDOUT\r\n':
                print('Network is not available, reseting')
                bkw.A9G_uart.write('cellular.reset()\r\n')
                cmd = bkw.A9G_uart.readline()#leo respuesta, la primera es el comando
                lib.time.sleep(3)
                break
            ans = str(raw_ans, 'utf8')  #paso de raw bytes a string utf8
            if ans[1:5] == 'True':
                bkw.memory["ram"]["FlagA9GData"] = True
                MobileNet, IPaddress = ans.replace("(","").replace(")","").replace("'","").split(', ')
                IPaddress = IPaddress.rstrip()
                return(bkw.memory["ram"]["FlagA9GData"] , IPaddress)
            else:
                bkw.memory["ram"]["FlagA9GData"] = False
                print('gprsSetup() unsuccesful,', t+1,'more tries left now' )
                return(False, '')

    except Exception as err:
        print(err)
        bkw.memory["ram"]["FlagA9GData"] = False
        print('gprsSetup() unsuccesful,', t+1,'more tries left now' )
        return(False, '')


def getSats():
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at getSats, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break
        bkw.memory["ram"]["bloquedtask"] = 'getSats'+ " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False

        bkw.A9G_uart.write("gps.on()\r\n") # prendo gps en todo caso 
        lib.time.sleep_ms(50)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo 
        readAndCleanALL()
        bkw.A9G_uart.write('gps.get_satellites()\r\n') # status de los satelites
        lib.time.sleep_ms(300)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo 
        ans = bkw.A9G_uart.readline()

        while ans is None:#leo hasta vaciar el buffer
            for i in range(111):
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==50:
                    bkw.memory["ram"]["A9GcomAvailable"] = True
                    return( -2, -2) 
                lib.time.sleep_ms(50)

        if ans.decode('utf-8')[0] == '(':
            tracking, visibles = ans.decode('utf-8').replace("\r\n","").replace("(","").replace(")","").split(', ')
            tracking, visibles = int(tracking), int(visibles)
            bkw.memory["ram"]["A9GcomAvailable"] = True
            return( tracking, visibles) 
        return( -3, -3) 

    except Exception as ex:
        print(ex)
        print('last cmd', cmd)
        print('last ans', ans)
        bkw.memory["ram"]["A9GcomAvailable"] = True  
        return( -1, -1) 
                  
    

def fix_GPS():
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at fix_GPS, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break        
        bkw.memory["ram"]["bloquedtask"] = 'fix_GPS'+ " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False

        bkw.A9G_uart.write("gps.on()\r\n") # prendo gps en todo caso 
        lib.time.sleep_ms(50)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo 
        readAndCleanALL()
        bkw.A9G_uart.write('gps.get_satellites()\r\n') # status de los satelites
        lib.time.sleep_ms(300)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo 
        ans = bkw.A9G_uart.readline()
        while ans is None: #leo hasta vaciar el buffer
            for i in range(100): # aprox 10seg (100x100ms)
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==50:
                    ans = ''
                    break
                lib.time.sleep_ms(100)
        if ans.decode('utf-8')[0] == '(':
            tracking, visibles = ans.decode('utf-8').replace("\r\n","").replace("(","").replace(")","").split(', ')
            tracking, visibles = int(tracking), int(visibles)
        bkw.A9G_uart.write('gps.nmea_data()[0]\r\n') #RMC: (time: int, valid: bool, latitude, longitude, speed, course, variation: float)
        lib.time.sleep_ms(100)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        ans = bkw.A9G_uart.readline()
        lib.time.sleep_ms(100)
        while ans is None: #leo hasta vaciar el buffer
            for i in range(100):
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==50:
                    ans = ''
                    break
                lib.time.sleep_ms(100)
        nmea_RMC = ans.decode('utf-8').replace("\r\n","").replace("(","").replace(")","").split(', ')
        #    (677316751, True, -3431.517578125, -5829.950195312501, 0.421999990940094, 202.8099975585937, nan)

        
        if nmea_RMC[1] == 'True': # si el segundo elemento es true, tengo fix
            locationType = 'G'
            DateTime = int(int(nmea_RMC[0])/60)
            bkw.memory["ram"]["lastDateTime"] = DateTime
            lib.machine.RTC().datetime(lib.time.localtime(DateTime)) # sync machine time calendar/clock 
            lat = GGMMpMM2GpD(float(nmea_RMC[2]))
            lon = GGMMpMM2GpD(float(nmea_RMC[3]))
            accuracy = 5
            speed = float(nmea_RMC[4])*1.82
            curse= int(float(nmea_RMC[5]))
            # updating bkw.memory ram
        else:
            locationType = 'R'
            DateTime = int(int(nmea_RMC[0])/60)
            lat = 0
            lon = 0
            accuracy = 0
            speed = 0
            curse = 0

        bkw.memory["ram"]["lastLocationType"] = locationType
        bkw.memory["ram"]["lastSatsTrk"] = tracking
        bkw.memory["ram"]["lastSatsVis"] = visibles
        bkw.memory["ram"]["lastLocationLat"] = lat
        bkw.memory["ram"]["lastLocationLon"] = lon
        bkw.memory["ram"]["lastGPSAccuracy"] = accuracy
        bkw.memory["ram"]["lastSpeedGPS"] = speed
        bkw.memory["ram"]["lastCurseGPS"] = curse

        bkw.memory["ram"]["A9GcomAvailable"] = True
        return( locationType, DateTime, tracking, visibles, lat, lon, accuracy, speed, curse ) 

    except Exception as ex:
        print(ex)
        print('last cmd', cmd)
        print('last ans', ans)
        bkw.memory["ram"]["A9GcomAvailable"] = True        
      
    
def fix_AGPS(): ## agps fix using mobile data from A9G 
    print('bkw.USE_DATA -->:{}, fix_AGPS bkw.FlagA9GData->{}, bkw.USE_Google->{}'.format(bkw.USE_DATA, bkw.USE_Google, bkw.memory["ram"]["FlagA9GData"]))
    if bkw.USE_DATA is False:
        return('AGPS NA, set not USE_DATA', 0, 0, 0, 0, 0, 0)
    try:
        readAndCleanALL()
        if bkw.FlagA9GData == False:
            print('bkw.FlagA9GData is not set on, coonecting now')
            (MobileNet, IPaddress) = A9G_connectData(4)  # conecto los datos
            print('fix AGPS init, GPRS is Connected?', MobileNet, 'IP:', IPaddress)
        else:
            print('fix_AGPS() init, bkw.memory["ram"]["FlagA9GData"]?:{}  --> GPRS was already Connected'.format(bkw.memory["ram"]["FlagA9GData"]))
        if isA9Gresponding() is False:
            print('A9G do not respond, A9G reset and wait 5sec')
            A9G_EN(1)
            lib.time.sleep(5)
        if not bkw.sta_if.active():
            bkw.sta_if.active(True)
            onAirWifis = bkw.sta_if.scan()
            bkw.sta_if.active(False)
        else:
            onAirWifis = bkw.sta_if.scan()
        w = tuple(dict(macAddress=macAddress, signalStrength=signalStrength) for SSID, macAddress, channel, signalStrength, AuthMethod,  _ in onAirWifis )
        qtyWifis = len(w)
        wifis = ''
        m = len(w)
        m = min(3,m)
        for k in w[0:m]:    
            wifis = wifis + "'" + lib.ubinascii.hexlify(k['macAddress'],':').decode() +"','"+  str(k['signalStrength']) + "',"
        wifis = wifis[0:len(wifis)-1]
        while bkw.memory["ram"]["A9GcomAvailable"] == False:
            print(" wait for A9GcomAvailable = True at fix_AGPS, BlockedTask is {} ".format(bkw.memory["ram"]["bloquedtask"]))
            lib.time.sleep(1)
        bkw.memory["ram"]["A9GcomAvailable"] = False            
        for t in range(2):
            if bkw.USE_Google == True:
                bkw.A9G_uart.write("getAgps_Google({})\r\n".format(wifis))
            else:
                bkw.A9G_uart.write("getAgps_Unwired({})\r\n".format(wifis))
            cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
            print('A9G cmd:', cmd) #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
            i=0
            raw_ans = bkw.A9G_uart.readline() #esta seria la respuesta de getAgps()
            while raw_ans is None and i < 15: #espero 30 timeouts del serial hasta tener una respuesta 
                print('waiting getAgps() response # ', i)
                raw_ans = bkw.A9G_uart.readline()
                i += 1
            if raw_ans is not None:
                break
        if raw_ans is None: # si aun no hay respuesta reseteo A9G
            print('getAgps() do not respond, break')
            return('AGPS NoAns', 0, 0, 0, 0, 0, 0)
        print('A9G response to getAgps..():', raw_ans) # tuve esta respueta
        if raw_ans == b'[Errno 5] EIO\r\n' or raw_ans == b'[Errno 2] ENOENT\r\n' or raw_ans == b'[Errno 107] ENOTCONN\r\n':
            print('last raw_ans:', raw_ans)
            return('AGPS Error', 0, 0, 0, 0, 0, 0)
        print('A9G response to getAgps() seems valid!')
        ans = raw_ans.decode('utf-8').rstrip()  #paso de raw bytes a string utf8 
        
        lat,lon,accuracy,qtyCells,responseTime = ans.replace("(","").replace(")","").split(', ')
        bkw.memory["ram"]["lastLocationType"] = 'A'
        bkw.memory["ram"]["lastLocationLat"] = lat
        bkw.memory["ram"]["lastLocationLon"] = lon
        bkw.memory["ram"]["accuracy"] = accuracy
        bkw.memory["ram"]["qtyCells"] = qtyCells
        bkw.memory["ram"]["qtyWifis"] = qtyWifis
    
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return('AGPS', lat, lon, int(accuracy), int(qtyCells), qtyWifis, int(responseTime))
    except Exception as ex:
        print(ex)
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return('AGPS Error', 0, 0, 0, 0, 0, 0)
    bkw.memory["ram"]["A9GcomAvailable"] = True

def getCells():
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at getCells, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break       
        bkw.memory["ram"]["bloquedtask"] = 'getCells'+ " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False
        readAndCleanALL()
        cells = ''
        bkw.A9G_uart.write("cellular.stations()\r\n")
        lib.time.sleep_ms(200)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd)  #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
        ans = bkw.A9G_uart.readline()
        lib.time.sleep_ms(100)
        while ans is None: #leo hasta vaciar el buffer
            for i in range(200):
                ans = bkw.A9G_uart.readline()
                if ans is not None:
                    break
                if i==30:
                    print('error getCells, ans wan None 30 times, ans:', ans)
                    bkw.memory["ram"]["A9GcomAvailable"] = True
                    errorCells= ((0, 0, 0, 0, 0, -120, 0, 65535),)
                    return(errorCells)
                lib.time.sleep_ms(100)
        if ans.decode('utf-8')[0] == "(":
            cells = ans.decode('utf-8').rstrip()
        cells = eval(cells)
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(cells)

    except Exception as ex:
        print("Mira el error getCells()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        bkw.memory["ram"]["A9GcomAvailable"] = True
        errorCells= ((0, 0, 0, 0, 0, -120, 0, 65535),)
        return(errorCells)


def getRawCellsShorted(maxReturn_C=2):
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at getRawCellsShorted, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break  
        bkw.memory["ram"]["bloquedtask"] = 'getRawCellsShorted' + " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        bkw.memory["ram"]["A9GcomAvailable"] = False
        readAndCleanALL()

        bkw.A9G_uart.write("getCellsShorted({})\r\n".format(maxReturn_C))
        lib.time.sleep_ms(200)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd)  #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
        ans = bkw.A9G_uart.readline()

        lib.time.sleep_ms(100)
        while ans is not None:
            if ans.decode('utf-8')[0] == "'":
                #print('A9G ans:', ans)
                cells = ans.decode('utf-8').rstrip()
            ans = bkw.A9G_uart.readline()
            lib.time.sleep_ms(100)
        cells = eval(cells)
        #QtyCell = eval(cells[0]) # las celdas no puede ser mas de 6, con un digito estaria ok
        cells = cells[0:len(cells)-1] #saco la ultima / externa
        #cells = cells +'/'            # Agrego separador
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(cells)
    except Exception as ex:
        bkw.memory["ram"]["A9GcomAvailable"] = True
        print("Mira el error getRawCellsShorted()")
        print("==>>>")
        print(ex)
        print("^^^^^")  
        errorCells= '1C/0;0;0-0,120'
        return(errorCells)
    
def getRawCells(maxReturn_C=2):
    try:
        for w in range(60):
            if w == 14:
                A9G_EN(1)
                A9G_Serial(1)
                lib.time.sleep(5)
                bkw.memory["ram"]["A9GcomAvailable"] = True
                return('')
                
            if bkw.memory["ram"]["A9GcomAvailable"] == False:
                print(" wait for A9GcomAvailable = True at getRawCells, blockedTask is {}".format(bkw.memory["ram"]["bloquedtask"]))
                lib.time.sleep(1)
            else:
                break  
        bkw.memory["ram"]["A9GcomAvailable"] = False
        bkw.memory["ram"]["bloquedtask"] = 'getRawCells' + " - "+ str(lib.time.localtime(lib.time.time())[5])+":"+str(lib.time.localtime(lib.time.time())[6])
        readAndCleanALL()
        bkw.A9G_uart.write("getCells({})\r\n".format(maxReturn_C))
        lib.time.sleep_ms(100)
        cmd = bkw.A9G_uart.readline() #leo respuesta, la primera es el comando
        #print('A9G cmd:', cmd)  #cmd.decode('utf-8').rstrip()) # imprimo lo que leo
        lib.time.sleep_ms(100)
        ans = bkw.A9G_uart.readline()
        while ans is not None:
            if ans.decode('utf-8')[0] == "'":
                #print('A9G ans:', ans)
                cells = ans.decode('utf-8').rstrip()
            ans = bkw.A9G_uart.readline()
            lib.time.sleep_ms(100)
        cells = eval(cells)
        #QtyCell = eval(cells[0]) # las celdas no puede ser mas de 6, con un digito estaria ok
        cells = cells[0:len(cells)-1] #saco la ultima / externa
        #cells = cells +'/'            # Agrego separador
        bkw.memory["ram"]["A9GcomAvailable"] = True
        return(cells)
    
    except Exception as ex:
        bkw.memory["ram"]["A9GcomAvailable"] = True
        print("Mira el error getRawCells()")
        print("==>>>")
        print(ex)
        print("^^^^^")  
        errorCells= '1C/0-0-0-0,120'
        return(errorCells)
        
        
def getAGPS(apikey =  ''):
    try:
        readAndCleanALL()
        cells = getCells()
        QtyCells = len(cells)
        j = dict(cellTowers=tuple(dict(mobileCountryCode=mobileCountryCode, mobileNetworkCode=mobileNetworkCode, locationAreaCode=locationAreaCode, cellId=cellId, Bsic=Bsic, signalStrength=signalStrength,  RxLevSub=RxLevSub) for mobileCountryCode, mobileNetworkCode,locationAreaCode, cellId, Bsic, signalStrength,  RxLevSub,  _ in cells ))
        j = lib.json.dumps(j)
        j = lib.json.loads(j)
        bkw.sta_if.active(True)
        onAirWifis = bkw.sta_if.scan()
        QtyWifis = len(onAirWifis)
        w = dict(wifiAccessPoints=tuple(dict(macAddress=lib.ubinascii.hexlify(macAddress,':').decode(), signalStrength=signalStrength) for SSID, macAddress, Channel, signalStrength, AuthMethod,  _ in onAirWifis ))
        j.update(w)  # sumo los dos jsons(j+w)
        try:
            T0 = lib.time.time()
            r = lib.urequests.post('https://www.googleapis.com/geolocation/v1/geolocate?key=AIzaSyCW-qcNeQc_-VKtdWLs7-sQmUqNjI7cJ_M', json=j)
            responseTime = lib.time.time() - T0
            lat = r.json()['location']['lat']
            lon = r.json()['location']['lng']
            accuracy = r.json()['accuracy']
            # print('getAGPS -> {},{} {}Cells {}wifis (accuracy= {}m, rt:{}s)'.format(lat,lon,QtyCells,QtyWifis,accuracy,responseTime))
            r.close()
            return(lat,lon,QtyCells,QtyWifis,accuracy,responseTime)
        except Exception as ex:
            print(ex)
            return(0,0,0,0,0,0)

    except Exception as ex:
        print("Mira el error getAGPS()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        return(0,0,0,0,0,0)

def getRawWifis(maxReturn_W=4):
    try:
#        if not bkw.sta_if.isconnected():
#            bkw.sta_if.active(True)
#            onAirWifis = bkw.sta_if.scan()
#            bkw.sta_if.active(False)
#        else:
#            onAirWifis = bkw.sta_if.scan()
        bkw.sta_if.active(True)
        onAirWifis = bkw.sta_if.scan()
        if onAirWifis == []:
            return('0W/0,120')
        
        w = tuple(dict(SSID=SSID, BSID=BSID, Channel=Channel, Signal=Signal, AuthMethod=AuthMethod) for SSID, BSID, Channel, Signal, AuthMethod,  _ in onAirWifis )
        wifis = str(len(w))+'W/'
        m=len(w)
        m = min(maxReturn_W,m)
        for k in w[0:m]:
            wifis = wifis + (lib.ubinascii.hexlify(k['BSID'],':').decode()+','+str((-1)*k['Signal'])+',')
        if len(w) != 0: # tengo al menos un wifi
            wifis = wifis[0:len(wifis)-1] # saco la ultima coma
        wifis = wifis
        wifis = wifis.replace(':','')
        return(wifis)

    except Exception as ex:
        print("Mira el error getRawWifis()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        return('0E/0,120')  

def getRawWifisNames(maxReturn_W=3):
     try:
#        if not bkw.sta_if.active():
#            bkw.sta_if.active(True)
#            onAirWifis = bkw.sta_if.scan()
#            bkw.sta_if.active(False)
#        else:
#            onAirWifis = bkw.sta_if.scan()
        bkw.sta_if.active(True)
        onAirWifis = bkw.sta_if.scan()
        if onAirWifis == []:
            return('0/ ,0')
        
        w = tuple(dict(SSID=SSID, BSID=BSID, Channel=Channel, Signal=Signal, AuthMethod=AuthMethod) for SSID, BSID, Channel, Signal, AuthMethod,  _ in onAirWifis )
        wifis = str(len(w))+'/'
        m=len(w)
        m = min(maxReturn_W,m)
        for k in w[0:m]:
            wifis = wifis + (str(k['SSID'].decode("utf-8"))+','+str((-1)*k['Signal'])+',')
        wifis = wifis[0:len(wifis)-1] # saco la ultima coma
        wifis = wifis +'/'
        wifis = wifis.replace(':','')
        return(wifis)

     except Exception as ex:
        print("Mira el error getRawWifisNames()")
        print("==>>>")
        print(ex)
        print("^^^^^") 
        return('0/----,120')
                
def mapClear():
    print('cleaning blynk app Map')
    bkw.blynk.virtual_write(101,"clr")

def areSameWifis(qtyToMatch=5): # compare list in ram/last con la lista actual/
    try:
        lastWifiList = bkw.memory['ram']['lastWifis']
        nowWifiList = wifisOnAir(qtyToMatch)
        matches = 0
        for isMatch in nowWifiList:
            for thisLast in lastWifiList:
                if isMatch == thisLast:
                    matches += 1
        
        qtyWifiLast= len(lastWifiList)          
        return(matches,qtyWifiLast)
    except Exception as ex:
        print("Mira el error getRawWifis()")
        print("==>>>")
        print(ex)
        print("^^^^^")  

    except Exception as ex:
        print("Mira el error areSameWifis()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        return(0,0)
                    
def wifisOnAir(maxReturn_W=5):
    try:
        rawWifis = getRawWifis(maxReturn_W).split('/')[1].split(',')
        wifilist = []
        for i in range(0,len(rawWifis),2):
            wifilist.append(rawWifis[i])
        return(wifilist)
    except Exception as ex:
        print("Mira el error wifisOnAir()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        wifilist = []
        return(wifilist)
        

def IsrSensor1(Pin): # bkw.memory["ram"]["inMotion"] = 0 # captures when no motion for 15s
    bkw.sensor1.irq(handler=IsrSensorBlocked, trigger=lib.machine.Pin.IRQ_RISING)
    bkw.sensor2.irq(handler=IsrSensorBlocked, trigger=lib.machine.Pin.IRQ_RISING)
    bkw.memory["ram"]["lastStopedHits"] = bkw.memory["ram"]["lastStopedHits"] + 1
    bkw.memory["ram"]["lastStopedTime"] = lib.time.time()
    #print("Stop motion Timer reach (int1 S1 Pin15) # {}, at {}".format(bkw.memory["ram"]["lastStopedHits"], nowString(lib.time.localtime(bkw.memory["ram"]["lastStopedTime"] + bkw.TMZ)) ) )
    bkw.memory["ram"]["inMotion"] = 0
    #bkw.memory["ram"]["lastMovingHits"] = 0
    setMotionDetection()

def IsrSensor2(Pin):
    bkw.memory["ram"]["lastMovingHits"] = bkw.memory["ram"]["lastMovingHits"] + 1
    bkw.memory["ram"]["lastMovingTime"] = lib.time.time()
    #print("Motion Detection (int2 S2 Pin2) # {}, at {}".format(bkw.memory["ram"]["lastMovingHits"], nowString(lib.time.localtime(bkw.memory["ram"]["lastMovingTime"] + bkw.TMZ)) ) )
    bkw.memory["ram"]["inMotion"] = 1
    bkw.memory["ram"]["lastStopedHits"] = 0
    setMotionDetection()

def IsrSensorBlocked(Pin):
    return()
        
def setMotionDetection():
    try:
    #print("---->>>> setMotionDetection()")
        s = bkw.config['hardwareSettings']['vibraSensibility']
        s = '0'+str(s) if int(s) < 10 else str(s) 
        sensibilidad = lib.ubinascii.unhexlify(s)
        
        bkw.sensor1.irq(handler=IsrSensorBlocked, trigger=lib.machine.Pin.IRQ_RISING)
        bkw.sensor2.irq(handler=IsrSensorBlocked, trigger=lib.machine.Pin.IRQ_RISING)
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG2, lib.ubinascii.unhexlify(b'40'))         #rst,normal mode
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1, lib.ubinascii.unhexlify(b'64'))         #ODR=50,sleep ODR=12.5,enter standby mode
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG2, lib.ubinascii.unhexlify(b'04'))         #normal mode, auto-sleep enabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG3, lib.ubinascii.unhexlify(b'42'))         #transient enabled wake up from auto-sleep IPOL 1 act / 42 = bin2hex('0b01000010')
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG4, lib.ubinascii.unhexlify(b'a0'))         #ASLP INT enabled, Transient INT enabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG5, lib.ubinascii.unhexlify(b'80'))         #auto-sleep -> INT1,transient -> INT2
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_XYZ_DATA_CFG, lib.ubinascii.unhexlify(b'10'))      #HPF output enabled , 2g mode
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_HP_FILTER_CUTOFF, lib.ubinascii.unhexlify(b'00'))  #HPF=2Hz   
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PL_CFG, lib.ubinascii.unhexlify(b'80'))            #P/L disabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_FF_MT_CFG, lib.ubinascii.unhexlify(b'00'))         #MT/FF disabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_TRANSIENT_CFG, lib.ubinascii.unhexlify(b'0e'))     #TRANSIENT ELE latch disabled, HPF enable, transient x/y/z axes enabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_TRANSIENT_THS, sensibilidad)     #transient threshold=0.126g
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_TRANSIENT_COUNT, lib.ubinascii.unhexlify(b'00'))   #  
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_PULSE_CFG, lib.ubinascii.unhexlify(b'00'))         #tap/double tap disabled
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_ASLP_COUNT, lib.ubinascii.unhexlify(b'0a'))        #at .3s units, set the minimum time required to be judged from move to stop, 0a set to 3 sec, 37 set 15s, 64 set 30s
        bkw.busI2C.writeto_mem(bkw.A_ADDRESS, bkw.A_CTRL_REG1, lib.ubinascii.unhexlify(b'65'))
        #print("---->>>> enabling IRQs")
        lib.time.sleep_ms(50)
        bkw.sensor1.irq(handler=IsrSensor1, trigger=lib.machine.Pin.IRQ_RISING)
        bkw.sensor2.irq(handler=IsrSensor2, trigger=lib.machine.Pin.IRQ_RISING)

    except Exception as ex:
        print("Mira el error wifisOnAir()")
        print("==>>>")
        print(ex)
        print("^^^^^")  

def sendLocationMsg(maxReturn_W =3,maxReturn_C=1):
    
    # bkw.uid bkw.uid[len(bkw.uid)-6:]
    # status 0 No Alarmado memory["ram"]["bootStatus"] = 'UnArmed' or Armed, 1 =Alarmed
    # Charge
    # indexLocation
    # since
    # wifichg
    # motionStats
    # satStats satTrk,satVis
    # Type G GPS / Type R RAW
    # R1 Part 1
    # R2 Part 2
    # data >> /#W/W1,L1,..,W3,L3/#C/C1,S1,C2,S2
    try:
        if not isA9Gconnected(20):
            print("A9G reseted now to try reconnect")
            A9G_EN(1)
            A9G_Serial(1)
            lib.time.sleep(5)
            notConnectedMsg = "sendLocationMsg and A9G is not connected, isA9Gconnected() was False"
            print(notConnectedMsg)
            return(notConnectedMsg)

        bootStatusMsg = 1 if bkw.memory["ram"]["bootStatus"] == 'Alarmed' else 0
        charge = str(battery()[1])
        bkw.memory["ram"]["smsPointIndex"] = bkw.memory["ram"]["smsPointIndex"] + 1
        pointIndex = str(bkw.memory["ram"]["smsPointIndex"])
        elapsedTime = str(int((lib.time.time() - bkw.memory["ram"]["alarmedTimeZero"])/60)) if bkw.memory["ram"]["bootStatus"] == 'Alarmed' else str(int((lib.time.time() - bkw.memory["ram"]["bootTime"])/60))
        wifiNoChg, wifiTotal = areSameWifis()
        wifiChgStats = str(wifiNoChg) +','+ str(wifiTotal)
        Motion = 'N'
        Periods = 0
        if bkw.memory["ram"]["inMotion"] == 0: # if Stoped, equal 0
            Motion = 'S'
            Periods =  str(bkw.memory["ram"]["lastStopedHits"])[-2:] #me quedo ultimas dos cifras
            timeStampString = DateTimeStringShort(bkw.memory["ram"]["lastMovingTime"])
        if bkw.memory["ram"]["inMotion"] == 1 : # if moving, > 0
            Motion = 'M'
            Periods =  str(bkw.memory["ram"]["lastMovingHits"])[-2:] #me quedo ultimas dos cifras
            timeStampString = DateTimeStringShort(bkw.memory["ram"]["lastStopedTime"])
        motionStats = Periods + Motion + timeStampString
        #intento obterner GPS
        ( lastLocationType, DateTime, tracking, visibles, lat, lon, accuracy, speed, curse )   = fix_GPS()
        satStats = str(tracking) +','+ str(visibles)
        locMsg =  bkw.uid[len(bkw.uid)-6:] +'/'+ str(bootStatusMsg)    
        locMsg =  locMsg +'/'+ charge
        locMsg =  locMsg +'/'+ pointIndex
        locMsg =  locMsg +'/'+ elapsedTime
        locMsg =  locMsg +'/'+ motionStats
        locMsg =  locMsg +'/'+ satStats
        locMsg =  locMsg +'/'+ lastLocationType
        
        if lastLocationType ==  'G':
            gpsData = str(DateTime) +','+ "{:.4f}".format(lat)+','+"{:.4f}".format(lon)+','+str(accuracy)+','+str(int(speed))+','+str(int(curse))
            bkw.memory["ram"]["lastGPSLocationLat"] = lat
            bkw.memory["ram"]["lastGPSLocationLon"] = lon
            bkw.memory["ram"]["lastGPSAccuracy"] = 5
            locData = getRawWifis(1) +'/'+ getRawCells(1)+'/'+ gpsData
        else:
            if len(locMsg) > 46:
                locData =  getRawWifis(2) +'/'+ getRawCellsShorted(1)
            else:
                if wifiTotal >1:
                    locData =  getRawWifis(3) +'/'+ getRawCellsShorted(2)
                else:
                    locData = getRawWifis(1) +'/'+ getRawCellsShorted(4)

        locMsg =  locMsg +'/'+ locData
        sendSMS(locMsg)
        setMotionDetection() # reactivate incase not active setMotionDetection()
        return(locMsg)

    except Exception as ex:
        print("error on sendLocationMsg()")
        print("==>>>")
        print(ex)
        return('')
        print("^^^^^")
        
def callOwner(callTimeOut_s=30): ## To do get a better isconnected logic
    try:
        if not isA9Gconnected(60): # until connected or 60 times 
            print("A9G reseted now to try reconnect")
            A9G_EN(1)
            A9G_Serial(1)
            lib.time.sleep(10)

        bkw.A9G_uart.write("cellular.dial('{}')\r\n".format(str(bkw.owner_phone).replace('+', '')))
        lib.time.sleep_ms(50)
        readAndPrintALL()
        lib.time.sleep(callTimeOut_s)
        bkw.A9G_uart.write("cellular.dial(False)\r\n")
        readAndPrintALL()
        print("owner called")
        bkw.memory["ram"]["A9GcomAvailable"] = True
    except Exception as ex:
        print("error on callOwner()")
        print("==>>>")
        print(ex)
        print("^^^^^")
                
def GGMMpMM2GpD(value):
    try:
        ggmmpmm = str(value)
        sign = '-' if ggmmpmm.find('-') >= 0 else '+'
        gg = int(ggmmpmm[1:ggmmpmm.find('.')-2]) if (sign == '-' or sign == '+' ) else int(ggmmpmm[0:ggmmpmm.find('.')-2])
        mm = float(ggmmpmm[ggmmpmm.find('.')-2:])/60
        GpD = -gg-mm if sign == '-' else gg+mm
        return(GpD)
    except Exception as ex:
        print("error on GGMMpMM2GpD()")
        print("==>>>")
        print(ex)  
        print("^^^^^")
        
def updateBlynkLoc():
    #print('----> bkw.blynk.disconnect() anti bug/blynk lib ')
    #bkw.blynk.disconnect()
    try:
        ( locationType, GPS_DateTime, GPS_tracking, GPS_visibles, GPS_lat, GPS_lon, GPS_accuracy, GPS_speed, GPS_curse )  = fix_GPS()
        ( AGPS_lat, AGPS_lon, AGPS_QtyCells, AGPS_QtyWifis, AGPS_accuracy, AGPS_responseTime) = getAGPS()
        if locationType == 'G':
            lat = GPS_lat
            lon = GPS_lon
            accuracy = GPS_accuracy
        else: 
            locationType = 'A'
            lat = AGPS_lat
            lon = AGPS_lon
            accuracy = AGPS_accuracy

        bkw.memory["ram"]["lastLocationType"] = locationType
        bkw.memory["ram"]["lastLocationLat"] = lat
        bkw.memory["ram"]["lastLocationLon"] = lon
        bkw.memory["ram"]["lastAccuracy"] = accuracy
        bkw.memory["ram"]["lastQtyWifis"] = AGPS_QtyWifis
        bkw.memory["ram"]["lastQtyCells"] = AGPS_QtyCells
        bkw.memory["ram"]["satTracking"] = GPS_tracking
        bkw.memory["ram"]["satVisibles"] = GPS_visibles
        bkw.memory["ram"]["lastSpeed"] = GPS_speed
        bkw.memory["ram"]["lastCurse"] = GPS_curse
        
        bkw.memory["ram"]["blynkPointIndex"] = bkw.memory["ram"]["blynkPointIndex"] + 1
        bkw.memory["ram"]["BlynkTimestampStr"] = nowString()

        bkw.blynk.connect()
        if bkw.blynk.connected() is False:
            lib.time.sleep(1)
        mapinfo = 'Home~{}m #{}@{}'.format(str(accuracy), str(bkw.memory["ram"]["blynkPointIndex"]), nowString()[-13:-3] )
        print('mapinfo', mapinfo)
        bkw.blynk.virtual_write(101, bkw.memory["ram"]["blynkPointIndex"], bkw.memory["ram"]["lastLocationLat"], bkw.memory["ram"]["lastLocationLon"], mapinfo )
        print(bkw.memory["ram"]["lastLocationLat"], bkw.memory["ram"]["lastLocationLon"], mapinfo)
        elapsedTime = int((lib.time.time() - bkw.memory["ram"]["alarmedTimeZero"])/60) if bkw.memory["ram"]["bootStatus"] == 'Alarmed' else int((lib.time.time() - bkw.memory["ram"]["bootTime"])/60)
        
        bkw.blynk.virtual_write(102, '{}'.format(bkw.memory["ram"]["blynkPointIndex"]))
        bkw.blynk.virtual_write(103, '{}'.format(elapsedTime))
        bkw.blynk.virtual_write(104, '{}'.format(bkw.memory["ram"]["lastAccuracy"]))
        bkw.blynk.virtual_write(105, '{}'.format(bkw.memory["ram"]["BlynkTimestampStr"]))
        bkw.blynk.virtual_write(106, '{}'.format(bkw.memory["ram"]["lastQtyWifis"]))
        bkw.blynk.virtual_write(107, '{}'.format(bkw.memory["ram"]["lastQtyCells"])) 
        bkw.blynk.virtual_write(108, '{}'.format(bkw.memory["ram"]["satTracking"]))
        bkw.blynk.virtual_write(109, '{}'.format(bkw.memory["ram"]["satVisibles"])) 
        bkw.blynk.virtual_write(116, '{:.1f}'.format(GPS_speed)) #to do
        bkw.blynk.virtual_write(117, '{:.1f}'.format(GPS_curse)) 
        if (0*45) + 22.5 < GPS_curse and GPS_curse <= (0*45) +67.5:
            namedCurse = 'NE'
        if (1*45) + 22.5 < GPS_curse and GPS_curse <= (1*45) +67.5:
            namedCurse = 'E'
        if (2*45) + 22.5 < GPS_curse and GPS_curse <= (2*45) +67.5:
            namedCurse = 'SE'
        if (3*45) + 22.5 < GPS_curse and GPS_curse <= (3*45) +67.5:
            namedCurse = 'S'
        if (4*45) + 22.5 < GPS_curse and GPS_curse <= (4*45) +67.5:
            namedCurse = 'SO'
        if (5*45) + 22.5 < GPS_curse and GPS_curse <= (5*45) +67.5:
            namedCurse = 'O'
        if (6*45) + 22.5 < GPS_curse and GPS_curse <= (6*45) +67.5:
            namedCurse = 'NO'
        if (7*45) + 22.5 < GPS_curse or GPS_curse <= (0*45) + 22.5:
            namedCurse = 'N'
        bkw.blynk.virtual_write(118, namedCurse)
        bkw.blynk.virtual_write(119, '{:.5f},{:.5f}'.format(bkw.memory["ram"]["lastLocationLat"],bkw.memory["ram"]["lastLocationLon"]) )

    except Exception as ex:
        print("Mira el error updateBlynkLoc()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        
def toggleBlynkLed():
    if bkw.memory["ram"]["awakeBlynkMsg"] == False:
        bkw.memory["ram"]["awakeBlynkMsg"] = True
        bkw.blynk.virtual_write(254, 255 if bkw.memory["ram"]["awakeBlynkMsg"] else 0)
    else:
        bkw.memory["ram"]["awakeBlynkMsg"] = False
        bkw.blynk.virtual_write(254, 255 if bkw.memory["ram"]["awakeBlynkMsg"] else 0)
         
def updateBlynkStatusESP():
    try:
        if lib.time.time()%30 == 1: #refresco lento
            bkw.blynk.virtual_write(53, '{}'.format(bkw.memory["ram"]["HomeWifiNameNow"]))
            bkw.blynk.virtual_write(54, '{}'.format(bkw.sta_if.ifconfig()[0]))
            bkw.memory["ram"]["batVolts"], bkw.memory["ram"]["batCharge"] = battery()
            bkw.blynk.virtual_write(131, '{}'.format(bkw.memory["ram"]["batVolts"]))
            bkw.blynk.set_property( 131, 'color', bkw.colors['White'] if bkw.memory["ram"]["batCharge"] > 20 else bkw.colors['FireBrick'])
            bkw.memory["ram"]["bkwTemp"] = '{:.1f}'.format( (lib.esp32.raw_temperature() - 32)/1.8 )
            bkw.blynk.virtual_write(133, '{}'.format(bkw.memory["ram"]["bkwTemp"]))
            bkw.blynk.run()
            elapsedTime = int((lib.time.time() - bkw.memory["ram"]["alarmedTimeZero"])/60) if bkw.memory["ram"]["bootStatus"] == 'Alarmed' else int((lib.time.time() - bkw.memory["ram"]["bootTime"])/60)
            bkw.blynk.virtual_write(103, '{}'.format(elapsedTime))
            bkw.blynk.run()

        if lib.time.time()%10 == 1:
            strongest2Wifis =  getRawWifisNames(2).split('/')
            qtyWifis = int(strongest2Wifis[0])
            if qtyWifis > 0:
                bkw.blynk.virtual_write(126, '{}'.format(strongest2Wifis[1].split(',')[0]))
                bkw.blynk.virtual_write(127, '{}'.format(-1*int(strongest2Wifis[1].split(',')[1])))
                bkw.blynk.set_property( 126, 'color', bkw.colors['White'] )
                bkw.blynk.set_property( 127, 'color', bkw.colors['White'] )
            else:
                bkw.blynk.virtual_write(126, '---')
                bkw.blynk.virtual_write(127, None)
                bkw.blynk.set_property( 126, 'color', bkw.colors['Gray'] )
                bkw.blynk.set_property( 127, 'color', bkw.colors['Gray'] )
    
            if qtyWifis > 1:
                bkw.blynk.virtual_write(128, '{}'.format(strongest2Wifis[1].split(',')[2]))
                bkw.blynk.virtual_write(129, '{}'.format(-1*int(strongest2Wifis[1].split(',')[3])))
                bkw.blynk.set_property( 128, 'color', bkw.colors['White'] )
                bkw.blynk.set_property( 129, 'color', bkw.colors['White'] )
            else:
                bkw.blynk.virtual_write(128, '---')
                bkw.blynk.virtual_write(129, None)
                bkw.blynk.set_property( 128, 'color', bkw.colors['Gray'] )
                bkw.blynk.set_property( 129, 'color', bkw.colors['Gray'] )
            
            bkw.blynk.run()

        if lib.time.time()%2 == 1:
            bkw.blynk.virtual_write(110, '{}'.format(bkw.memory["ram"]["inMotion"]))
            bkw.blynk.virtual_write(111, '{}'.format(bkw.memory["ram"]["lastMovingTime"]-lib.time.time())) #delta Secs since last Move
            bkw.blynk.virtual_write(112, '{}'.format(bkw.memory["ram"]["lastStopedHits"]))
            bkw.blynk.virtual_write(113, '{}'.format(bkw.memory["ram"]["lastStopedTime"]))
            bkw.blynk.virtual_write(114, '{}'.format(bkw.memory["ram"]["lastMovingHits"]))
            bkw.blynk.virtual_write(115, '{}'.format(bkw.memory["ram"]["lastMovingTime"]))
            passUpdate = 1
            if bkw.memory["ram"]["satTracking"] >= 4:
                passUpdate = 0
                ( locationType, GPS_DateTime, GPS_tracking, GPS_visibles, GPS_lat, GPS_lon, GPS_accuracy, GPS_speed, GPS_curse )  = fix_GPS()
                bkw.memory["ram"]["lastLocationType"] = locationType
                bkw.memory["ram"]["lastLocationLat"] = GPS_lat
                bkw.memory["ram"]["lastLocationLon"] = GPS_lon
                bkw.memory["ram"]["lastAccuracy"] = GPS_accuracy
                bkw.memory["ram"]["satTracking"] = GPS_tracking
                bkw.memory["ram"]["satVisibles"] = GPS_visibles
                bkw.memory["ram"]["lastSpeed"] = GPS_speed
                bkw.memory["ram"]["lastCurse"] = GPS_curse
                bkw.blynk.virtual_write(119, '{:.5f},{:.5f}'.format(bkw.memory["ram"]["lastLocationLat"],bkw.memory["ram"]["lastLocationLon"]) )
                bkw.blynk.virtual_write(116, '{:.1f}'.format(GPS_speed)) #to do
                bkw.blynk.set_property(116, 'color', bkw.colors['White'])            
                bkw.blynk.virtual_write(117, '{:.1f}'.format(GPS_curse)) 
                bkw.blynk.set_property(117, 'color', bkw.colors['White'])            
                if (0*45) + 22.5 < GPS_curse and GPS_curse <= (0*45) +67.5:
                    namedCurse = 'NE'
                if (1*45) + 22.5 < GPS_curse and GPS_curse <= (1*45) +67.5:
                    namedCurse = 'E'
                if (2*45) + 22.5 < GPS_curse and GPS_curse <= (2*45) +67.5:
                    namedCurse = 'SE'
                if (3*45) + 22.5 < GPS_curse and GPS_curse <= (3*45) +67.5:
                    namedCurse = 'S'
                if (4*45) + 22.5 < GPS_curse and GPS_curse <= (4*45) +67.5:
                    namedCurse = 'SO'
                if (5*45) + 22.5 < GPS_curse and GPS_curse <= (5*45) +67.5:
                    namedCurse = 'O'
                if (6*45) + 22.5 < GPS_curse and GPS_curse <= (6*45) +67.5:
                    namedCurse = 'NO'
                if (7*45) + 22.5 < GPS_curse or GPS_curse <= (0*45) + 22.5:
                    namedCurse = 'N'
                bkw.blynk.virtual_write(118, namedCurse)
                bkw.blynk.set_property( 118, 'color', bkw.colors['White'])            
            else:
                if passUpdate == 0:
                    bkw.blynk.set_property( 116, 'color', bkw.colors['Gray']) 
                    bkw.blynk.set_property( 117, 'color', bkw.colors['Gray']) 
                    bkw.blynk.set_property( 118, 'color', bkw.colors['Gray']) 

            toggleBlynkLed()
            bkw.blynk.run()

    except Exception as ex:
        print("Mira el error en updateBlynkStatusESP()")
        print("==>>>")
        print(ex)
        print("^^^^^")
                
def updateBlynkStatusA9G():
    try:
        cell = getRawCells(1).split('/')
        bkw.memory["ram"]["cellQty"] = cell[0].replace('C','')
        bkw.memory["ram"]["cellID"]  = cell[1].split(',')[0]
        bkw.memory["ram"]["cellSignal"] = '-' + cell[1].split(',')[1]
        bkw.memory["ram"]["A9Gconnected"] = isA9Gconnected()
        ( satTracking, satVisibles) = getSats()
        bkw.memory["ram"]["satTracking"] = satTracking
        bkw.memory["ram"]["satVisibles"] = satVisibles

        bkw.blynk.virtual_write(107, '{}'.format(bkw.memory["ram"]["cellQty"]))

        bkw.blynk.virtual_write(108, '{}'.format(bkw.memory["ram"]["satTracking"]))  
        bkw.blynk.set_property( 108, 'color', bkw.colors['White'] if bkw.memory["ram"]["satTracking"] >= 4 else bkw.colors['Gray'])
        bkw.blynk.virtual_write(109, '{}'.format(bkw.memory["ram"]["satVisibles"]))
        bkw.blynk.set_property( 109, 'color', bkw.colors['White'] if bkw.memory["ram"]["satTracking"] >= 4 else bkw.colors['Gray'])

        bkw.blynk.virtual_write(120, 255 if bkw.memory["ram"]["A9Gconnected"] else 0)
        bkw.blynk.virtual_write(122, '{}'.format(bkw.memory["ram"]["cellID"]))
        bkw.blynk.set_property( 122, 'color', bkw.colors['White'] if bkw.memory["ram"]["A9Gconnected"] else bkw.colors['Gray'])
        bkw.blynk.virtual_write(123, '{}'.format(bkw.memory["ram"]["cellSignal"]))
        bkw.blynk.set_property( 123, 'color', bkw.colors['White'] if bkw.memory["ram"]["A9Gconnected"] else bkw.colors['Gray'])

        bkw.blynk.run()

    
    except Exception as ex:
        print("Mira el error en updateBlynkStatusA9G()")
        print("==>>>")
        print(ex)
        print("^^^^^")

def updateBlynkIds():
    try:
        (simOk,IMSI) = isA9GwithSIM()
        emei = get_emei()
        hash_BlyinkUI = bkw.config['Secrets']['blynkInternet']
    
        bkw.blynk.virtual_write(90, '{}'.format( bkw.uid ))
        bkw.blynk.virtual_write(91, '{}'.format( emei ))
        bkw.blynk.virtual_write(92, '{}'.format( IMSI ))
        bkw.blynk.virtual_write(95, '{}'.format( hash_BlyinkUI ))
  
        bkw.blynk.run()

    
    except Exception as ex:
        print("Mira el error en updateBlynkStatusA9G()")
        print("==>>>")
        print(ex)
        print("^^^^^")

def updateBlynkConfig():
    try:
        if bkw.memory["ram"]["configChanged"] == 1: # config file related
            
            bkw.blynk.virtual_write(40, '{}'.format(bkw.config['reportTo']['owner_phone']))
            bkw.blynk.virtual_write(41, '{}'.format(bkw.config['AP']['AP_pass']))
            bkw.blynk.virtual_write(42, '{}'.format(bkw.config['APN']['APN_NAME']))
            bkw.blynk.virtual_write(43, '{}'.format(bkw.config['APN']['APN_USER']))
            bkw.blynk.virtual_write(44, '{}'.format(bkw.config['APN']['APN_PASS']))
    
            bkw.blynk.virtual_write(45, '{}'.format(bkw.config['reportTo']['homeWifis'][0]['SSID']))
            bkw.blynk.virtual_write(46, '{}'.format(bkw.config['reportTo']['homeWifis'][0]['pass']))
            bkw.blynk.virtual_write(47, '{}'.format(bkw.config['reportTo']['homeWifis'][1]['SSID']))
            bkw.blynk.virtual_write(48, '{}'.format(bkw.config['reportTo']['homeWifis'][1]['pass']))
            bkw.blynk.virtual_write(49, '{}'.format(bkw.config['reportTo']['homeWifis'][2]['SSID']))
            bkw.blynk.virtual_write(50, '{}'.format(bkw.config['reportTo']['homeWifis'][2]['pass']))
            bkw.blynk.virtual_write(51, '{}'.format(bkw.config['reportTo']['homeWifis'][3]['SSID']))
            bkw.blynk.virtual_write(52, '{}'.format(bkw.config['reportTo']['homeWifis'][3]['pass']))
    
            bkw.blynk.virtual_write(55, '{}'.format(bkw.config['hardwareSettings']['vibraSensibility']))
            bkw.blynk.virtual_write(56, '{}'.format(bkw.config['hardwareSettings']['touchSensibility']))
                    
            bkw.blynk.virtual_write(62, '{}'.format(bkw.config['Timers']['unArmedSelfWakeTimer_m']))
            bkw.blynk.virtual_write(63, '{}'.format(bkw.config['Timers']['armedSelfWakeTimer_m']))

            bkw.blynk.virtual_write(64, '{}'.format(bkw.config['Timers']['periodLocationPO_s']))
            bkw.blynk.virtual_write(65, '{}'.format(bkw.config['Timers']['periodLocationA1_s']))
            bkw.blynk.virtual_write(66, '{}'.format(bkw.config['Timers']['alarmedActive1_m']))
            bkw.blynk.virtual_write(67, '{}'.format(bkw.config['Timers']['alarmedSleep1_m']))
            bkw.blynk.virtual_write(68, '{}'.format(bkw.config['Timers']['periodLocationA2_s']))
            bkw.blynk.virtual_write(69, '{}'.format(bkw.config['Timers']['alarmedActive2_m']))
            bkw.blynk.virtual_write(70, '{}'.format(bkw.config['Timers']['alarmedSleep2_m']))
            
            bkw.memory["ram"]["configChanged"] = 0
            
    except Exception as ex:
        print("Mira el error fun.updateBlynkConfig()")
        print("==>>>")
        print(ex)
        print("^^^^^")

   
def tryHomeWifi():
    try:
        for lookup in range(len(bkw.config['reportTo']['homeWifis'])):
            print('wifi scaning for {}'.format(bkw.config['reportTo']['homeWifis'][lookup]['SSID']))
            if getRawWifisNames(5).find(bkw.config['reportTo']['homeWifis'][lookup]['SSID']) > 0:
                print('Config Wifi available')
                print('Found and trying', bkw.config['reportTo']['homeWifis'][lookup]['SSID'])
                bkw.sta_if.active(True)
                bkw.sta_if.connect(bkw.config['reportTo']['homeWifis'][lookup]['SSID'],bkw.config['reportTo']['homeWifis'][lookup]['pass'])
                print('====>> Connected Wifi:', bkw.config['reportTo']['homeWifis'][lookup]['SSID'])
                bkw.ftp.start()
                print('[waiting for an IP ]',end='')
                while bkw.sta_if.ifconfig()[0] == '0.0.0.0':
                    lib.time.sleep(1)
                    print('.',end='')
                print('===>> ftp started ok at: bkw.sta_if.ifconfig()[0]', bkw.sta_if.ifconfig()[0])
                try:
                    lib.ntptime.settime() # clock synced
                    print('time post ntp sync:', nowString())
                except Exception as error:
                    print('lib.ntptime.settime() ==>> error')
                    print(error)
                    print('---------------')
                print('===>> nowString(), now is ', nowString( lib.time.localtime(lib.time.time() + bkw.TMZ ) ))
                lib.webrepl.start()
                bkw.memory["ram"]["isHomeWifiNow"] = True
                bkw.memory["ram"]["HomeWifiNameNow"] = bkw.config['reportTo']['homeWifis'][lookup]['SSID']
                return(True)
        
        return(False)

    except Exception as ex:
        print("Mira el error tryHomeWifi()")
        print("==>>>")
        print(ex)
        print("^^^^^")
        return(False)       
