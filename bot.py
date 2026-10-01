import requests, os, time, threading, pandas as pd, numpy as np
from flask import Flask
from datetime import datetime

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
BINANCE = "https://api.binance.com"

# Cho Render thấy có web
@app.route('/')
def home():
    return f"Bot CCI 150 Mid+Top đang chạy - {datetime.now().strftime('%d/%m %H:%M:%S')}"

def send(msg):
    if not TOKEN or not CHAT_ID:
        print("Chưa có TOKEN hoặc CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=15)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

def get_mid_top_coins():
    try:
        print("Lấy danh sách Mid+Top từ CoinGecko...")
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false"
        data = requests.get(url, timeout=20).json()
        filtered = []
        for c in data:
            mc = c.get('market_cap',0) or 0
            # Mid Cap 100M-1B + Top Cap >1B
            if 100_000_000 <= mc:
                filtered.append(c['symbol'].upper() + "USDT")

        ex = requests.get(f"{BINANCE}/api/v3/exchangeInfo", timeout=10).json()
        binance_symbols = set([s['symbol'] for s in ex['symbols'] if s['status']=='TRADING'])
        final = [s for s in filtered if s in binance_symbols]

        blacklist = ['USDCUSDT','FDUSDUSDT','TUSDUSDT','DAIUSDT','BUSDUSDT','EURUSDT']
        final = [s for s in final if s not in blacklist]
        final = final[:150]
        print(f"Đã lọc {len(final)} coin")
        return final
    except Exception as e:
        print(f"Lỗi lấy coin list: {e}, dùng fallback")
        return ["ASTERUSDT","BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","OPUSDT","ARBUSDT","LINKUSDT","MATICUSDT","DOTUSDT","LTCUSDT"]

def get_klines(symbol, interval):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code!= 200: return None
        d = r.json()
        if len(d) < 35: return None
        df = pd.DataFrame(d, columns=['t','o','h','l','c','v','a','b','c1','c2','c3','c4'])
        df['c']=df['c'].astype(float); df['h']=df['h'].astype(float)
        df['l']=df['l'].astype(float); df['v']=df['v'].astype(float)
        return df
    except:
        return None

def calc_cci(df, period=20):
    tp = (df['h'] + df['l'] + df['c']) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma) / (0.015 * mad)
    return cci.iloc[-1]

# Chống spam: báo rồi thì 6 tiếng sau mới báo lại
sent_cache = {}

def scan_loop():
    # Báo đã online để bạn biết bot sống
    time.sleep(5)
    send(f"✅ *Bot CCI 150 Mid+Top ONLINE*\n{datetime.now().strftime('%d/%m/%Y %H:%M')}\nĐang quét Top+Mid Cap | DK: CCI -250~-220 + Vol x2\nWeb: {os.environ.get('RENDER_EXTERNAL_URL','')}")

    while True:
        try:
            coins = get_mid_top_coins()
            signals = []
            now = datetime.now()

            for coin in coins:
                for tf in ["1h", "4h", "1d"]:
                    key = f"{coin}_{tf}"
                    # Nếu đã báo trong 6 tiếng thì bỏ qua
                    if key in sent_cache and (now - sent_cache[key]).total_seconds() < 21600:
                        continue

                    df = get_klines(coin, tf)
                    if df is None: continue

                    try:
                        cci = calc_cci(df)
                        last_vol = df['v'].iloc[-1]
                        avg_vol = df['v'].iloc[-21:-1].mean()
                        if avg_vol == 0: continue
                        vol_x = last_vol / avg_vol

                        # ĐIỀU KIỆN CỦA BẠN
                        if -250 < cci < -220 and vol_x >= 2.0:
                            signals.append({
                                "symbol": coin, "tf": tf, "cci": cci,
                                "vol_x": vol_x, "price": df['c'].iloc[-1]
                            })
                            sent_cache[key] = now
                            print(f"SIGNAL {coin} {tf} CCI {cci:.1f} Vol x{vol_x:.1f}")
                    except: pass
                    time.sleep(0.2)

            if signals:
                msg = f"🚨 *CCI BOTTOM 150 COIN {now.strftime('%H:%M')}* 🚨\n"
                msg += f"DK: CCI -250~-220 + Vol Spike x2\n\n"
                for s in signals[:20]:
                    msg += f"✅ *{s['symbol']}* [{s['tf'].upper()}] ${s['price']:.5f}\n"
                    msg += f" CCI: `{s['cci']:.1f}` | Vol: x{s['vol_x']:.1f}\n"
                    msg += f" [Trade](https://www.binance.com/en/trade/{s['symbol']})\n\n"
                send(msg)
                print(f"Đã gửi {len(signals)} tín hiệu")
            else:
                print(f"{now.strftime('%H:%M:%S')} - Không có tín hiệu")

        except Exception as e:
            print(f"Lỗi vòng quét: {e}")
            send(f"⚠️ Bot lỗi: {e}")

        print("Ngủ 30 phút...")
        time.sleep(1800) # 30 phút

# Chạy quét ngầm
threading.Thread(target=scan_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
