from .base import ExchangeAdapter
from .paper import PaperExchange

__all__ = ["ExchangeAdapter", "PaperExchange"]

try:
    from .ccxt_adapter import CcxtExchange, CcxtUnavailable
    __all__ += ["CcxtExchange", "CcxtUnavailable"]
except ImportError:
    pass
