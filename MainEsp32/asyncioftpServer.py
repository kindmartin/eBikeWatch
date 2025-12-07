# ftp_async.py
import uasyncio as asyncio
import uos

async def handle_data_conn(reader, writer, fp, mode):
    if mode == "RETR":
        while True:
            chunk = fp.read(1024)
            if not chunk:
                break
            await writer.awrite(chunk)
    else:  # STOR
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                break
            fp.write(chunk)
    await writer.aclose()
    fp.close()

async def handle_ftp_client(reader, writer):
    cwd = "/"
    await writer.awrite("220 ESP32 async FTP\r\n")

    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.decode().strip()
        if not line:
            continue
        cmd, *rest = line.split(" ", 1)
        arg = rest[0] if rest else ""
        cmd = cmd.upper()

        if cmd == "USER":
            await writer.awrite("230 Logged in.\r\n")
        elif cmd == "PWD":
            await writer.awrite('257 "{}"\r\n'.format(cwd))
        elif cmd == "QUIT":
            await writer.awrite("221 Bye.\r\n")
            break
        elif cmd == "PASV":
            # Abrir server de datos en puerto fijo
            data_port = 13333
            ip = "192,168,1,10"   # poner tu IP real
            p1, p2 = divmod(data_port, 256)
            await writer.awrite(
                "227 Entering Passive Mode ({},{},{}).\r\n"
                .format(ip, p1, p2)
            )

            # Crear server de datos UNA sola vez para esta transferencia:
            fut = asyncio.get_event_loop().create_future()

            async def data_srv(reader_d, writer_d):
                fut.set_result((reader_d, writer_d))

            srv = await asyncio.start_server(data_srv, "0.0.0.0", data_port)
            # guardar srv si querés cerrarlo luego
        elif cmd == "RETR":
            path = arg if arg.startswith("/") else "{}/{}".format(cwd, arg)
            fp = open(path, "rb")
            await writer.awrite("150 Opening data.\r\n")
            reader_d, writer_d = await fut
            await handle_data_conn(reader_d, writer_d, fp, "RETR")
            await writer.awrite("226 Done.\r\n")
        # ... etc para STOR / LIST / CWD ...
        else:
            await writer.awrite("502 Unsupported\r\n")

    await writer.aclose()


async def ftp_async_server():
    srv = await asyncio.start_server(handle_ftp_client, "0.0.0.0", 21)
    # opcional: guardar srv en variable global para cerrar luego
    await srv.wait_closed()


# Para correr el servidor FTP asíncrono:
"""
import uasyncio as asyncio
from ftp_async import ftp_async_server

async def main():
    # otras tareas: UI, PR, etc.
    asyncio.create_task(ftp_async_server())
    # ... más create_task(...)
    while True:
        await asyncio.sleep(1)
        
"""