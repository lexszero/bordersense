import os
import logging
import re
from typing import List

import serial
from pexpect_serial import SerialSpawn

import grpc
from chirpstack_api import api

from .modbus_device import ModbusDevice

log = logging.getLogger('transport')

CHIRPSTACK_SERVER = os.environ.get('CHIRPSTACK_SERVER', 'bordersense:8080')
CHIRPSTACK_API_TOKEN = os.environ.get('CHIRPSTACK_API_TOKEN')

channel = grpc.insecure_channel(CHIRPSTACK_SERVER)
auth_token = [("authorization", "Bearer %s" % CHIRPSTACK_API_TOKEN)]

chirpstack_dev_service = api.DeviceServiceStub(channel)

def send_lora_cmd(dev_eui, fport, buf):
    req = api.EnqueueDeviceQueueItemRequest()
    req.queue_item.confirmed = True
    req.queue_item.data = bytes(buf)
    req.queue_item.dev_eui = dev_eui
    req.queue_item.f_port = fport
    return chirpstack_dev_service.Enqueue(req, metadata=auth_token)

class ATCommandError(Exception):
    def __init__(self, code, msg, *args, **kwargs):
        self.code = code
        self.msg = msg
        super().__init__(f'AT command error: {code}:{msg}', *args, **kwargs)

def send_at_command(ss, cmd):
    log.info(f'Sending {cmd}')
    ss.sendline(cmd)
    idx = ss.expect(['OK', r'ERROR:(\d+):(\w+)'], timeout=5)
    if idx == 0:
        return
    elif idx == 1:
        code, msg = ss.match.groups()
        raise ATCommandError(int(code), msg.decode())

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


class Transport:
    @staticmethod
    def configure_local(requests, port="/dev/ttyUSB0"):
        pass

    @staticmethod
    def configure_lora(requests, dev_eui, serial=0):
        pass

    @staticmethod
    def gen_slave_response_parser(slaves):
        pass

class TransportRAK7431(Transport):
    MAX_COMMANDS = 32
    MAX_RESPONSE_BYTES = 40

    @staticmethod
    def configure_local(requests, port="/dev/ttyUSB0"):
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

        with serial.Serial(port, baudrate=115200) as port:
            ss = SerialSpawn(port)
            ss.sendline('AT+ECHO=0')
            ss.expect('OK')
            ss.sendline('AT+POLLTASK')
            num_polltasks = -1
            while True:
                idx = ss.expect(['OK', r'(\d+):([0-9A-F]+)'])
                if idx == 0:
                    break
                else:
                    num_polltasks = int(ss.match.groups()[0])

            log.info(f"Currently {num_polltasks} poll tasks")
            for n in range(1, num_polltasks+1):
                try:
                    send_at_command(ss, f'AT+RMPOLL={n}')
                except ATCommandError as e:
                    if e.msg == 'DUPLICATE':
                        continue

            for cmd in init_commands:
                send_at_command(ss, cmd)

            for n, req in enumerate(requests, 1):
                req = req.hex()
                cmd = f"AT+ADDPOLL={n}:{req}"
                try:
                    send_at_command(ss, cmd)
                except ATCommandError as e:
                    if e.msg == 'DUPLICATE':
                        log.info(f"Poll task #{n} already exists, removing it first")
                        send_at_command(ss, f'AT+RMPOLL={n}')
                        send_at_command(ss, cmd)

            for cmd in final_commands:
                send_at_command(ss, cmd)

    @staticmethod
    def configure_lora(requests, dev_eui, serial=0):
        n = 1
        for req in requests:
            mser = 2*serial+n
#            cmd = bytes([0x04, 0, mser, 0, 1, n])
#            log.info(f"Deleting #{n:>2}: {cmd.hex(' ')}")
#            send_lora_cmd(dev_eui, 129, cmd)

            cmd = bytes([0x03, 0, mser+1, 0, len(req)+1, n, *req])
            log.info(f"Adding #{n:>2}: {cmd.hex(' ')}")
            send_lora_cmd(dev_eui, 129, cmd)
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

class TransportDragino(Transport):
    MAX_COMMANDS = 16
    MAX_RESPONSE_BYTES = None

    @staticmethod
    def configure_local(requests, port="/dev/ttyUSB1"):
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

        with serial.Serial(port, baudrate=9600) as port:
            ss = SerialSpawn(port)
            ss.sendline('AT')
            idx = ss.expect(['OK', 'Incorrect Password'])
            if idx == 1:
                ss.sendline('123456')

            for cmd in init_commands:
                send_at_command(ss, cmd)

            n = 1
            for req in requests:
                req = req[:-2].hex(' ')
                cmd = f"AT+COMMAND{n:1X}={req},1"
                send_at_command(ss, cmd)
                send_at_command(ss, f"AT+CMDDL{n:1X}=1000")
                n += 1

            for cmd in final_commands:
                send_at_command(ss, cmd)
            ss.sendline('ATZ')

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
