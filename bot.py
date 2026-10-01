import requests, os, time, threading, pandas as pd, numpy as np
from flask import Flask
from datetime import datetime

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
BINANCE = "https://api.binance.com"

# === CẤU HÌNH CỦA BẠN ===
VOL_MIN = 2.0
VOL_MAX = 5.0
TIMEFRAMES = ["1h", "4h", "1d"] # auto quét 3 khung
AUTO_SCAN = True
SCAN_INTERVAL = 1800 # 30 phút

sent_cache = {}
last_update_id = 0
scan_now_flag = False

@app.route('/')
def home():
    return f"Bot CCI Vol {VOL_MIN}x-{VOL_MAX}x | TF {','.join(TIMEFRAMES)} | Auto:{AUTO_SCAN} | {datetime.now()}"

def send(msg):
    if not TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
    except: pass

def get_mid_top_coins():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false"
        data = requests.get(url, timeout=20).json()
        filtered = []
        for c in data:
            mc = c.get('market_cap',0) or 0
            if mc >= 100_000_000:
                filtered.append(c['symbol'].upper() + "USDT")
        ex = requests.get(f"{BINANCE}/api/v3/exchangeInfo", timeout=10).json()
        binance_symbols = set([s['symbol'] for s in ex['symbols'] if s['status']=='TRADING'])
        final = [s for s in filtered if s in binance_symbols]
        blacklist = ['USDCUSDT','FDUSDUSDT','TUSDUSDT','DAIUSDT','EURUSDT']
        final = [s for s in final if s not in blacklist][:150]
        return final
    except:
        return ["ASTERUSDT","BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","OPUSDT","ARBUSDT","LINKUSDT","AVAXUSDT","DOGEUSDT","ADAUSDT","XRPUSDT","DOTUSDT","MATICUSDT","LTCUSDT"]

def get_klines(symbol, interval):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code!= 200: return None
        d = r.json()
        if len(d) < 35: return None
        df = pd.DataFrame(d, columns=['t','o','h','l','c','v','a','b','c1','c2','c3','c4'])
        df['c']=df['c'].astype(float); df['h']=df['h'].astype(float); df['l']=df['l'].astype(float); df['v']=df['v'].astype(float)
        return df
    except: return None

def calc_cci(df):
    tp = (df['h'] + df['l'] + df['c']) / 3
    sma = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma) / (0.015 * mad)
    return cci.iloc[-1]

def do_scan():
    global sent_cache
    coins = get_mid_top_coins()
    print(f"{datetime.now()} - Quét {len(coins)} coin Vol {VOL_MIN}x-{VOL_MAX}x")
    signals = []
    now = datetime.now()
    for coin in coins:
        for tf in TIMEFRAMES:
            key = f"{coin}_{tf}"
            if key in sent_cache and (now - sent_cache[key]).total_seconds() < 21600:
                continue
            df = get_klines(coin, tf)
            if df is None: continue
            try:
                cci = calc_cci(df)
                vol_x = df['v'].iloc[-1] / df['v'].iloc[-21:-1].mean()
                # ĐK FINAL: CCI -250~-220 và Vol x2-x5
                if -250 < cci < -220 and VOL_MIN <= vol_x <= VOL_MAX:
                    signals.append({"symbol":coin,"tf":tf,"cci":cci,"vol_x":vol_x,"price":df['c'].iloc[-1]})
                    sent_cache[key] = now
            except: pass
            time.sleep(0.15)

    if signals:
        msg = f"🚨 *CCI VOL {VOL_MIN}x-{VOL_MAX}x {now.strftime('%H:%M')}* 🚨\n"
        msg += f"TF: {','.join(TIMEFRAMES)} | {len(coins)} coin Mid+Top\n\n"
        for s in signals[:20]:
            msg += f"✅ *{s['symbol']}* [{s['tf'].upper()}] ${s['price']:.5f}\n CCI:`{s['cci']:.1f}` Vol x{s['vol_x']:.1f}\n [Trade](https://www.binance.com/en/trade/{s['symbol']})\n\n"
        send(msg)
    else:
        print("Không có tín hiệu")
    return len(signals)

def scan_loop():
    global scan_now_flag
    send(f"✅ *Bot ONLINE*\nVol: {VOL_MIN}x-{VOL_MAX}x | TF: {','.join(TIMEFRAMES)}\nAuto quét: {'BẬT' if AUTO_SCAN else 'TẮT'} / 30p\nLệnh: /scan /check /auto /status")
    while True:
        try:
            if AUTO_SCAN or scan_now_flag:
                do_scan()
                scan_now_flag = False
            else:
                print("Auto quét đang TẮT")
        except Exception as e:
            print(f"Lỗi scan: {e}")
        time.sleep(SCAN_INTERVAL)

def command_loop():
    global last_update_id, scan_now_flag, AUTO_SCAN, VOL_MIN, VOL_MAX
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id+1}&timeout=30"
            r = requests.get(url, timeout=35).json()
            if not r.get('ok'):
                time.sleep(3); continue
            for upd in r.get('result', []):
                last_update_id = upd['update_id']
                msg_obj = upd.get('message',{})
                text = msg_obj.get('text','').strip()
                chat = str(msg_obj.get('chat',{}).get('id',''))
                if chat!= str(CHAT_ID): continue

                if text in ['/start','/help']:
                    send("🤖 *LỆNH BOT*\n/start - Menu\n/status - Trạng thái\n/scan - Quét ngay\n/check SYMBOL - vd /check ASTERUSDT\n/auto on - Bật auto\n/auto off - Tắt auto\n/vol 2 5 - Đổi vol min max")
                elif text == '/status':
                    send(f"📊 *STATUS*\nVol: {VOL_MIN}x-{VOL_MAX}x\nTF: {','.join(TIMEFRAMES)}\nAuto: {'BẬT' if AUTO_SCAN else 'TẮT'}\nCache: {len(sent_cache)} tín hiệu\nGiờ: {datetime.now().strftime('%H:%M:%S')}")
                elif text == '/scan':
                    send("⏳ Đang quét ngay 150 coin...")
                    scan_now_flag = True
                elif text.startswith('/check'):
                    parts = text.split()
                    if len(parts)<2: send("Dùng: /check ASTERUSDT")
                    else:
                        sym = parts[1].upper()
                        if not sym.endswith('USDT'): sym+='USDT'
                        rep = f"🔍 *{sym}*\n"
                        for tf in TIMEFRAMES:
                            df = get_klines(sym, tf)
                            if df is None: rep+=f"{tf}: no data\n"; continue
                            cci = calc_cci(df); vol_x = df['v'].iloc[-1]/df['v'].iloc[-21:-1].mean()
                            ok = "✅" if (-250<cci<-220 and VOL_MIN<=vol_x<=VOL_MAX) else "❌"
                            rep+=f"{ok} {tf.upper()}: CCI `{cci:.1f}` Vol x{vol_x:.1f} ${df['c'].iloc[-1]:.4f}\n"
                        send(rep)
                elif text.startswith('/auto'):
                    if 'off' in text: AUTO_SCAN=False; send("🔴 Auto quét đã TẮT")
                    else: AUTO_SCAN=True; send("🟢 Auto quét đã BẬT - 1h,4h,1D")
                elif text.startswith('/vol'):
                    try:
                        p=text.split(); VOL_MIN=float(p[1]); VOL_MAX=float(p[2])
                        send(f"Đã đổi Vol thành {VOL_MIN}x - {VOL_MAX}x")
                    except: send("Dùng: /vol 2 5")
            time.sleep(2)
        except Exception as e:
            print(f"Lỗi command: {e}"); time.sleep(5)

threading.Thread(target=scan_loop, daemon=True).start()
threading.Thread(target=command_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
