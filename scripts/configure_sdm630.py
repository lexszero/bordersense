#!/usr/bin/env python3
import logging, coloredlogs

from pymodbus.constants import Defaults, Endian
Defaults.Slave = 1

from pymodbus.transaction import ModbusRtuFramer
from pymodbus.factory import ClientDecoder as ModbusClientDecoder
from pymodbus.payload import BinaryPayloadBuilder

from pymodbus.register_read_message import (
        ReadHoldingRegistersRequest,
        )

from pymodbus.register_write_message import (
        WriteMultipleRegistersRequest
        )

import grpc
from chirpstack_api import api

log = logging.getLogger()
coloredlogs.install(
        fmt="%(name)s %(levelname)s: %(message)s",
        level=logging.DEBUG
        )
logging.getLogger('pymodbus').setLevel(logging.WARN)

CHIRPSTACK_SERVER = 'gw-rpi:8080'
CHIRPSTACK_API_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJjaGlycHN0YWNrIiwiaXNzIjoiY2hpcnBzdGFjayIsInN1YiI6ImIxNjQ1NzMxLTU5NjctNGMwOS1hOTAwLWQ2ZDQ3ZmVkODg5NiIsInR5cCI6ImtleSJ9.ssJUZHVP3AuZQQItWJrYs6-XUAyBXaIybnSWk6vkhPI'
SDM630_PASSWORD = 1000
SDM630_UPLOAD_INTERVAL = 5
FIELDS = [7,8,9]

def sdm630_config_downlinks(fields, password=SDM630_PASSWORD, upload_interval=SDM630_UPLOAD_INTERVAL):
    # Source: https://www.thethingsnetwork.org/forum/t/trouble-getting-an-eastron-sdm630-meter-to-send-data/59992/7
    
    yield ReadHoldingRegistersRequest(0x18, 2, 1)                       # knock-knock

    b = BinaryPayloadBuilder(byteorder=Endian.Big)
    b.add_32bit_float(password)
    r_password = b.to_registers()
    b.reset()

    yield WriteMultipleRegistersRequest(0x18, r_password, 1)
    yield ReadHoldingRegistersRequest(0x0E, 2)

    for f in FIELDS + [0xff]*(30-len(fields)):
        b.add_8bit_uint(f)
    r_fields = b.to_registers()
    b.reset()

    yield WriteMultipleRegistersRequest(0xFE12, [len(fields)], 1)      # WTF??? 5 or 6 in examples
    yield WriteMultipleRegistersRequest(0xFE02, r_fields, 1)
    yield WriteMultipleRegistersRequest(0xFE01, [upload_interval], 1)


def send_downlinks(dev_eui):
    channel = grpc.insecure_channel(CHIRPSTACK_SERVER)

    # Device-queue API client.
    client = api.DeviceServiceStub(channel)

    # Define the API key meta-data.
    auth_token = [("authorization", "Bearer %s" % CHIRPSTACK_API_TOKEN)]

    mbf = ModbusRtuFramer(ModbusClientDecoder())
    for req in sdm630_config_downlinks(FIELDS):
        packet = mbf.buildPacket(req)

        req = api.EnqueueDeviceQueueItemRequest()
        req.queue_item.confirmed = True
        req.queue_item.data = packet
        req.queue_item.dev_eui = dev_eui
        req.queue_item.f_port = 1
        resp = client.Enqueue(req, metadata=auth_token)
        log.info(f"Sent {packet.hex('')} -> ID {resp.id}")
        log.info(resp.id)

if __name__ == '__main__':
    send_downlinks('0101010101010101')
