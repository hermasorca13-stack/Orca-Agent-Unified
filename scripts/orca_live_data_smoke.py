from trading_bot.data.providers import BinancePublicProvider

provider = BinancePublicProvider(timeout=10.0)
quote = provider.fetch_quote("BTC/USDT")
print({"exchange": quote.exchange, "symbol": quote.symbol, "bid": quote.bid, "ask": quote.ask, "volume_24h": quote.volume_24h, "spread_bps": quote.spread_bps})
