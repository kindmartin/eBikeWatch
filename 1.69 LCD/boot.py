import network as network, machine

try:
	import startup_cleanup
	startup_cleanup.run()
except ImportError:
	pass

#import bleREPL 


if hasattr(network, 'hostname'):
	uid_suffix = '0000'
	if machine is not None and hasattr(machine, 'unique_id'):
		try:
			uid = machine.unique_id()
			if isinstance(uid, (bytes, bytearray)) and len(uid) >= 2:
				uid_suffix = '{:02X}{:02X}'.format(uid[-2], uid[-1])
		except Exception:
			uid_suffix = '0000'
	network.hostname('ESP-{}'.format(uid_suffix))