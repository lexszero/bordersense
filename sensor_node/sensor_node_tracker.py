import logging
from typing import Literal

from pydantic import BaseModel

from .utils import LoRaDevice, SerialDevice
from .sensor_node import SensorNode

log = logging.getLogger("sensor_node_tracker")

class SensorNodeTrackerConfig(BaseModel):
    device_type: Literal['trackerd']
    fix_time: int
    update_interval_static: int
    update_interval_motion: int

class SensorNodeTrackerDragino(SensorNode):
    config: SensorNodeTrackerConfig

    def __init__(self, config: SensorNodeTrackerConfig):
        self.config = config

    def configure_local(self, args):
        log.info("Configuring Dragino TrackerD over serial")
        with SerialDevice(args.port, baudrate=115200) as dev:
            dev.send_at_command("AT+INTWK=1")
            dev.send_at_command(f"AT+FTIME={self.config.fix_time}")
            dev.send_at_command(f"AT+TDC={self.config.update_interval_static*1000}")
            dev.send_at_command(f"AT+MTDC={self.config.update_interval_motion*1000}")

    def configure_lora(self, args):
        pass

SensorNode.register('trackerd', SensorNodeTrackerDragino, SensorNodeTrackerConfig)
