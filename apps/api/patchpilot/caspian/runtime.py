from functools import lru_cache

from patchpilot.caspian.adapter import CaspianGateway


@lru_cache
def get_gateway() -> CaspianGateway:
    return CaspianGateway()

