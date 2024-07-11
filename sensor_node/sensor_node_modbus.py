import logging
import asyncio
import re
from pydantic import BaseModel, conint
from typing import List, Literal, Optional

from pymodbus.server import StartAsyncSerialServer
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.datastore import ModbusServerContext

from .sensor_node import SensorNode
from .modbus_device import ModbusDevice
from .utils import ATCommandError, SerialDevice, LoRaDevice

log = logging.getLogger('sensor_node_modbus')

class ModbusSlaveConfig(BaseModel):
    address: int = conint(ge=0, le=255)
    device_conf: str

class SensorNodeModbusConfig(BaseModel):
    poll_period: int
    modbus_slaves: List[ModbusSlaveConfig]

class SensorNodeModbus(SensorNode):
    config: SensorNodeModbusConfig
    modbus_slaves: List[ModbusDevice]

    def __init__(self, config: SensorNodeModbusConfig, max_response_bytes: Optional[int] = None):
        self.config = config
        self.modbus_slaves: List[ModbusDevice] = []

        total_regs = 0
        all_blocks = []
        for slave_conf in self.config.modbus_slaves:
            max_resp_regs = None
            if max_response_bytes:
                max_resp_regs = max_response_bytes/2
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
        js = self.gen_slave_response_parser(self.modbus_slaves)
        print(js)

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

def js_common():
    return '''
function convert(signed, scale, errorVals, limit, val) {{
    if (errorVals.includes(val))
        return undefined;
    if (limit && val > limit)
        return undefined;
    if (signed)
        val = val<<0;
    return val*scale;
}}
'''

class SensorNodeRAK7431(SensorNodeModbus):
    MAX_COMMANDS = 32
    MAX_RESPONSE_BYTES = 40

    def __init__(self, config: SensorNodeModbusConfig):
        super().__init__(config, self.MAX_RESPONSE_BYTES)

    def configure_local(self, args):
        requests = []
        for slave in self.modbus_slaves:
            requests += slave.read_requests()

        init_commands: List[str] = [
                'AT+CLASS=C',
                'AT+PUBLIC=1',
                'AT+CONFIRM=0',
                'AT+BAUDRATE=9600',
                'AT+DATABIT=8',
                'AT+STOPBIT=2',
                'AT+PARITY=NONE',
                'AT+DTUMODE=MODBUS',
                'AT+TRANSPARENT=0',
                'AT+POLLPERIOD=30',
                'AT+ENABLEPOLL=0'
                ]

        final_commands = [
                'AT+ENABLEPOLL=1',
                'AT+RESTART'
                ]

        with SerialDevice(args.port, baudrate=115200) as port:
            port.sendline('AT+ECHO=0')
            port.expect('OK')
            port.sendline('AT+POLLTASK')
            num_polltasks = -1
            while True:
                idx, match = port.expect(['OK', r'(\d+):([0-9A-F]+)'])
                if idx == 0:
                    break
                else:
                    num_polltasks = int(match.groups()[0])

            log.info(f"Currently {num_polltasks} poll tasks")
            for n in range(1, num_polltasks+1):
                try:
                    port.send_at_command(f'AT+RMPOLL={n}')
                except ATCommandError as e:
                    if e.msg == 'DUPLICATE':
                        continue

            for cmd in init_commands:
                port.send_at_command(cmd)

            for n, req in enumerate(requests, 1):
                req = req.hex()
                cmd = f"AT+ADDPOLL={n}:{req}"
                try:
                    port.send_at_command(cmd)
                except ATCommandError as e:
                    if e.msg == 'DUPLICATE':
                        log.info(f"Poll task #{n} already exists, removing it first")
                        port.send_at_command(f'AT+RMPOLL={n}')
                        port.send_at_command(cmd)

            for cmd in final_commands:
                port.send_at_command(cmd)

    def configure_lora(self, args):
        requests = []
        for slave in self.modbus_slaves:
            requests += slave.read_requests()
        n = 1
        dev = LoRaDevice(args.dev_eui)
        for req in requests:
            mser = 2*args.serial+n
#            cmd = bytes([0x04, 0, mser, 0, 1, n])
#            log.info(f"Deleting #{n:>2}: {cmd.hex(' ')}")
#            dev.send(129, cmd)

            cmd = bytes([0x03, 0, mser+1, 0, len(req)+1, n, *req])
            log.info(f"Adding #{n:>2}: {cmd.hex(' ')}")
            dev.send(129, cmd)
            n += 1

    @staticmethod
    def gen_slave_response_parser(slaves):
        cases = ''
        n = 0
        for slave in slaves:
            for block in slave.all_blocks:
                n += 1
                if len(slaves) > 1:
                    meas_name = f"'_{slave.address}'"
                else:
                    meas_name = "''"
                measurement = ',\n'.join(block.gen_decoder(meas_name))
                decoder = re.sub(r'^', ' '*12, measurement, flags=re.MULTILINE).strip()
                cases += f'''
        case {n}:
            return [{decoder}]
'''

        return f'''
{js_common()}

function parse_modbus_pdu(dev_name, task_id, buf, tags) {{
    switch (task_id) {{
{cases}
    }}
}}

const dev_name = msg.payload.deviceInfo.deviceName;
const buf = new Buffer(msg.payload.data, 'base64');

const msg_type = buf[0] & 0x0F;
const fail = buf[0] & 0x40;

if (msg_type != 0x01)
    return;

const task_id = buf[5];
const tags = {{
    ...msg.payload.deviceInfo.tags,
    dev_name: dev_name
}};

if (fail) {{
    msg.payload = [{{
        measurement: dev_name + "_error",
        fields: {{
            task_id: task_id,
            code: buf[6]
        }},
        tags: tags
    }}]
}}
else {{
    msg.payload = parse_modbus_pdu(dev_name, task_id, buf.slice(9), tags);
}}

return msg;
'''

class SensorNodeDraginoRS485(SensorNodeModbus):
    MAX_COMMANDS = 16

    def __init__(self, config: SensorNodeModbusConfig):
        super().__init__(config, None)

    def configure_local(self, args):
        requests = []
        for slave in self.modbus_slaves:
            requests += slave.read_requests()

        init_commands: List[str] = [
                'AT+RPL=4',
                'AT+BAUDR=9600',
                'AT+PARITY=0',
                'AT+STOPBIT=2',
                'AT+TDC=60000',
                'AT+MBFUN=1',
                ]

        final_commands = [
                'AT+DATAUP=1',
                ]

        with SerialDevice(args.port, baudrate=9600) as port:
            port.sendline('AT')
            idx, match = port.expect(['OK', 'Incorrect Password'])
            if idx == 1:
                port.sendline('123456')

            for cmd in init_commands:
                port.send_at_command(cmd)

            n = 1
            for req in requests:
                req = req[:-2].hex(' ')
                cmd = f"AT+COMMAND{n:1X}={req},1"
                port.send_at_command(cmd)
                port.send_at_command(f"AT+CMDDL{n:1X}=1000")
                n += 1

            for cmd in final_commands:
                port.send_at_command(cmd)
            port.sendline('ATZ')

    def configure_lora(self, args):
        requests = []
        for slave in self.modbus_slaves:
            requests += slave.read_requests()

        n = 1
        dev = LoRaDevice(args.dev_eui)
        for req in requests:
#            cmd = bytes([0x04, 0, mser, 0, 1, n])
#            log.info(f"Deleting #{n:>2}: {cmd.hex(' ')}")
#            dev.send(129, cmd)
            req = req[:-2]
            cmd = bytes([0xAF, n, 0x01, len(req), *req, 0x01])
            log.info(f"Command #{n:>2}: {cmd.hex(' ')}")
            dev.send(1, cmd)
            cmd = bytes([0xAF, n, 0x02, 3, 0x00, 0x00, 0x00, 0x01])
            log.info(f"Datacut #{n:>2}: {cmd.hex(' ')}")
            dev.send(1, cmd)
            n += 1


    @staticmethod
    def gen_slave_response_parser(slaves):
        offset = 0
        parts = []
        for slave in slaves:
            if len(slaves) > 1:
                meas_name = f"'_{slave.address}'"
            else:
                meas_name = "''"
            for block in slave.all_blocks:
                parts.append(',\n'.join(block.gen_decoder(meas_name, offset=offset)))
                offset += block.size * 2
    
        measurements = re.sub(r'^', ' '*8, ',\n'.join(parts), flags=re.MULTILINE).strip()
    
        return f'''
const dev_name = msg.tags.dev_name;
const buf = msg.payload;
const tags = {{
    ...msg.tags
}};

{js_common()}

if (buf.every((x) => ((x == 0xff) || (x == 0x00)))) {{
    msg.payload = [{{
        measurement: dev_name + "_error",
        fields: {{
            code: 0xff
        }},
        tags: tags
    }}]
}}
else {{
    const data = [
        {measurements}
    ];
    msg.payload = data.filter((item) => !Object.values(item.fields).every((x) => x == undefined));
}}

return msg;

'''

SensorNode.register("rak7431", SensorNodeRAK7431, SensorNodeModbusConfig)
SensorNode.register("dragino-rs485", SensorNodeDraginoRS485, SensorNodeModbusConfig)
