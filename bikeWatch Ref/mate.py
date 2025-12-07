import network, time

sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)
sta_if.connect('Mate-2.4GHz','29655468')

print('[waiting for an IP ]',end='')
while sta_if.ifconfig()[0] == '0.0.0.0':
    time.sleep(1)
    print('.',end='')

import webrepl
webrepl.start()

import ftp_thread
ftp = ftp_thread.FtpTiny()
ftp.start()


print('Mate WIFI connected / ftp at:', sta_if.ifconfig()[0]  )