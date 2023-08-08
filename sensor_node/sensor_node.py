import logging
import asyncio
from pydantic import BaseModel, conint
from typing import List, Literal

from pymodbus.server import StartAsyncSerialServer
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.datastore import ModbusServerContext

from .transport import Transport, TransportRAK7431, TransportDragino
from .modbus_device import ModbusDevice

log = logging.getLogger('sensor_node')

class ModbusSlaveConfig(BaseModel):
    address: int = conint(ge=0, le=255)
    device_conf: str

class SensorNodeConfig(BaseModel):
    transport: Literal['rak7431', 'dragino']
    poll_period: int
    modbus_slaves: List[ModbusSlaveConfig]

transport_classes = {
        'rak7431': TransportRAK7431,
        'dragino': TransportDragino
        }

class SensorNode:
    config: SensorNodeConfig
    transport: Transport
    modbus_slaves: List[ModbusDevice]

    def __init__(self, conf_file: str):
        log.info(f"Loading sensor node configuration {conf_file}")
        with open(conf_file, 'r') as f:
            self.config = SensorNodeConfig.model_validate_json(f.read())

        self.transport = transport_classes[self.config.transport]
        self.modbus_slaves: List[ModbusDevice] = []

        total_regs = 0
        all_blocks = []
        for slave_conf in self.config.modbus_slaves:
            max_resp_regs = None
            if self.transport.MAX_RESPONSE_BYTES:
                max_resp_regs = self.transport.MAX_RESPONSE_BYTES/2
            slave = ModbusDevice(slave_conf.address, 'devices/'+slave_conf.device_conf, max_response_regs=max_resp_regs)
            all_blocks += slave.all_blocks
            for n, b in enumerate(slave.all_blocks):
                log.info(f"block #{n} {b.name}: 0x{b.start:04x} - 0x{b.start+b.size:04x}   ({b.size} regs, {b.size*2} bytes)")
                for cn, chan in enumerate(b.chans):
                    log.info(f"   chan #{cn:>4}   {chan['address']}: {chan['name']:<32} {chan.get('format', ''):<5}")
                total_regs += b.size

            self.modbus_slaves.append(slave)
        log.info(f"Total {len(all_blocks)} reads, {total_regs} regs")

    def print_reads(self, args):
        for slave in self.modbus_slaves:
            for req in slave.read_requests():
                log.info(f'Read request: {req}')

    def gen_parser(self, args):
        js = self.transport.gen_slave_response_parser(self.modbus_slaves)
        print(js)

    def configure_transport_local(self, args):
        requests = []
        for slave in self.modbus_slaves:
            requests += slave.read_requests()
        self.transport.configure_polling(requests, args.port)

    def configure_transport_lora(self, args):
        requests = []
        for slave in self.modbus_slaves:
            requests += slave.read_requests()
        self.transport.configure_remote(requests, args.dev_eui, args.serial)

    def emulate_modbus(self, args):
        slaves = {}
        for slave in self.modbus_slaves:
            slaves[slave.address] = slave.emulated_slave_context()
        context = ModbusServerContext(slaves=slaves)

        asyncio.run(StartAsyncSerialServer(
            context=context,  # Data storage
            framer=ModbusRtuFramer,
            # timeout=1,  # waiting time for request to complete
            port=args.port,  # serial port
            # custom_functions=[],  # allow custom handling
            stopbits=2,  # The number of stop bits to use
            bytesize=8,  # The bytesize of the serial messages
            parity="N",  # Which kind of parity to use
            baudrate=9600,  # The baud rate to use for the serial device
            handle_local_echo=True,  # Handle local echo of the USB-to-RS485 adaptor
            #ignore_missing_slaves=False,  # ignore request to a missing slave
            # broadcast_enable=False,  # treat slave_id 0 as broadcast address,
            # strict=True,  # use strict timing, t1.5 for Modbus RTU
            ))


