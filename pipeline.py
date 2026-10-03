import os
import boto3
import json
import requests
import io
import yfinance as yf
import pandas as pd
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
# 2. EXTRACT & TRANSFORM: VERİ ÇEKME
# ==========================================
def fetch_market_data():
    print("Küresel piyasa verileri çekiliyor...")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    portfoy = {
        "Döviz Kurları": {"USD / TRY": "USDTRY=X", "EUR / TRY": "EURTRY=X", "EUR / USD": "EURUSD=X"},
        "Emtialar": {"Ons Altın": "GC=F", "Ons Gümüş": "SI=F", "Brent Petrol": "BZ=F"},
        "Borsa Endeksleri": {"BIST 100": "XU100.IS", "S&P 500": "^GSPC", "Nasdaq 100": "^NDX"},
        "Şirketler": {"Apple": "AAPL", "Nvidia": "NVDA", "Microsoft": "MSFT", "THY": "THYAO.IS"},
        "Fonlar (ETF)": {"SPDR S&P 500": "SPY", "Invesco QQQ": "QQQ", "Vanguard Total": "VTI"},
        "Kripto": {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "Solana": "SOL-USD"}
    }

    records = []
    telegram_mesaji = "📊 *Kapsamlı Piyasa & Portföy Bülteni*\n"
    telegram_mesaji += f"🕒 _{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"

    now_utc = datetime.utcnow()
    tarih_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

    for kategori, varliklar in portfoy.items():
        telegram_mesaji += f"*{kategori}*\n"
        for isim, sembol in varliklar.items():
            try:
                hist = yf.Ticker(sembol, session=session).history(period="5d")
                if len(hist) >= 2:
                    bugun = float(hist['Close'].iloc[-1])
                    dun = float(hist['Close'].iloc[-2])
                    degisim = ((bugun - dun) / dun) * 100
                    ikon = "🟢" if degisim >= 0 else "🔴"
                    telegram_mesaji += f"  {ikon} {isim}: `{bugun:.2f}` ({degisim:+.2f}%)\n"

                    records.append({
                        "kategori": kategori,
                        "varlik_adi": isim,
                        "sembol": sembol,
                        "anlik_fiyat": round(bugun, 4),
                        "gunluk_degisim_yuzdesi": round(degisim, 2),
                        "cekilen_tarih": tarih_str,
                        "yil": str(now_utc.year),
                        "ay": f"{now_utc.month:02d}",
                        "gun": f"{now_utc.day:02d}"
                    })
            except Exception as e:
                print(f"Hata [{isim}]: {e}")
        telegram_mesaji += "\n"

    return records, telegram_mesaji

# ==========================================
# 3. LOAD: MEDALLION MIMARISI (BRONZE & SILVER)
# ==========================================
def save_to_medallion_lake(data, s3_client):
    if not data:
        return None

    now_utc = datetime.utcnow()
    yil = str(now_utc.year)
    ay = f"{now_utc.month:02d}"
    gun = f"{now_utc.day:02d}"
    timestamp_tag = now_utc.strftime("%Y%m%d_%H%M%S")

    # --- BRONZE (RAW) ---
    bronze_key = f"bronze/year={yil}/month={ay}/day={gun}/raw_market_{timestamp_tag}.json"
    jsonl_data = "\n".join([json.dumps(r, ensure_ascii=False) for r in data]) + "\n"
    s3_client.put_object(
        Bucket=BUCKET_NAME, Key=bronze_key,
        Body=jsonl_data.encode('utf-8'), ContentType='application/json'
    )
    print(f"✅ [Bronze/Raw] yüklendi: s3://{BUCKET_NAME}/{bronze_key}")

    # --- SILVER (CLEANED) ---
    df = pd.DataFrame(data)
    df['anlik_fiyat'] = df['anlik_fiyat'].astype(float)
    df['gunluk_degisim_yuzdesi'] = df['gunluk_degisim_yuzdesi'].astype(float)
    df['cekilen_tarih'] = pd.to_datetime(df['cekilen_tarih'])

    silver_key = f"silver/yil={yil}/ay={ay}/gun={gun}/market_{timestamp_tag}.parquet"
    parquet_buffer = io.BytesIO()
    cols_to_save = ['kategori', 'varlik_adi', 'sembol', 'anlik_fiyat', 'gunluk_degisim_yuzdesi', 'cekilen_tarih']
    df[cols_to_save].to_parquet(parquet_buffer, engine='pyarrow', compression='snappy', index=False)

    s3_client.put_object(
        Bucket=BUCKET_NAME, Key=silver_key,
        Body=parquet_buffer.getvalue(), ContentType='application/octet-stream'
    )
    print(f"✅ [Silver/Parquet] yüklendi: s3://{BUCKET_NAME}/{silver_key}")

    return df

# ==========================================
# 4. GOLD KATMANI (ANALYTICS & AGGREGATIONS)
# ==========================================
def generate_and_save_gold_layer(df_silver, s3_client):
    if df_silver is None or df_silver.empty:
        return

    print("Gold analitik metrikleri (7D SMA) hesaplanıyor...")
    now_utc = datetime.utcnow()
    yil = str(now_utc.year)
    ay = f"{now_utc.month:02d}"
    gun = f"{now_utc.day:02d}"
    timestamp_tag = now_utc.strftime("%Y%m%d_%H%M%S")

    gold_records = []
    # Her varlık için analitik metrik hesapla
    for sembol, grup in df_silver.groupby('sembol'):
        anlik = grup['anlik_fiyat'].iloc[-1]
        
        # Yahoo Finance'ten son 7 günlük kapanışları alarak gerçek 7D SMA hesaplayalım
        try:
            ticker = yf.Ticker(sembol)
            hist7 = ticker.history(period="7d")['Close']
            sma_7 = float(hist7.mean()) if not hist7.empty else anlik
        except Exception:
            sma_7 = anlik

        sapma = ((anlik - sma_7) / sma_7) * 100 if sma_7 > 0 else 0.0

        gold_records.append({
            "kategori": grup['kategori'].iloc[-1],
            "varlik_adi": grup['varlik_adi'].iloc[-1],
            "sembol": sembol,
            "anlik_fiyat": round(anlik, 4),
            "sma_7": round(sma_7, 4),
            "sma_7_sapma_yuzdesi": round(sapma, 2),
            "hesaplama_tarihi": pd.to_datetime(now_utc.strftime("%Y-%m-%d %H:%M:%S"))
        })

    df_gold = pd.DataFrame(gold_records)
    gold_key = f"gold/yil={yil}/ay={ay}/gun={gun}/gold_analytics_{timestamp_tag}.parquet"
    
    parquet_buffer = io.BytesIO()
    df_gold.to_parquet(parquet_buffer, engine='pyarrow', compression='snappy', index=False)

    s3_client.put_object(
        Bucket=BUCKET_NAME, Key=gold_key,
        Body=parquet_buffer.getvalue(), ContentType='application/octet-stream'
    )
    print(f"✅ [Gold/Analytics] yüklendi: s3://{BUCKET_NAME}/{gold_key}")

# ==========================================
# 5. ATHENA PARTITION ONARIMI
# ==========================================
def repair_athena_partitions():
    print("Athena partition tabloları güncelleniyor...")
    athena_client = boto3.client(
        'athena',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=REGION_NAME
    )
    # Hem Silver hem Gold tablosunu onar
    for table in ["silver_gunluk_fiyatlar", "gold_gunluk_metrikler"]:
        try:
            athena_client.start_query_execution(
                QueryString=f"MSCK REPAIR TABLE {table};",
                QueryExecutionContext={'Database': 'piyasa_verileri'},
                ResultConfiguration={'OutputLocation': f"s3://{BUCKET_NAME}/athena-sonuclari/"},
                WorkGroup='primary'
            )
            print(f"✅ Athena MSCK REPAIR başlatıldı: {table}")
        except Exception as e:
            print(f"⚠️️ {table} partition onarım uyarısı: {e}")

# ==========================================
# 6. TELEGRAM BİLDİRİMİ
# ==========================================
def notify_telegram(mesaj):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"})

# ==========================================
# 7. ANA ÇALIŞTIRMA BLOĞU
# ==========================================
if __name__ == "__main__":
    records, mesaj = fetch_market_data()
    s3 = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=REGION_NAME
    )
    df_silver = save_to_medallion_lake(records, s3)
    generate_and_save_gold_layer(df_silver, s3)
    repair_athena_partitions()
    notify_telegram(mesaj)