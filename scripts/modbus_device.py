import logging, json, re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, List, Dict, Optional
from pymodbus.register_read_message import ReadInputRegistersRequest, ReadHoldingRegistersRequest
from pymodbus.factory import ClientDecoder as ModbusClientDecoder
from pymodbus.transaction import ModbusRtuFramer
from devtools import debug

log = logging.getLogger('mbdev')
mb_framer = ModbusRtuFramer(ModbusClientDecoder())

def is_skipped(chan):
    if 'name' not in chan:
        return True
    if chan.get('group') == 'hw_info':
        return True
    return any([re.match(regex, chan['name']) for regex in [
        r'Ch.*PF',
        r'Ch.*energy',
        r'Ch.*Voltage angle',
        r'.*[Pp]hase angle',
        r'.*THD',
        r'.*demand',
        r'.*average',
        r'.*I sum',
        r'Ah,'
        ]])

def get_channel_size(chan) -> int:
    fmt = chan.get('format', 'u16')
    fmt_len = {
            's16': 1,
            'u16': 1,
            's32': 2,
            'u32': 2,
            's64': 4,
            'u64': 4,
            'float': 2
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
    errvals = []
    if fmt in ['s16', 'u16']:
        errvals = [0xffff]
        ret = f'({buf}[{offset}] << 8) | {buf}[{offset+1}]'
    elif fmt in ['s32', 'u32']:
        errvals = [0xffffffff]
        if word_order == 'little_endian':
            ret = f'({buf}[{offset+2}] << 24) | ({buf}[{offset+3}] << 16) | ({buf}[{offset+0}] << 8) | ({buf}[{offset+1}] << 0)'
        else:
            ret = f'({buf}[{offset+0}] << 24) | ({buf}[{offset+1}] << 16) | ({buf}[{offset+2}] << 8) | ({buf}[{offset+3}] << 0)'
    elif fmt == 'float':
        ret = f'({buf}.readFloat({buf}[{offset}])'
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

    def __init__(self, desc, method, start, size):
        if isinstance(desc, str):
            self.name = desc
            self.desc = None
        elif isinstance(desc, dict):
            self.name = ','.join(desc.keys())
            self.desc = desc
        self.start = start
        self.size = size
        self.chans = []
        if method == 'input':
            self.request = ReadInputRegistersRequest
        elif method == 'holding':
            self.request = ReadHoldingRegistersRequest

    def build_read_request(self, slave_addr: int) -> str:
        req = self.request(self.start, self.size, slave_addr)
        return mb_framer.buildPacket(req)

    def gen_decoder_measurement(self, measurement, chan_list, tags={}, offset=0):
        linesep = f",\n        "
        m = re.match(r'ch(\d+)_(\w+)', measurement)
        measurement = 'dev_name'
        if m:
            measurement += f' + "_ch{repr(m.group(1))}"'
        lines = []
        #debug(chan_list)
        for chan_idx in chan_list:
            chan = self.chans[chan_idx]
            log.debug(f'{chan=}')
            lines.append(f"{sanitize_chan_name(chan['name'])}: {gen_chan_decoder(chan, self.start, offset=offset)}")
        fields = linesep.join(lines)
        return f'''{{
    measurement: {measurement},
    fields: {{
        {fields}
    }},
    tags: tags
}}'''

    def gen_decoder(self, *args, **kwargs):
        if self.desc:
            return [self.gen_decoder_measurement(measurement, chan_list, *args, **kwargs) for measurement, chan_list in self.desc.items()]
        else:
            return [self.gen_decoder_measurement(self.name, range(len(self.chans)), *args, **kwargs)]


class ModbusDevice:
    config: Dict[str, Any]
    input_regs: Dict[int, Dict[str, Any]]
    holding_regs: Dict[int, Dict[str, Any]]
    input_blocks: List[RegisterBlock]
    holding_blocks: List[RegisterBlock]

    def __init__(self, config_file, max_response_regs=None):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
    
        self.input_regs = {}
        self.holding_regs = {}
        self.input_blocks = []
        self.holding_blocks = []

        for chan in self.config['device']['channels']:
            if is_skipped(chan):
                continue
            addr = chan['address']
            if isinstance(addr, str):
                addr = int(addr, 16)
            if chan['reg_type'] == 'input':
                self.input_regs[addr] = chan
            elif chan['reg_type'] == 'holding':
                self.holding_regs[addr] = chan

        log.info(f"Loaded device config, {len(self.holding_regs)} holding, {len(self.input_regs)} input")
        self.split_into_blocks(max_response_regs=max_response_regs)

    @property
    def all_blocks(self):
        return self.input_blocks + self.holding_blocks

    def split_into_blocks(self, *args, **kwargs):
        self.input_blocks = self._split_into_blocks('input', self.input_regs, *args, **kwargs)
        self.holding_blocks = self._split_into_blocks('holding', self.holding_regs, *args, **kwargs)
    
#    def _split_into_blocks(self, method, regs, max_response_regs=None):
#        block_desc = self.config['device'].get(method+'_blocks', [])
#        blocks = []
#        for blk in block_desc:

    def _split_into_blocks(self, method, regs, max_response_regs=None):
        block_desc = self.config['device'].get(method+'_blocks', [])
        if not block_desc:
            return []
        next_addr = -1
        blocks: List[RegisterBlock] = []
        sorted_inputs = sorted(regs.items())
        block = RegisterBlock(block_desc[0], method, sorted_inputs[0][0], 0)
        block_idx = 0
        for addr, chan in sorted(regs.items()):
            log.debug(f"{block_idx=} {addr=} {chan['name']}")
            if addr == next_addr:
                s_addr = '------'
            else:
                s_addr = f'0x{addr:04x}'

            size = get_channel_size(chan)
            if (next_addr >= 0 and addr != next_addr) or (max_response_regs and block.size + size == max_response_regs):
                blocks.append(block)
                block_idx += 1
                if block_idx >= len(block_desc):
                    desc = f'new_block_{block_idx}'
                else:
                    desc = block_desc[block_idx]
                block = RegisterBlock(desc, method, addr, 0)

            block.chans.append(chan)
            block.size += size
            next_addr = addr + size
            log.debug(f"{s_addr}: {chan.get('group', ''):<16} {chan['name']:<32} {chan.get('format', ''):<5}")
        if block:
            blocks.append(block)

        return blocks

    def read_requests(self, slave_addr):
        for b in self.all_blocks:
            yield b.build_read_request(slave_addr)
