import os
import logging

import serial
from pexpect_serial import SerialSpawn

import grpc
from chirpstack_api import api

log = logging.getLogger("utils")

CHIRPSTACK_SERVER = os.environ.get('CHIRPSTACK_SERVER', '10.6.0.5:8080')
CHIRPSTACK_API_TOKEN = os.environ.get('CHIRPSTACK_API_TOKEN')

channel = grpc.insecure_channel(CHIRPSTACK_SERVER)
chirpstack_auth_token = [("authorization", "Bearer %s" % CHIRPSTACK_API_TOKEN)]
chirpstack_dev_service = api.DeviceServiceStub(channel)


class ATCommandError(Exception):
    def __init__(self, code, msg, *args, **kwargs):
        self.code = code
        self.msg = msg
        super().__init__(f'AT command error: {code}:{msg}', *args, **kwargs)

class SerialDevice:
    def __init__(self, port, *args, **kwargs):
        self.port = serial.Serial(port, *args, **kwargs)
        self.ss = SerialSpawn(self.port)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.port.close()

    def send_at_command(self, cmd):
        log.info(f'Sending {cmd}')
        self.ss.sendline(cmd)
        idx = self.ss.expect(['OK', r'ERROR:(\d+):(\w+)'], timeout=5)
        if idx == 0:
            return
        elif idx == 1:
            code, msg = self.ss.match.groups()
            raise ATCommandError(int(code), msg.decode())

    def sendline(self, *args, **kwargs):
        return self.ss.sendline(*args, **kwargs)

    def expect(self, *args, **kwargs):
        idx = self.ss.expect(*args, **kwargs)
        return (idx, self.ss.match)

    @property
    def match(self):
        return self.ss.match

class LoRaDevice:
    def __init__(self, eui):
        self.eui = eui

    def get_info(self):
        req = api.GetDeviceRequest(dev_eui=self.eui)
        return chirpstack_dev_service.Get(req, metadata=chirpstack_auth_token)

    def send(self, fport, data, confirmed=True):
        log.info(f"Sending LoRa downlink {fport=} {data=}")
        req = api.EnqueueDeviceQueueItemRequest()
        req.queue_item.confirmed = confirmed
        req.queue_item.data = bytes(data)
        req.queue_item.dev_eui = self.eui
        req.queue_item.f_port = fport
        return chirpstack_dev_service.Enqueue(req, metadata=chirpstack_auth_token)

