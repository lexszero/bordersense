#!/usr/bin/env python3
import os, sys, logging
from devtools import debug

log = logging.getLogger("console")

import grpc
from chirpstack_api import api

CHIRPSTACK_SERVER = 'gw-rpi:8080'
CHIRPSTACK_API_TOKEN = os.environ.get('CHIRPSTACK_API_TOKEN')
channel = grpc.insecure_channel(CHIRPSTACK_SERVER)
auth_token = [("authorization", "Bearer %s" % CHIRPSTACK_API_TOKEN)]

dev_svc = api.DeviceServiceStub(channel)

def send_lora_cmd(dev_eui, fport, buf, confirmed=True):
    log.info(f"Sending to {dev_eui} {fport=} {confirmed=}: {buf}")
    req = api.EnqueueDeviceQueueItemRequest()
    req.queue_item.confirmed = confirmed
    req.queue_item.data = bytes(buf)
    req.queue_item.dev_eui = dev_eui
    req.queue_item.f_port = fport
    return dev_svc.Enqueue(req, metadata=auth_token)

def rak7431_reset(dev_eui):
    send_lora_cmd(dev_eui, 129, bytes([0x1f, 0x00, 0x01, 0x00, 0x00]))
