print(' ############## Importing bkw from FS ############### ')

import lib_full as lib
import fun



################################################### initial ConfigParser
#with open('bikewatch.cfg') as r: # with open('bikewatch.cfg') as r:
#   config = lib.json.load(r)

#with open('bikewatch.cfg', 'w') as f:
#        lib.json.dump(config, f)
        
def loadConfig(configFile = 'bikewatch.cfg'):
    ls = lib.uos.listdir()
    config = {}
    for filename in ls:
        if filename == configFile:
            config = {}
            with open(configFile) as r: # with open('bikewatch.cfg') as r:
                config = lib.json.load(r)
            r.close()
    return(config)
config = loadConfig('bikewatch.cfg')


def saveConfig(configFile = 'bikewatch.cfg'):
    with open(configFile, 'w') as f:
        lib.json.dump(config, f)
    f.close()
    print('{}.cfg Saved!'.format(configFile))
    msg = uid +'|'+'Bikewatch Updated'


uid = lib.ubinascii.hexlify(lib.machine.unique_id(),':').decode().replace(':','')    
BatteryCalibration_A = config['hardwareSettings']['BatteryCalibration_A']
BatteryCalibration_B = config['hardwareSettings']['BatteryCalibration_B']
vibraSensibility = config['hardwareSettings']['vibraSensibility']
touchSensibility = config['hardwareSettings']['touchSensibility']

AP_name = config['AP']['AP_name']
AP_pass = config['AP']['AP_pass']

# config owner
owner_phone = config['reportTo']['owner_phone']
registered_device = [(b'\xa4K\xd536\xd2',)][0][0]

# config platformSMS
smsServer_phone = config['reportTo']['smsServer_phone']

# config timers
periodCheckOwner = config['Timers']['periodCheckOwner']
periodLocation = config['Timers']['periodLocationPO_s']
periodBatt = config['Timers']['periodBatt']

# config Cell Operator
APN_NAME = config['APN']['APN_NAME']
APN_USER = config['APN']['APN_USER']
APN_PASS = config['APN']['APN_PASS']

# config modes
USE_DATA = config['Flags']['USE_DATA']
SendMaps = config['Flags']['SendMaps']
SendRAW = config['Flags']['SendRAW']
USE_Google = config['Flags']['USE_Google']

# Status
# Alarmed = config['bootStatus']['Alarmed']


################################################### initial object/intances

TMZ = - 3*3600 #timezone ART

sta_if = lib.network.WLAN(lib.network.STA_IF)      
ftp = lib.ftp_thread.FtpTiny()

bikewatch_AP =  lib.network.WLAN(lib.network.AP_IF)
A9G_uart = lib.machine.UART(1, baudrate=115200, bits=8, parity=None, stop=1, tx=27, rx=26, rts=-1, cts=-1, txbuf=512, rxbuf=512, timeout=1, timeout_char=500)     #default GPIO for UART1 is 9 and 10, and for UART2 is 16 and 17. GPIO 9 and 10 are used for the SPI flash, GPIO 16 and 17 for the SPI RAM. So the defaults must be changed.

scl = lib.machine.Pin(18, lib.machine.Pin.IN, lib.machine.Pin.PULL_UP)  # SCL
sda = lib.machine.Pin(19, lib.machine.Pin.IN, lib.machine.Pin.PULL_UP)  # SDA
busI2C = lib.machine.I2C(0) # pin 18 /19

vbat36 = lib.machine.ADC(lib.machine.Pin(36))
vbat36.atten(vbat36.ATTN_11DB)

led = lib.machine.Pin(13, lib.machine.Pin.OUT,lib.machine.Pin.PULL_DOWN) #io13 Led 
statusLed = lib.machine.Timer(0)

smsIn = lib.machine.Pin(25, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN) #SMS receive flag Pin / hw interrupt a9g 29
smsOut = lib.machine.Pin(33, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN) #SMS sent hw flag Pin / hw interrupt a9g 26

A9G_power = lib.machine.Pin(0, lib.machine.Pin.OUT, lib.machine.Pin.PULL_DOWN) # set dummy PIN to avoid Pin 12 boot issues
A9G_reset = lib.machine.Pin(0, lib.machine.Pin.OUT, lib.machine.Pin.PULL_DOWN)

sensor1 = lib.machine.Pin(15, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # sensor INT1
sensor2 = lib.machine.Pin(2, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # sensor INT2

p39 = lib.machine.Pin(39, lib.machine.Pin.IN, lib.machine.Pin.PULL_DOWN)   # boton inicio

wake = lib.machine.Pin(32, mode = lib.machine.Pin.IN)
touch = lib.machine.TouchPad(wake)
touch.config(int(config['hardwareSettings']['touchSensibility']))

################################################### initial ram values variables 

memory = {"ram" : {}}
memory["ram"]["uid"] = lib.ubinascii.hexlify(lib.machine.unique_id(),':').decode().replace(':','')
memory["ram"]["bootTime"] = lib.time.time()
memory["ram"]["lastMovingTime"] = lib.time.time()
memory["ram"]["lastStopedTime"] = lib.time.time()
memory["ram"]["inMotion"] = 0
memory["ram"]["lastStopedHits"] = 0
memory["ram"]["lastMovingHits"] = 0
memory["ram"]["configChanged"] = 1
memory["ram"]["FlagA9GENA"] = 0
memory["ram"]["FlagA9GData"] = ''
memory["ram"]["cellQty"] = ''
memory["ram"]["cellID"] = ''
memory["ram"]["cellSignal"] = ''
memory["ram"]["batVolts"] = ''
memory["ram"]["bkwTemp"] = ''
memory["ram"]["A9Gconnected"] = False
memory["ram"]["satTracking"] = 0
memory["ram"]["satVisibles"] = 0
memory["ram"]["isHomeWifiNow"] = False
memory["ram"]["HomeWifiNameNow"] = ''
memory["ram"]["A9GcomAvailable"] = True
memory['ram']['lastWifis'] = [] #fun.wifisOnAir(maxReturn_W=6)
memory["ram"]["awakeBlynkMsg"] = 0
memory["ram"]["statusLed_Blinks"] = 3
memory["ram"]["statusLed_Duration_ms"] = 2000
memory["ram"]["statusLed_waits_ms"] = 1000

################################################### RTC mem
rtc = lib.machine.RTC()
# update ram mem from rtc mem
if rtc.memory() != b'': # if rtc mem is not empty

    rtcmem = lib.json.loads(rtc.memory())

    memory["ram"]["thisBootMode"] = rtcmem['nextBootMode'] if "nextBootMode" in rtcmem else 'normal'
    memory["ram"]["bootStatus"] = rtcmem['bootStatus'] if "bootStatus" in rtcmem else 'UnArmed'
    memory["ram"]["deepSleepCounter"] = rtcmem['deepSleepCounter'] if "deepSleepCounter" in rtcmem else 0
    memory["ram"]["lastDSBattery"] = rtcmem['lastDSBattery'] if "lastDSBattery" in rtcmem else 0
    memory["ram"]["lastTimestamp_s"] = rtcmem['lastTimestamp_s'] if "lastTimestamp_s" in rtcmem else 0
    memory["ram"]["lastDeepSleep_s"] = rtcmem['lastDeepSleep_s'] if "lastDeepSleep_s" in rtcmem else 0
    memory["ram"]["lastLocationType"] = rtcmem['lastLocationType'] if "lastLocationType" in rtcmem else ''
    memory["ram"]["lastLocationLat"] = rtcmem['lastLocationLat'] if "lastLocationLat" in rtcmem else 0
    memory["ram"]["lastLocationLon"] = rtcmem['lastLocationLon'] if "lastLocationLon" in rtcmem else 0
    memory["ram"]["smsPointIndex"] = rtcmem['smsPointIndex'] if "smsPointIndex" in rtcmem else 0
    memory["ram"]["secondsAlarmed"] = rtcmem['secondsAlarmed'] if "secondsAlarmed" in rtcmem else 0
    memory["ram"]["lastWifis"] = rtcmem['lastWifis'] if "lastWifis" in rtcmem else []   
    memory["ram"]["blynkPointIndex"] = rtcmem['blynkPointIndex'] if "blynkPointIndex" in rtcmem else 0
    memory["ram"]["alarmedTimeZero"] = rtcmem['alarmedTimeZero'] if "alarmedTimeZero" in rtcmem else 0
    
else: # RTC mem was empty 

    memory["ram"]["thisBootMode"] = 'normal'
    memory["ram"]["bootStatus"] = 'UnArmed'
    memory["ram"]["deepSleepCounter"] = 0
    memory["ram"]["lastDSBattery"] = 0
    memory["ram"]["lastTimestamp_s"] = 0
    memory["ram"]["lastDeepSleep_s"] = 0
    memory["ram"]["lastLocationType"]  = ''
    memory["ram"]["lastLocationLat"] = 0
    memory["ram"]["lastLocationLon"] = 0
    memory["ram"]["secondsAlarmed"] = 0
    memory["ram"]["smsPointIndex"] = 0
    memory['ram']['lastWifis'] = [] 
    memory["ram"]["blynkPointIndex"] = 0
    memory["ram"]["alarmedTimeZero"] = 0  

################################################### blynk related stuff

blynk = lib.blynklib.Blynk(config['Secrets']['blynkInternet'], server = config['reportTo']['blynkServers']['address_1'], port = config['reportTo']['blynkServers']['port_1'], heartbeat=15, rcv_buffer=1024) # log=print) # 

@blynk.handle_event("connect")
def connect_handler():
    print('[CONNECT_EVENT]')
@blynk.handle_event("disconnect")
def disconnect_handler():
    print('[DISCONNECT_EVENT]')

##### blynk app updates /writes

# ['reportTo']
@blynk.handle_event('write V40')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    print("new Owner phone value:", value[0])
    
    config['reportTo']['owner_phone'] = value[0]
    memory["ram"]["configChanged"] = 1

# AP and APN
@blynk.handle_event('write V41')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['AP']['AP_pass'] = value[0]
    memory["ram"]["configChanged"] = 1
            
@blynk.handle_event('write V42')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['APN']['APN_NAME'] = value[0]
    memory["ram"]["configChanged"] = 1
       
@blynk.handle_event('write V43')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['APN']['APN_USER'] = value[0]
    memory["ram"]["configChanged"] = 1
        
@blynk.handle_event('write V44')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['APN']['APN_PASS'] = value[0]
    memory["ram"]["configChanged"] = 1

# home Wifis
@blynk.handle_event('write V45')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][0]['SSID'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V46')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][0]['pass'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V47')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][1]['SSID'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V48')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][1]['pass'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V49')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][2]['SSID'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V50')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][2]['pass'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V51')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][3]['SSID'] = value[0]
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V52')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['reportTo']['homeWifis'][3]['pass'] = value[0]
    memory["ram"]["configChanged"] = 1

# Informed WIFI atachedconfig    
#53 ssid
#54 ip

#['hardwareSettings']
@blynk.handle_event('write V55')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['hardwareSettings']['vibraSensibility'] = int(value[0])
    memory["ram"]["configChanged"] = 1
        
@blynk.handle_event('write V56')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['hardwareSettings']['touchSensibility'] = int(value[0])
    touch.config(int(config['hardwareSettings']['touchSensibility']))
    memory["ram"]["configChanged"] = 1

    
# Timers sets
@blynk.handle_event('write V62')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['unArmedSelfWakeTimer_m'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V63')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['armedSelfWakeTimer_m'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V64')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['periodLocationPO_s'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V65')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['periodLocationA1_s'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V66')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['alarmedActive1_m'] = int(value[0])
    memory["ram"]["configChanged"] = 1
    
@blynk.handle_event('write V67')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['alarmedSleep1_m'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V68')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['periodLocationA2_s'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V69')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['alarmedActive2_m'] = int(value[0])
    memory["ram"]["configChanged"] = 1

@blynk.handle_event('write V70')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    config['Timers']['alarmedSleep2_m'] = int(value[0])
    memory["ram"]["configChanged"] = 1

# Blynk App Actions buttons

@blynk.handle_event('write V71')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V71 == '1'  -->> togle Led")
        fun.toggle_led(1)
        

@blynk.handle_event('write V72')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V76 == '1'  -->> boot PowerOn /Config (ESP32 reset)")
        lib.machine.reset()
        
@blynk.handle_event('write V73')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V74 == '1'  -->> Update StatusTab")
        fun.updateBlynkStatusESP()

@blynk.handle_event('write V74')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V74 == '1'  -->> Update StatusTab")
        fun.updateBlynkStatusA9G()
        
@blynk.handle_event('write V75')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V75 == '1'  -->> A9G reset")
        fun.A9G_EN(1)

@blynk.handle_event('write V76')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V76 == '1'  -->> ESP32 reset")
        lib.machine.reset()

@blynk.handle_event('write V77')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V77 == '1'  -->> Update Map")
        fun.updateBlynkLoc()

@blynk.handle_event('write V78')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V78 == '1'  -->> Send Location SMS")
        fun.sendLocationMsg(maxReturn_W =3,maxReturn_C=2)
        
@blynk.handle_event('write V79')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if value[0] == '1':
        print("write V79 == '1'  -->> clearing blynk app map")
        fun.mapClear()

blynk.handle_event('write V80')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    # delayed clear on SMS paste input


@blynk.handle_event('write V100')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if eval(value[0]) == 1:
        saveConfig('bikewatch.cfg')
    
@blynk.handle_event('write V101')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))

@blynk.handle_event('write V200')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if eval(value[0]) == 1:
        print('goSleepUnArmed')
        fun.touchActioned(config['Timers']['unArmedSelfWakeTimer_m'])

@blynk.handle_event('write V201')
def write_virtual_pin_handler(pin, value):
    print("V{} AND value: {}".format(pin, value))
    if eval(value[0]) == 1:
        print('goSleepArmed')
        armedSelfWakeTimer_m = config['Timers']['armedSelfWakeTimer_m']
        fun.buttonActioned(armedSelfWakeTimer_m)


# Flags   
@blynk.handle_event('write V210')
def write_virtual_pin_handler(pin, value):
    print("V{} = USE_DATA = value: {}".format(pin, value))
    config['Flags']['USE_DATA']  = eval(value[0])
    memory["ram"]["configChanged"] = 1
    
@blynk.handle_event('write V211')
def write_virtual_pin_handler(pin, value):
    print("V{} = SendMaps = value: {}".format(pin, value))
    config['Flags']['SendMaps']  = eval(value[0])
    memory["ram"]["configChanged"] = 1
        
colors = {'Magenta': '#FF00FF', 'Lime':'#00FF00', 'FireBrick': '#B22222', 'Aqua':'#00FFFF', 'DeepSkyBlue':'#00BFFF', 'White':'#FFFFFF', 'Black':'#000000', 'Navy':'#000080', 'Gray':'#808080'}
            
A_ADDRESS = const(28)               
A_STATUS_MMA8452Q = const(0)       # STATUS_MMA8452Q = const(const(0x00)
A_OUT_X_MSB = const(1)             # OUT_X_MSB = const(0x01)            
A_OUT_X_LSB = const(2)             # OUT_X_LSB = const(0x02)            
A_OUT_Y_MSB = const(3)             # OUT_Y_MSB = const(0x03)            
A_OUT_Y_LSB = const(4)             # OUT_Y_LSB = const(0x04)            
A_OUT_Z_MSB = const(5)             # OUT_Z_MSB = const(0x05)            
A_OUT_Z_LSB = const(6)             # OUT_Z_LSB = const(0x06)            
A_SYSMOD = const(11)               # SYSMOD = const(0x0B)               
A_INT_SOURCE = const(12)           # INT_SOURCE = const(0x0C)           
A_WHO_AM_I = const(13)             # WHO_AM_I = const(0x0D)             
A_XYZ_DATA_CFG = const(14)         # XYZ_DATA_CFG = const(0x0E)         
A_HP_FILTER_CUTOFF = const(15)     # HP_FILTER_CUTOFF = const(0x0F)     
A_PL_STATUS = const(16)            # PL_STATUS = const(0x10)            
A_PL_CFG = const(17)               # PL_CFG = const(0x11)               
A_PL_COUNT = const(18)             # PL_COUNT = const(0x12)             
A_PL_BF_ZCOMP = const(19)          # PL_BF_ZCOMP = const(0x13)          
A_P_L_THS_REG = const(20)          # P_L_THS_REG = const(0x14)          
A_FF_MT_CFG = const(21)            # FF_MT_CFG = const(0x15)            
A_FF_MT_SRC = const(22)            # FF_MT_SRC = const(0x16)            
A_FF_MT_THS = const(23)            # FF_MT_THS = const(0x17)            
A_FF_MT_COUNT = const(24)          # FF_MT_COUNT = const(0x18)          
A_TRANSIENT_CFG = const(29)        # TRANSIENT_CFG = const(0x1D)        
A_TRANSIENT_SRC = const(30)        # TRANSIENT_SRC = const(0x1E)        
A_TRANSIENT_THS = const(31)        # TRANSIENT_THS = const(0x1F)        
A_TRANSIENT_COUNT = const(32)      # TRANSIENT_COUNT = const(0x20)      
A_PULSE_CFG = const(33)            # PULSE_CFG = const(0x21)            
A_PULSE_SRC = const(34)            # PULSE_SRC = const(0x22)            
A_PULSE_THSX = const(35)           # PULSE_THSX = const(0x23)           
A_PULSE_THSY = const(36)           # PULSE_THSY = const(0x24)           
A_PULSE_THSZ = const(37)           # PULSE_THSZ = const(0x25)           
A_PULSE_TMLT = const(38)           # PULSE_TMLT = const(0x26)           
A_PULSE_LTCY = const(39)           # PULSE_LTCY = const(0x27)           
A_PULSE_WIND = const(40)           # PULSE_WIND = const(0x28)           
A_ASLP_COUNT = const(41)           # ASLP_COUNT = const(0x29)           
A_CTRL_REG1 = const(42)            # CTRL_REG1 = const(0x2A)            
A_CTRL_REG2 = const(43)            # CTRL_REG2 = const(0x2B)            
A_CTRL_REG3 = const(44)            # CTRL_REG3 = const(0x2C)            
A_CTRL_REG4 = const(45)            # CTRL_REG4 = const(0x2D)            
A_CTRL_REG5 = const(46)            # CTRL_REG5 = const(0x2E)            
A_OFF_X = const(47)                # OFF_X = const(0x2F)                
A_OFF_Y = const(48)                # OFF_Y = const(0x30)                
A_OFF_Z = const(49)                # OFF_Z = const(0x31)                
