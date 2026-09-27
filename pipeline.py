import os
import boto3
import json
import yfinance as yf
import requests
from datetime import datetime


# ==========================================
# 1. KİMLİK BİLGİLERİ VE AYARLAR
# ==========================================
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
BUCKET_NAME = 'scrape-data-bucket-330656342602-eu-north-1-an'
REGION_NAME = 'eu-north-1'

# ==========================================
# 2. EXTRACT: YAHOO FINANCE İLE ÇOKLU PİYASA VERİSİ
# ==========================================
def fetch_market_data():
    print("Küresel piyasa verileri çekiliyor...")
    
    # Yahoo Finance'in GitHub'ı bot sanmaması için kendimizi gerçek tarayıcı gibi gösteriyoruz
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    varliklar = {
        "Bitcoin": "BTC-USD",
        "Ethereum": "ETH-USD",
        "Ons Altın": "GC=F",
        "Ons Gümüş": "SI=F",
        "S&P 500 Endeksi": "^GSPC",
        "BIST 100 Endeksi": "XU100.IS"
    }
    
    products = []
    
    for isim, sembol in varliklar.items():
        try:
            # Session'ı yfinance'e yediriyoruz
            ticker_data = yf.Ticker(sembol, session=session)
            # Hafta sonu boşluğu yememek için son 5 günü çekiyoruz
            hist = ticker_data.history(period="5d")
            
            if not hist.empty:
                # Son 5 günün içindeki en son (en güncel) fiyatı alıyoruz
                fiyat = hist['Close'].iloc[-1]
                products.append({
                    "varlik_adi": isim,
                    "sembol": sembol,
                    "anlik_fiyat": str(round(float(fiyat), 2)),
                    "cekilen_tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            print(f"{isim} ({sembol}) için veri çekilemedi: {e}")
            
    return products
# ==========================================
# 3. LOAD: BULUTA YÜKLEME (ATHENA İÇİN JSONL FORMATI)
# ==========================================
def upload_to_s3(data):
    if not data:
        print("S3'e yüklenecek veri bulunamadı.")
        return
        
    print(f"\nÇekilen Varlık Sayısı: {len(data)}")
    
    # Athena'nın okuyabilmesi için veriyi alt alta satırlar (JSONL) haline getiriyoruz
    jsonl_data = ""
    for item in data:
        jsonl_data += json.dumps(item, ensure_ascii=False) + "\n"
    
    print("\nPiyasa verileri AWS S3'e yükleniyor...")
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
    print(f"Başarılı! Veri gölüne yüklendi: s3://{BUCKET_NAME}/{file_name}")