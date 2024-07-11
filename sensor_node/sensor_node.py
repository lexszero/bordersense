import logging
from pydantic import BaseModel

log = logging.getLogger("sensor_node")

class SensorNodeConfig(BaseModel):
    device_type: str

DEVICE_TYPES = {}

class SensorNode:
    @staticmethod
    def register(device_type: str, cls, conf_cls):
        log.info(f"Registering device type {device_type}")
        DEVICE_TYPES[device_type] = (cls, conf_cls)

    @staticmethod
    def create(conf_file: str):
        log.info(f"Loading sensor node configuration {conf_file}")
        conf_data = None
        with open(conf_file, 'r') as f:
            conf_data = f.read()

        config = SensorNodeConfig.model_validate_json(conf_data)

        device_class, config_class = DEVICE_TYPES[config.device_type]
        device_config = config_class.model_validate_json(conf_data)
        return device_class(device_config)

    def configure_local(self, args):
        log.fatal("Undefined configure_local")

    def do_configure_local(self, args):
        self.configure_local(args)

    def configure_lora(self, args):
        log.fatal("Undefined configure_lora")

    def do_configure_lora(self, args):
        self.configure_lora(args)
