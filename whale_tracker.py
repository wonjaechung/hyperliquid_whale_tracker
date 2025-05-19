import asyncio, json, sys, os, csv
from datetime import datetime
from websockets import connect
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL


### WS_URL = " " 
THRESHOLD = 10000  # 저장할 최소 거래 금액 (USD)
COINS = ["BTC", "ETH", "SOL"]
CSV_FILE = "whale_logs.csv"

info = Info(MAINNET_API_URL, skip_ws=True)


def safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def append_to_csv(row):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Address", "Symbol", "Side",
                "Position (USD)", "Position (Coin)",
                "Entry Price", "Liq. Price", "Margin",
                "Unrealised PnL", "Leverage", "Lev. Type",
                "Trade Price", "Timestamp"
            ])
        writer.writerow(row)


def print_header():
    header = (
        f"{'Address':42s} | {'Symbol':6s} | {'Side':5s} | "
        f"{'Position':>12s} | {'Coin':>10s} | {'Entry Px':>10s} | "
        f"{'Liq. Px':>10s} | {'Margin':>10s} | {'PnL':>10s} | "
        f"{'Lev':>4s} | {'Type':>6s} | {'Trade Px':>10s} | Time"
    )
    print(header)
    print("-" * len(header))

async def whale_tracker():
    async with connect(WS_URL) as ws:
    
        for coin in COINS:
            await ws.send(json.dumps({
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": coin}
            }))
        print(f"🔔 Subscribed to trades for: {COINS}\n")
        print_header()


        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("channel") != "trades":
                    continue

                for t in msg["data"]:
                    price = safe_float(t["px"])
                    size = safe_float(t["sz"])
                    value = price * size
                    symbol = t["coin"]
                    side = t["side"]
                    ts = datetime.fromtimestamp(t["time"] / 1000).strftime("%Y-%m-%d %H:%M")

                    print(f"▶ TRADE: {symbol} {side} {size:.4f}@{price:.2f} = ${value:,.2f}")

                    if value < THRESHOLD:
                        continue

                    for user_addr in t.get("users", []):
                        print(f"• Fetching state for {user_addr} …", file=sys.stderr)
                        try:
                            us = info.user_state(user_addr)
                            positions = us.get("assetPositions", [])
                        except Exception as e:
                            print(f"❌ Error fetching state: {e}", file=sys.stderr)
                            continue

                        for ap in positions:
                            pos = ap.get("position", {})
                            if pos.get("coin") != symbol:
                                continue

        
                            position_usd = safe_float(pos.get("positionValue"))
                            position_coin = safe_float(pos.get("szi"))
                            entry_price = safe_float(pos.get("entryPx"))
                            liq_price = safe_float(pos.get("liquidationPx"))
                            margin_used = safe_float(pos.get("marginUsed"))
                            unreal_pnl = safe_float(pos.get("unrealizedPnl"))
                            leverage = safe_float(pos.get("leverage", {}).get("value"))
                            lev_type = pos.get("leverage", {}).get("type", "unknown")

                        
                            print(
                                f"{user_addr:42s} | {symbol:<6s} | {side:<5s} | "
                                f"{position_usd:12,.2f} | {position_coin:10,.4f} | {entry_price:10,.2f} | "
                                f"{liq_price:10,.2f} | {margin_used:10,.2f} | {unreal_pnl:10,.2f} | "
                                f"{leverage:4.0f} | {lev_type:<6s} | {price:10,.2f} | {ts}"
                            )

                            append_to_csv([
                                user_addr, symbol, side,
                                position_usd, position_coin,
                                entry_price, liq_price, margin_used,
                                unreal_pnl, leverage, lev_type,
                                price, ts
                            ])

            except Exception as e:
                print(f"❌ Error while processing trade: {e}", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(whale_tracker())

