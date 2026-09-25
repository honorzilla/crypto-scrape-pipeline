import requests
import boto3
import json
from datetime import datetime
import os

# ==========================================
# 1. KİMLİK BİLGİLERİ VE AYARLAR
# ==========================================
# Anahtarları artık kodun içine değil, GitHub Secrets ortamına yazacağız
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
BUCKET_NAME = 'scrape-data-bucket-330656342602-eu-north-1-an'
REGION_NAME = 'eu-north-1'

# ==========================================
# 2. EXTRACT: BİNANCE CANLI KRİPTO VERİSİ
# ==========================================
def fetch_crypto_prices():
    print("Binance API'sinden canlı kripto fiyatları çekiliyor...")
    # Binance API asla bot engeli atmaz, tamamen herkese açıktır.
    url = "https://api.binance.com/api/v3/ticker/price"
    
    products = []
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Piyasayı domine eden 5 ana coini seçiyoruz
        hedef_coinler = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
        
        for item in data:
            if item['symbol'] in hedef_coinler:
                products.append({
                    "coin_adi": item['symbol'].replace("USDT", ""),
                    "anlik_fiyat": str(round(float(item['price']), 2)) + " $",
                    "cekilen_tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
    except Exception as e:
        print(f"API bağlantı hatası: {e}")
        
    return products

# ==========================================
# 3. LOAD: BULUTA YÜKLEME
# ==========================================
def upload_to_s3(data):
    if not data:
        print("S3'e yüklenecek veri bulunamadı.")
        return
        
    print(f"\nÇekilen Veri Sayısı: {len(data)}")
    print(json.dumps(data, indent=2)) # Veriyi ekranda da gör
    
    print("\nKripto verileri AWS S3'e yükleniyor...")
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=REGION_NAME
    )
    
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    file_name = f"kripto_takibi/binance_prices_{date_str}.json"
    
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=file_name,
        Body=json.dumps(data, ensure_ascii=False, indent=4),
        ContentType='application/json'
    )
    print(f"Başarılı! Veri gölüne yüklendi: s3://{BUCKET_NAME}/{file_name}")

if __name__ == "__main__":
    scraped_data = fetch_crypto_prices()
    upload_to_s3(scraped_data)