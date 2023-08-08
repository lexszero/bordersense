#!/usr/bin/env python3
import enum
import logging, coloredlogs, argparse, re
from typing import Any, List, Dict, Optional

import serial
from pexpect_serial import SerialSpawn

from modbus_device import ModbusDevice, sanitize_chan_name

log = logging.getLogger('genconf')
coloredlogs.install(
        fmt="%(name)s %(levelname)s: %(message)s",
        level=logging.INFO
        )

class ATCommandError(Exception):
    def __init__(self, code, msg, *args, **kwargs):
        self.code = code
        self.msg = msg
        super().__init__(f'RAK7431 AT command error: {code}:{msg}', *args, **kwargs)

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
function convert(signed, scale, errorVals, val) {{
    if (errorVals.includes(val))
        return undefined;
    if (signed)
        val = val<<0;
    return val*scale;
}}
'''

class Transport:
    @staticmethod
    def configure_polling(slave_addr, dev, port="/dev/ttyUSB0"):
        pass

    @staticmethod
    def gen_modbus_parser(dev):
        pass

class TransportRAK7431(Transport):
    MAX_COMMANDS = 32
    MAX_RESPONSE_BYTES = 42

    @staticmethod
    def configure_polling(slave_addr, dev, port="/dev/ttyUSB0"):
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
                'AT+POLLPERIOD=120',
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

            for n, req in enumerate(dev.read_requests(slave_addr), 1):
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
    def gen_modbus_parser(dev):
        cases = ''
        for n, block in enumerate(dev.all_blocks, 1):
            measurement = ',\n'.join(block.gen_decoder())
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
    dev_name: dev_name,
    dev_type: "{dev.config['device_type']}"
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
    def configure_polling(slave_addr, dev, port="/dev/ttyUSB1"):
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

            for n, req in enumerate(dev.read_requests(slave_addr), 1):
                req = req[:-2].hex(' ')
                cmd = f"AT+COMMAND{n:1X}={req},1"
                send_at_command(ss, cmd)
                send_at_command(ss, f"AT+CMDDL{n:1X}=1000")

            for cmd in final_commands:
                send_at_command(ss, cmd)
            ss.sendline('ATZ')

    @staticmethod
    def gen_modbus_parser(dev):
        offset = 0
        parts = []
        for block in dev.all_blocks:
            parts.append(',\n'.join(block.gen_decoder(offset=offset)))
            offset += block.size * 2
    
        measurements = re.sub(r'^', ' '*8, ',\n'.join(parts), flags=re.MULTILINE).strip()
    
        return f'''
const dev_name = msg.tags.dev_name;
const buf = msg.payload;
const tags = {{
    ...msg.tags,
    dev_type: "{dev.config['device_type']}"
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

def action_gen_parser(device, transport, args):
    js = transport.gen_modbus_parser(device)
    print(js)

def action_configure(device, transport, args):
    transport.configure_polling(args.address, device, args.port)

def action_print_requests(device, transport, args):
    n = 1
    for req in device.read_requests(args.address):
        log.info(f"Request #{n:>2}: {req.hex(' ')}")
        cmd_del = bytes([0x04, 0, 2+n*2, 0, 1, n])
        cmd_add = bytes([0x03, 0, 2+n*2+1, 0, len(req)+1, n, *req])
        n += 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="config-map12e-fw2.json",
            help="Modbus device JSON config path, (default: %(default)s)")
    parser.add_argument("-t", "--transport", type=str, required=True,
            choices=['rak7431', 'dragino'],
            help="LoRa transport type"
            )
    actions = parser.add_subparsers(title="Action", required=True)

    act_gen_parser = actions.add_parser("gen_parser", help="Generate JS for node-red")
    act_gen_parser.set_defaults(func=action_gen_parser)

    act_conf = actions.add_parser("configure", help="Configure transport polling")
    act_conf.set_defaults(func=action_configure)
    act_conf.add_argument("-p", "--port", type=str, default="/dev/ttyUSB0", help="Serial port (default: %(default)s)")
    act_conf.add_argument("-a", "--address", type=lambda s: int(s, 0), required=True, help="Modbus slave address", default=0)

    act_print_requests = actions.add_parser("print_requests", help="Print read requests")
    act_print_requests.add_argument("-a", "--address", type=lambda s: int(s, 0), required=True, help="Modbus slave address", default=0)
    act_print_requests.set_defaults(func=action_print_requests)

    args = parser.parse_args()

    if args.transport == 'rak7431':
        transport = TransportRAK7431
    elif args.transport == 'dragino':
        transport = TransportDragino
    else:
        raise RuntimeError("Unsupported transport")

    dev = ModbusDevice(args.config, max_response_regs=20)

    total_regs = 0
    all_blocks = dev.all_blocks
    for n, b in enumerate(all_blocks):
        log.info(f"block #{n} {b.name}: 0x{b.start:04x} - 0x{b.start+b.size:04x}   ({b.size} regs, {b.size*2} bytes)")
        for cn, chan in enumerate(b.chans):
            log.info(f"   chan #{cn:>4}   {chan['address']}: {chan['name']:<32} {chan.get('format', ''):<5}")
        total_regs += b.size

    log.info(f"Total {len(all_blocks)} blocks, {total_regs} regs")

    args.func(dev, transport, args)

if __name__ == '__main__':
    main()
