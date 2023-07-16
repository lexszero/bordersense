import logging, json, re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, List, Dict, Optional
from pymodbus.register_read_message import ReadInputRegistersRequest
from pymodbus.factory import ClientDecoder as ModbusClientDecoder
from pymodbus.transaction import ModbusRtuFramer

log = logging.getLogger('wb-map12e')
mb_framer = ModbusRtuFramer(ModbusClientDecoder())

block_desc = [
        {
            'frequency': [0],
        },
        'U_phase_angle',
        'ch1_power',
        {
            'ch1_Irms': [3,4,5],
            'U': [0, 1, 2, 6, 7, 8]
        },
        'U_peak',
        'ch1_Ipeak',
        'ch2_power',
        'ch2_Irms',
        'ch2_Ipeak',
        'ch3_power',
        'ch3_Irms',
        'ch3_Ipeak',
        'ch4_power',
        'ch4_Irms',
        'ch4_Ipeak'
        ]


def is_skipped(chan):
    if chan['group'] == 'hw_info':
        return True
    return any([word in chan['name'] for word in ['energy', 'PF', 'Phase angle']])

def get_channel_size(chan) -> int:
    fmt = chan.get('format', 'u16')
    fmt_len = {
            's16': 1,
            'u16': 1,
            's32': 2,
            'u32': 2,
            's64': 4,
            'u64': 4
            }

    if fmt == 'string':
        return chan['string_data_size']
    else:
        return fmt_len[fmt]

def sanitize_chan_name(name):
    s = re.sub(r'^Ch \d+\s+', '', name)
    s = re.sub(r'^(.*) (Total|L[1-3])$', r'\2 \1', s)
    s = re.sub(r'\s', '_', s)
    s = re.sub(r'-', '_', s)
    return s

def gen_chan_decoder(chan, start_address, buf='buf', offset=0):
    fmt = chan['format']
    word_order = chan.get('word_order', 'big_endian')
    offset = offset + (int(chan['address'], 16) - start_address) * 2
    ret = ''
    if fmt in ['s16', 'u16']:
        errvals = [0xffff]
        ret = f'({buf}[{offset}] << 8) | {buf}[{offset+1}]'
    elif fmt in ['s32', 'u32']:
        errvals = [0xffffffff]
        if word_order == 'little_endian':
            ret = f'({buf}[{offset}] << 8) | ({buf}[{offset+1}]) | ({buf}[{offset+2}] << 24) | ({buf}[{offset+3}] << 16)'
        else:
            ret = f'({buf}[{offset+2}] << 8) | ({buf}[{offset+3}]) | ({buf}[{offset}] << 24) | ({buf}[{offset+1}] << 16)'
    else:
        raise RuntimeError(f"Unsupported format: {fmt}")

    signed='false'
    if fmt[0] == 's':
        signed='true'
    scale = chan.get('scale', 1.0)
    if 'error_value' in chan:
        ev = int(chan['error_value'], 16)
        if ev not in errvals:
            errvals.append(ev)
    ret = f"convert({signed}, {scale}, [{', '.join(map(hex, errvals))}], {ret})"
    return ret

def format_dict(data, indent=8):
    return f",\n{' '*indent}".join([f'{k}: {v}' for k, v in data.items()])

@dataclass
class RegisterBlock:
    name: str
    start: int
    size: int
    chans: List[Dict[str, Any]]
    desc: Optional[Dict[str, List[int]]]
    def __init__(self, desc, start, size):
        if isinstance(desc, str):
            self.name = desc
            self.desc = None
        elif isinstance(desc, dict):
            self.name = ','.join(desc.keys())
            self.desc = desc
        self.start = start
        self.size = size
        self.chans = []

    def build_read_request(self, slave_addr: int) -> str:
        req = ReadInputRegistersRequest(self.start, self.size, slave_addr)
        return mb_framer.buildPacket(req)

    def gen_decoder_measurement(self, measurement, chan_list, tags={}, offset=0):
        linesep = f",\n        "
        tags = {}
        m = re.match(r'ch(\d+)_(\w+)', measurement)
        if m:
            tags['meas_channel'] = int(m.group(1))
            tags['meas_type'] = repr(m.group(2))
        else:
            tags['meas_type'] = repr(measurement)
        lines = []
        for chan_idx in chan_list:
            chan = self.chans[chan_idx]
            lines.append(f"{sanitize_chan_name(chan['name'])}: {gen_chan_decoder(chan, self.start, offset=offset)}")
        fields = linesep.join(lines)
        return f'''{{
    measurement: dev_name + "_{measurement}",
    fields: {{
        {fields}
    }},
    tags: {{
        ...tags,
        {format_dict(tags, indent=8)},
    }}
}}'''

    def gen_decoder(self, *args, **kwargs):
        if self.desc:
            return [self.gen_decoder_measurement(measurement, chan_list, *args, **kwargs) for measurement, chan_list in self.desc.items()]
        else:
            return [self.gen_decoder_measurement(self.name, range(len(self.chans)), *args, **kwargs)]


def parse_map12_config(json_path='config-map12e-fw2.json'):
    config = None
    with open(json_path, 'r') as f:
        config = json.load(f)

    def empty_list() -> list[Any]:
        return []

    groups: defaultdict[str, List[Any]] = defaultdict(empty_list)
    inputs: Dict[int, Dict[str, Any]] = {}
    for chan in config['device']['channels']:
        addr = chan['address']
        if is_skipped(chan):
            continue
        if isinstance(addr, str):
            addr = int(addr, 16)
        grp = groups[chan['group']]
        if chan['reg_type'] == 'input':
            inputs[addr] = chan
            grp.append(chan)

    next_addr = -1
    blocks: List[RegisterBlock] = []
    sorted_inputs = sorted(inputs.items())
    block = RegisterBlock(block_desc[0], sorted_inputs[0][0], 0)
    block_idx = 0
    for addr, chan in sorted(inputs.items()):
        if next_addr >= 0 and addr != next_addr:
            blocks.append(block)
            block_idx += 1
            block = RegisterBlock(block_desc[block_idx], addr, 0)

        if addr == next_addr:
            s_addr = '------'
        else:
            s_addr = f'0x{addr:04x}'

        size = get_channel_size(chan)
        block.chans.append(chan)
        block.size += size
        next_addr = addr + size
        log.debug(f"{s_addr}: {chan.get('group', ''):<16} {chan['name']:<32} {chan.get('format', ''):<5}")
    if block:
        blocks.append(block)

    return blocks


