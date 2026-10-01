import requests, os, time, pandas as pd, numpy as np
from datetime import datetime

TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
BINANCE = "https://api.binance.com"

def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_mid_top_coins():
    # Lấy 250 coin top vốn hóa từ CoinGecko
    print("Đang lấy danh sách Mid+Top Cap từ CoinGecko...")
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false"
    data = requests.get(url, timeout=20).json()
    
    filtered = []
    for c in data:
        mc = c.get('market_cap', 0) or 0
        # Lọc Mid + Top Cap: 100M -> 100B
        if 100_000_000 <= mc <= 100_000_000_000:
            # symbol coingecko là btc, binance là BTCUSDT
            filtered.append(c['symbol'].upper() + "USDT")
    
    # Check xem coin nào có trên Binance không
    exchange = requests.get(f"{BINANCE}/api/v3/exchangeInfo").json()
    binance_symbols = set([s['symbol'] for s in exchange['symbols'] if s['status']=='TRADING'])
    
    final_list = [s for s in filtered if s in binance_symbols]
    
    # Loại coin rác stable
    blacklist = ['USDCUSDT','FDUSDUSDT','TUSDUSDT','DAIUSDT','BUSDUSDT']
    final_list = [s for s in final_list if s not in blacklist]
    
    final_list = final_list[:150] # lấy 150 con
    print(f"Đã lọc được {len(final_list)} coin Mid+Top Cap có trên Binance")
    return final_list

def get_klines(symbol, interval):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return None
        data = r.json()
        if len(data) < 30: return None
        df = pd.DataFrame(data, columns=['t','o','h','l','c','v','a','b','c1','c2','c3','c4'])
        df['c']=df['c'].astype(float); df['h']=df['h'].astype(float)
        df['l']=df['l'].astype(float); df['v']=df['v'].astype(float)
        return df
    except:
        return None

def calc_cci(df):
    tp = (df['h'] + df['l'] + df['c']) / 3
    sma = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma) / (0.015 * mad)
    return cci.iloc[-1]

def main():
    coins = get_mid_top_coins()
    signals = []

    for coin in coins:
        for tf in ["1h", "4h", "1d"]:
            df = get_klines(coin, tf)
            if df is None: continue
            try:
                cci = calc_cci(df)
                last_vol = df['v'].iloc[-1]
                avg_vol = df['v'].iloc[-21:-1].mean()
                vol_x = last_vol / avg_vol if avg_vol>0 else 0

                # ĐIỀU KIỆN FINAL CỦA BẠN
                if -250 < cci < -220 and vol_x >= 2.0:
                    signals.append({
                        "symbol": coin, "tf": tf, "cci": cci, 
                        "vol_x": vol_x, "price": df['c'].iloc[-1]
                    })
                    print(f"SIGNAL {coin} {tf} CCI {cci:.1f} Vol x{vol_x:.1f}")
            except Exception as e:
                print(f"Lỗi {coin}: {e}")
            time.sleep(0.25) # delay tránh bị block

    if not signals:
        print("Không có tín hiệu")
        return

    # Gửi về Telegram cá nhân, chia nhỏ tin nhắn
    header = f"🚨 *CCI MID+TOP RADAR {datetime.now().strftime('%d/%m %H:%M')}* 🚨\nQuét {len(coins)} coin | ĐK: CCI -250~-220 + Vol x2\n\n"
    msg = header
    
    for s in signals:
        line = f"✅ *{s['symbol']}* [{s['tf'].upper()}] ${s['price']:.4f}\n   CCI: `{s['cci']:.1f}` | Vol x{s['vol_x']:.1f} | [Chart](https://www.binance.com/en/trade/{s['symbol']})\n\n"
        msg += line
        if len(msg) > 3500:
            send(msg)
            msg = ""
            time.sleep(1)
    
    if msg != "" and msg != header:
        send(msg)

main()
