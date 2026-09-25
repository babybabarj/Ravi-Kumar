"""
NEWS/MACRO-1A: Source adapters for macro intelligence.

Each adapter is responsible for:
1. Fetching data from its authorised official source.
2. Enforcing point-in-time causal availability.
3. Returning a MacroDataQuality state that accurately reflects the
   data's availability and provenance.

All adapters are fail-closed: missing credentials, network errors, or
unavailable data surfaces as an explicit quality state (NOT_CONFIGURED,
NOT_IMPLEMENTED, MISSING) rather than silently returning None.

TRADING_CAPABILITY = ZERO
"""
from btceth_os.macro.sources.bls import BLSAdapter
from btceth_os.macro.sources.bea import BEAAdapter
from btceth_os.macro.sources.fed import FedAdapter
from btceth_os.macro.sources.treasury import TreasuryAdapter
from btceth_os.macro.sources.alfred import ALFREDAdapter
from btceth_os.macro.sources.dxy import DXYAdapter
from btceth_os.macro.sources.breaking_news import BreakingNewsAdapter

__all__ = [
    "BLSAdapter",
    "BEAAdapter",
    "FedAdapter",
    "TreasuryAdapter",
    "ALFREDAdapter",
    "DXYAdapter",
    "BreakingNewsAdapter",
]
