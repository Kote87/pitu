#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hr_ble_to_serial.py
Lee la característica BLE de Frecuencia Cardíaca (UUID 0x2A37) y reenvía HR por Serial
como "HR,<valor>\n". Requiere activar 'Transmitir FC' en el Fenix 7 y emparejar.

Nota: es un *starter*. Adaptar dirección MAC/NOMBRE de tu reloj y permisos BLE.
"""
import asyncio
import serial
from bleak import BleakClient, BleakScanner

# Ajusta estos valores
TARGET_NAME_CONTAINS = "Fenix"
SERIAL_PORT = "/dev/ttyACM0"
BAUDRATE = 9600

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHAR    = "00002a37-0000-1000-8000-00805f9b34fb"

def parse_hr(data: bytearray) -> int:
    # Formato estándar Heart Rate Measurement (primer byte = flags)
    if not data: return 0
    flags = data[0]
    hr_16bit = bool(flags & 0x01)
    if hr_16bit and len(data) >= 3:
        return int(data[1] | (data[2] << 8))
    elif len(data) >= 2:
        return int(data[1])
    return 0

async def main():
    print("[BLE] Escaneando dispositivos...")
    devices = await BleakScanner.discover(timeout=5.0)
    target = None
    for d in devices:
        if d.name and TARGET_NAME_CONTAINS.lower() in d.name.lower():
            target = d
            break
    if not target:
        print("[BLE] No se encontró el Fenix (ajusta TARGET_NAME_CONTAINS o usa MAC).")
        return

    print(f"[BLE] Conectando a {target.name} ({target.address}) ...")
    async with BleakClient(target) as client:
        ok = await client.is_connected()
        if not ok:
            print("[BLE] No se pudo conectar.")
            return

        ser = serial.Serial(SERIAL_PORT, baudrate=BAUDRATE, timeout=1)
        await client.start_notify(HR_CHAR, lambda c, data: ser.write(f"HR,{parse_hr(data)}\n".encode("utf-8")))
        print("[BLE] Suscrito a HR. Ctrl+C para salir.")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            await client.stop_notify(HR_CHAR)
            ser.close()

if __name__ == "__main__":
    asyncio.run(main())