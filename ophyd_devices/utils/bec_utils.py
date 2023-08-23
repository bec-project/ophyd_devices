from bec_lib.core import bec_logger

logger = bec_logger.logger


class MockProducer:
    def set_and_publish(endpoint: str, msgdump: str):
        logger.info(f"BECMessage to {endpoint} with msg dump {msgdump}")
