from trading_bot.data.providers import BinancePublicProvider

provider = BinancePublicProvider(timeout=15.0)
print({"order_book": provider.fetch_order_book("BTC/USDT", limit=5)})
print({"ohlcv_count": len(provider.fetch_ohlcv("BTC/USDT", interval="1m", limit=10))})
print({"derivatives": provider.fetch_derivatives_context("BTC/USDT")})
