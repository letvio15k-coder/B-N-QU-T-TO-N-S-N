import requests, os, time, threading, pandas as pd, numpy as np
from flask import Flask
from datetime import datetime

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
BINANCE = "https://api.binance.com"

# Để Render thấy có port
@app.route('/')
def home():
    return "Bot CCI 150 coin đang chạy..."

def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=10)
    except: pass

def get_mid_top_coins():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false"
        data = requests.get(url, timeout=20).json()
        filtered = []
        for c in data:
            mc = c.get('market_cap',0) or 0
            if 100_000_000 <= mc <= 100_000_000_000:
                filtered.append(c['symbol'].upper() + "USDT")
        ex = requests.get(f"{BINANCE}/api/v3/exchangeInfo", timeout=10).json()
        binance_symbols = set([s['symbol'] for s in ex['symbols'] if s['status']=='TRADING'])
        final = [s for s in filtered if s in binance_symbols]
        blacklist = ['USDCUSDT','FDUSDUSDT','TUSDUSDT','DAIUSDT','BUSDUSDT']
        final = [s for s in final if s not in blacklist][:150]
        return final
    except:
        return ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","ASTERUSDT","OPUSDT","ARBUSDT"] # fallback

def get_klines(symbol, interval):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        if len(d) < 30: return None
        df = pd.DataFrame(d, columns=['t','o','h','l','c','v','a','b','c1','c2','c3','c4'])
        df['c']=df['c'].astype(float); df['h']=df['h'].astype(float)
        df['l']=df['l'].astype(float); df['v']=df['v'].astype(float)
        return df
    except: return None

def calc_cci(df):
    tp = (df['h'] + df['l'] + df['c']) / 3
    sma = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma) / (0.015 * mad)
    return cci.iloc[-1]

def scan_loop():
    while True:
        try:
            coins = get_mid_top_coins()
            print(f"{datetime.now()} - Quét {len(coins)} coin")
            signals = []
            for coin in coins:
                for tf in ["1h","4h","1d"]:
                    df = get_klines(coin, tf)
                    if df is None: continue
                    try:
                        cci = calc_cci(df)
                        vol_x = df['v'].iloc[-1] / df['v'].iloc[-21:-1].mean()
                        if -250 < cci < -220 and vol_x >= 2.0:
                            signals.append({"symbol":coin,"tf":tf,"cci":cci,"vol_x":vol_x,"price":df['c'].iloc[-1]})
                    except: pass
                    time.sleep(0.2)
            if signals:
                msg = f"🚨 *CCI 150 MID+TOP {datetime.now().strftime('%d/%m %H:%M')}* 🚨\n\n"
                for s in signals[:15]: # gửi tối đa 15 con 1 lần
                    msg += f"✅ *{s['symbol']}* [{s['tf'].upper()}] ${s['price']:.4f} CCI:`{s['cci']:.1f}` Vol x{s['vol_x']:.1f}\n"
                send(msg)
            else:
                print("Không có tín hiệu")
        except Exception as e:
            print(f"Lỗi scan: {e}")
        print("Ngủ 30 phút...")
        time.sleep(1800)

# Chạy scan ở background
threading.Thread(target=scan_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
