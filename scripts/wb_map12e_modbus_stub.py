#!/usr/bin/env python3
import logging, coloredlogs
import asyncio
import json

from pymodbus.server import StartAsyncSerialServer
from pymodbus.datastore import (
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSparseDataBlock,
)
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.payload import BinaryPayloadBuilder

from wb_map12e_common import is_skipped

log = logging.getLogger()
coloredlogs.install(
        fmt="%(name)s %(levelname)s: %(message)s",
        level=logging.DEBUG
        )

def chan_value(name):
    if 'Irms' in name:
        return 10
    elif 'Ipeak' in name:
        return 15
    elif 'I' in name:
        return 12
    elif 'Frequency' in name:
        return 50.0
    elif name == 'Voltage angle L1':
        return 0
    elif name == 'Voltage angle L2':
        return 120
    elif name == 'Voltage angle L2':
        return -120
    elif 'Total P' in name:
        return 50
    elif 'P L' in name:
        return 16.6
    elif 'Total Q' in name:
        return 51
    elif 'Q L' in name:
        return 17.6
    elif 'Total S' in name:
        return 52
    elif 'S L' in name:
        return 18.6
    elif 'Urms' in name:
        return 230
    elif 'Upeak' in name:
        return 232
    elif 'U L' in name:
        return 400
    else:
        return 0

def build_map12_datablock():
    with open('config-map12e-fw2.json', 'r') as f:
        config = json.load(f)

    regs = {}
    for chan in config['device']['channels']:
        if is_skipped(chan):
            continue
        name = chan['name']
        addr = chan['address']
        if isinstance(addr, str):
            addr = int(addr, 16)
        fmt = chan['format']
        scale = chan.get('scale', 1.0)
        if chan.get('word_order', 'big_endian') == 'little_endian':
            b = BinaryPayloadBuilder(byteorder='>', wordorder='<')
        else:
            b = BinaryPayloadBuilder(byteorder='>', wordorder='>')
        real_val = chan_value(name)
        val = int(real_val/scale)
        if fmt == 's16':
            b.add_16bit_int(val)
        elif fmt == 'u16':
            b.add_16bit_uint(val)
        elif fmt == 's32':
            b.add_32bit_int(val)
        elif fmt == 'u32':
            b.add_32bit_uint(val)
        elif fmt == 's64':
            b.add_64bit_int(val)
        elif fmt == 'u64':
            b.add_64bit_uint(val)
        else:
            raise RuntimeError(f"unsupported fmt in chan {chan['name']}: {fmt}")
        regvals = b.to_registers()
        log.info(f"Reg 0x{addr:04x}={addr} {name} = {real_val} {fmt} [{' '.join(map(hex, regvals))}]")
        regs[addr] = regvals
    return ModbusSparseDataBlock(regs)
 
async def run_async_server():
    """Run server."""
    #datablock = ModbusSequentialDataBlock(0x00, list(range(0, 0xFFFF)))
    # datablock = ModbusSparseDataBlock({0x00: 0, 0x05: 1})
    datablock = build_map12_datablock()
    context = ModbusSlaveContext(
            di=datablock, co=datablock, hr=datablock, ir=datablock,
            zero_mode=True
            )

    context = ModbusServerContext(slaves=context, single=True)

    return await StartAsyncSerialServer(
        context=context,  # Data storage
        framer=ModbusRtuFramer,
        # timeout=1,  # waiting time for request to complete
        port="/dev/ttyUSB0",  # serial port
        # custom_functions=[],  # allow custom handling
        stopbits=2,  # The number of stop bits to use
        bytesize=8,  # The bytesize of the serial messages
        parity="N",  # Which kind of parity to use
        baudrate=9600,  # The baud rate to use for the serial device
        handle_local_echo=True,  # Handle local echo of the USB-to-RS485 adaptor
        #ignore_missing_slaves=False,  # ignore request to a missing slave
        # broadcast_enable=False,  # treat slave_id 0 as broadcast address,
        # strict=True,  # use strict timing, t1.5 for Modbus RTU
        )


if __name__ == "__main__":
    asyncio.run(run_async_server(), debug=True)
