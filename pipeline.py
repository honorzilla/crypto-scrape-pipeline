import os
import boto3
import json
import requests
import yfinance as yf
from datetime import datetime

# ==========================================
# 1. KİMLİK BİLGİLERİ VE AYARLAR
# ==========================================
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
BUCKET_NAME = 'scrape-data-bucket-330656342602-eu-north-1-an'
REGION_NAME = 'eu-north-1'

# ==========================================
# 2. EXTRACT & TRANSFORM: GENİŞ PORTFÖY
# ==========================================
def fetch_market_data():
    print("Genişletilmiş küresel piyasa verileri çekiliyor...")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    })

    # Kategorilere ayrılmış zengin varlık listesi
    portfoy = {
        "Döviz Kurları": {
            "USD / TRY": "USDTRY=X",
            "EUR / TRY": "EURTRY=X",
            "EUR / USD": "EURUSD=X"
        },
        "Emtialar": {
            "Ons Altın": "GC=F",
            "Ons Gümüş": "SI=F",
            "Brent Petrol": "BZ=F"
        },
        "Borsa Endeksleri": {
            "BIST 100": "XU100.IS",
            "S&P 500": "^GSPC",
            "Nasdaq 100": "^NDX"
        },
        "Şirketler & Teknoloji Devleri": {
            "Apple": "AAPL",
            "Nvidia": "NVDA",
            "Microsoft": "MSFT",
            "THY (THYAO)": "THYAO.IS"
        },
        "Fonlar (ETF'ler)": {
            "SPDR S&P 500 Fonu": "SPY",
            "Invesco QQQ (Tech ETF)": "QQQ",
            "Vanguard Total Stock": "VTI"
        },
        "Kripto Paralar": {
            "Bitcoin": "BTC-USD",
            "Ethereum": "ETH-USD",
            "Solana": "SOL-USD"
        }
    }

    products = []
    telegram_mesaji = "📊 *Kapsamlı Piyasa & Portföy Bülteni*\n"
    telegram_mesaji += f"🕒 _{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"

    for kategori, varliklar in portfoy.items():
        telegram_mesaji += f"*{kategori}*\n"
        
        for isim, sembol in varliklar.items():
            try:
                ticker_data = yf.Ticker(sembol, session=session)
                hist = ticker_data.history(period="5d")
                
                if len(hist) >= 2:
                    bugunku_fiyat = hist['Close'].iloc[-1]
                    dunku_fiyat = hist['Close'].iloc[-2]
                    
                    degisim = ((bugunku_fiyat - dunku_fiyat) / dunku_fiyat) * 100
                    ikon = "🟢" if degisim >= 0 else "🔴"
                    
                    telegram_mesaji += f"  {ikon} {isim}: `{bugunku_fiyat:.2f}` ({degisim:+.2f}%)\n"
                    
                    products.append({
                        "kategori": kategori,
                        "varlik_adi": isim,
                        "sembol": sembol,
                        "anlik_fiyat": str(round(bugunku_fiyat, 2)),
                        "gunluk_degisim_yuzdesi": str(round(degisim, 2)),
                        "cekilen_tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
            except Exception as e:
                print(f"{isim} ({sembol}) için hata: {e}")
                
        telegram_mesaji += "\n"

    return products, telegram_mesaji

# ==========================================
# 3. LOAD: S3 YÜKLEME VE TELEGRAM GÖNDERİMİ
# ==========================================
def upload_to_s3_and_notify(data, mesaj):
    if not data:
        print("İşlenecek veri bulunamadı.")
        return

    # S3 Veri Gölü Yüklemesi (JSONL formatı)
    jsonl_data = ""
    for item in data:
        jsonl_data += json.dumps(item, ensure_ascii=False) + "\n"

    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=REGION_NAME
    )

    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    file_name = f"piyasa_takibi/market_data_{date_str}.json"

    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=file_name,
        Body=jsonl_data,
        ContentType='application/jsonlines'
    )
    print(f"Toplam {len(data)} adet varlık S3 veri gölüne yüklendi.")

    # Telegram Mesajı Gönderme
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mesaj,
            "parse_mode": "Markdown"
        }
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            print("Piyasa bülteni Telegram'a fırlatıldı!")
        else:
            print("Telegram hatası:", res.text)

# ==========================================
# ANA ÇALIŞTIRMA BLOĞU
# ==========================================
if __name__ == "__main__":
    scraped_data, bot_mesaji = fetch_market_data()
    upload_to_s3_and_notify(scraped_data, bot_mesaji)