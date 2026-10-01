import requests, os, time, pandas as pd, numpy as np
from datetime import datetime

TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

BINANCE = "https://api.binance.com"

def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_top_coins(limit=100):
    # Lấy top coin theo volume 24h trên Binance, loại bỏ stable coin
    url = f"{BINANCE}/api/v3/ticker/24hr"
    data = requests.get(url).json()
    # chỉ lấy cặp USDT
    usdt_pairs = [d for d in data if d['symbol'].endswith('USDT')]
    # loại stable & BTC, ETH để tập trung mid/top altcoin
    blacklist = ['USDCUSDT','BUSDUSDT','FDUSDUSDT','TUSDUSDT','DAIUSDT','BTCUSDT','ETHUSDT']
    usdt_pairs = [d for d in usdt_pairs if d['symbol'] not in blacklist]
    # sort theo volume
    usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
    # lấy top
    symbols = [d['symbol'] for d in usdt_pairs[:limit]]
    print(f"Quét {len(symbols)} coin: {symbols[:10]}...")
    return symbols

def get_klines(symbol, interval, limit=100):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    r = requests.get(url, timeout=10)
    if r.status_code != 200: return None
    data = r.json()
    if len(data) < 30: return None
    df = pd.DataFrame(data, columns=['t','o','h','l','c','v','c1','c2','c3','c4','c5','c6'])
    df['c'] = df['c'].astype(float); df['h'] = df['h'].astype(float)
    df['l'] = df['l'].astype(float); df['v'] = df['v'].astype(float)
    return df

def calc_cci(df, period=20):
    tp = (df['h'] + df['l'] + df['c']) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma) / (0.015 * mad)
    return cci.iloc[-1]

def scan_symbol(symbol):
    found = []
    for tf in ["1h", "4h", "1d"]:
        try:
            df = get_klines(symbol, tf)
            if df is None: continue
            cci = calc_cci(df)
            last_vol = df['v'].iloc[-1]
            avg_vol = df['v'].iloc[-21:-1].mean()
            vol_x = last_vol / avg_vol if avg_vol>0 else 0
            
            # ĐIỀU KIỆN CỦA BẠN
            if -250 < cci < -220 and vol_x >= 2.0:
                found.append({
                    "symbol": symbol, "tf": tf, "cci": cci, 
                    "vol_x": vol_x, "price": df['c'].iloc[-1]
                })
            time.sleep(0.2) # tránh bị Binance block
        except Exception as e:
            print(f"Lỗi {symbol} {tf}: {e}")
            continue
    return found

def main():
    coins = get_top_coins(80) # quét 80 con top+mid cap
    all_signals = []
    
    for coin in coins:
        sigs = scan_symbol(coin)
        if sigs:
            all_signals.extend(sigs)
    
    if not all_signals:
        print(f"{datetime.now()} - Không có tín hiệu")
        return

    # Gom tin nhắn lại 1 lần cho đỡ spam
    msg = f"🚨 *CCI BOTTOM RADAR {datetime.now().strftime('%d/%m %H:%M')}* 🚨\n"
    msg += f"Quét {len(coins)} coin Top/Mid Cap\n\n"
    
    for s in all_signals:
        msg += f"✅ *{s['symbol']}* - {s['tf'].upper()}\n"
        msg += f"   Giá: ${s['price']:.4f} | CCI: `{s['cci']:.1f}` | Vol x{s['vol_x']:.1f}\n"
        msg += f"   └> [Trade](https://www.binance.com/en/trade/{s['symbol']})\n\n"
        # Telegram giới hạn tin nhắn, nếu nhiều quá thì cắt ra
        if len(msg) > 3500:
            send(msg)
            msg = ""
            time.sleep(1)
    
    if msg:
        send(msg)
    print(f"Đã gửi {len(all_signals)} tín hiệu")

main()
