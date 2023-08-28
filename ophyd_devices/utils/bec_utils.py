import time

from bec_lib.core import bec_logger


logger = bec_logger.logger


class MockProducer:
    def set_and_publish(self, endpoint: str, msgdump: str):
        logger.info(f"BECMessage to {endpoint} with msg dump {msgdump}")


class MockDeviceManager:
    def __init__(self) -> None:
        self.devices = devices()


class devices:
    def __init__(self):
        self.mokev = mokev()


class mokev:
    def __init__(self):
        self.name = "mock_mokev"

    def read(self):
        return {self.name: {"value": 12.4, "timestamp": time.time()}}
