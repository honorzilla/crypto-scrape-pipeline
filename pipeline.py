import os
import boto3
import json
import yfinance as yf
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
    
    # Semboller: Kripto, Altın(GC=F), Gümüş(SI=F), S&P500(^GSPC), BIST100(XU100.IS)
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
            # yfinance ile varlığın verisini alıyoruz
            ticker_data = yf.Ticker(sembol)
            # Son 1 günlük veriyi çekip kapanış fiyatını (Close) alıyoruz
            hist = ticker_data.history(period="1d")
            
            if not hist.empty:
                fiyat = hist['Close'].iloc[-1]
                products.append({
                    "varlik_adi": isim,
                    "sembol": sembol,
                    "anlik_fiyat": f"{round(fiyat, 2)}",
                    "cekilen_tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            print(f"{isim} ({sembol}) için veri çekilemedi: {e}")
            
    return products

# ==========================================
# 3. LOAD: BULUTA YÜKLEME
# ==========================================
def upload_to_s3(data):
    if not data:
        print("S3'e yüklenecek veri bulunamadı.")
        return
        
    print(f"\nÇekilen Varlık Sayısı: {len(data)}")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
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
        Body=json.dumps(data, ensure_ascii=False, indent=4),
        ContentType='application/json'
    )
    print(f"Başarılı! Veri gölüne yüklendi: s3://{BUCKET_NAME}/{file_name}")

if __name__ == "__main__":
    scraped_data = fetch_market_data()
    upload_to_s3(scraped_data)