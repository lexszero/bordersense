#!/usr/bin/env python3
import logging, coloredlogs, argparse, re
from typing import Any, List, Dict, Optional

import serial
from pexpect_serial import SerialSpawn

from wb_map12e_common import parse_map12_config

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

def rak7431_configure_polling(slave_addr, blocks, port="/dev/ttyUSB0"):
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
            'AT+MODBUSRETRY=0',
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
        
        for n, b in enumerate(blocks, 1):
            req = b.build_read_request(slave_addr).hex()
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

def dragino_configure_polling(slave_addr, blocks, port="/dev/ttyUSB1"):
    init_commands: List[str] = [
            'AT+BAUDR=9600',
            'AT+PARITY=0',
            'AT+STOPBIT=2',
            'AT+TDC=60000',
            'AT+MBFUN=1',
            ]

    final_commands = [
            'AT+DATAUP=1',
            'ATZ'
            ]

    with serial.Serial(port, baudrate=9600) as port:
        ss = SerialSpawn(port)
        ss.sendline('AT')
        idx = ss.expect(['OK', 'Incorrect Password'])
        if idx == 1:
            ss.sendline('123456')

        for cmd in init_commands:
            send_at_command(ss, cmd)
        
        for n, b in enumerate(blocks, 1):
            req = b.build_read_request(slave_addr)[:-2].hex(' ')
            cmd = f"AT+COMMAND{n:1X}={req},1"
            send_at_command(ss, cmd)
            send_at_command("AT+CMDDL{n:1X}=1000", cmd)

        for cmd in final_commands:
            send_at_command(ss, cmd)

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

def gen_rak7431_map12e_parser(blocks):
    cases = ''
    for n, block in enumerate(blocks, 1):
        measurement = ',\n'.join(block.gen_decoder())
        decoder = re.sub(r'^', ' '*12, measurement, flags=re.MULTILINE).strip()
        cases += f'''
        case {n}:
            return [{decoder}]
'''

    return f'''
{js_common()}

function parse_map12e_pdu(dev_name, task_id, buf, tags) {{
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
    dev_type: "WB-MAP12E"
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
    msg.payload = parse_map12e_pdu(dev_name, task_id, buf.slice(9), tags);
}}

return msg;
'''

def gen_dragino_map12e_parser(blocks):
    offset = 0
    parts = []
    for block in blocks:
        parts.append(',\n'.join(block.gen_decoder(offset=offset)))
        offset += block.size * 2

    measurements = re.sub(r'^', ' '*8, ',\n'.join(parts), flags=re.MULTILINE).strip()

    return f'''
const dev_name = msg.tags.dev_name;
const buf = msg.payload;
const tags = {{
    ...msg.tags,
    dev_type: "WB-MAP12E"
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

def action_gen_parser(blocks, args):
    if args.modem == 'rak7431':
        js = gen_rak7431_map12e_parser(blocks)
    elif args.modem == 'dragino':
        js = gen_dragino_map12e_parser(blocks)
    else:
        raise RuntimeError("Unsupported modem")
    print(js)

def action_configure(blocks, args):
    if args.modem == 'rak7431':
        rak7431_configure_polling(args.address, blocks)
    elif args.modem == 'dragino':
        dragino_configure_polling(args.address, blocks)
    else:
        raise RuntimeError("Unsupported modem")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="config-map12e-fw2.json",
            help="Modbus device JSON config path, (default: %(default)s)")
    parser.add_argument("-m", "--modem", type=str, required=True,
            choices=['rak7431', 'dragino'])
    actions = parser.add_subparsers(title="Action", required=True)

    act_gen_parser = actions.add_parser("gen_parser", help="Generate JS for node-red")
    act_gen_parser.set_defaults(func=action_gen_parser)

    act_conf = actions.add_parser("configure", help="Configure modem polling")
    act_conf.set_defaults(func=action_configure)
    act_conf.add_argument("-p", "--port", type=str, default="/dev/ttyUSB0", help="Serial port (default: %(default)s)")
    act_conf.add_argument("-a", "--address", type=lambda s: int(s, 0), required=True, help="Modbus slave address")

    args = parser.parse_args()

    blocks = parse_map12_config(args.config)
    total_regs = 0
    for n, b in enumerate(blocks):
        log.info(f"block #{n} {b.name}: 0x{b.start:04x} - 0x{b.start+b.size:04x}   ({b.size} regs, {b.size*2} bytes)")
        for chan in b.chans:
            log.info(f"      {chan.get('group', ''):<16} {chan['name']:<32} {chan.get('format', ''):<5}")
        total_regs += b.size

    log.info(f"Total {len(blocks)} blocks, {total_regs} regs")

    args.func(blocks, args)

if __name__ == '__main__':
    main()
