# -*- coding: utf-8 -*-
"""
TEFAS Fon Detay Cekici
GitHub Actions tarafindan her gun calistirilir.

NOT (2026-09): TEFAS eski uc noktalari (BindHistoryInfo / BindHistoryAllocation)
kapatildi. tefas-crawler 0.6.0+ yalnizca gunluk fiyat/unvan/kategori bilgisi
donuyor; portfoy dagilimi ve risk degeri artik TEFAS tarafinda yayinlanmiyor.

Geriye uyumluluk icin cikti semasi degistirilmedi: 'risk_degeri' ve
'portfoy.dagilim' alanlari bos birakilarak korunur. TEFAS bu verileri yeniden
yayinlamaya baslarsa (veya alternatif kaynak eklenirse) buraya eklenebilir.
"""
import json
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tefas import Crawler
import time

CSV_YOLU = "accessible_alpha_funds.csv"
CIKTI_YOLU = "portfoy_cache.json"

def main():
    print("Fon detaylari cekiliyor...")
    df_evren = pd.read_csv(CSV_YOLU)
    if "code" in df_evren.columns:
        kodlar = df_evren["code"].dropna().unique().tolist()
    else:
        kodlar = df_evren.iloc[:, 0].dropna().unique().tolist()

    kodlar = list(set(kodlar))
    if "PPZ" not in kodlar: kodlar.append("PPZ")

    crawler = Crawler(fund_limit=2000)
    bitis = datetime.datetime.now()
    baslangic = bitis - datetime.timedelta(days=30) # son 30 gune bak, en yeniyi al
    bas_str = baslangic.strftime("%Y-%m-%d")
    bit_str = bitis.strftime("%Y-%m-%d")

    def fetch_one(kod):
        for _ in range(3):
            try:
                df = crawler.fetch(start=bas_str, end=bit_str, name=kod)
                if df is not None and not df.empty:
                    df = df.sort_values("date", ascending=False)
                    satir = df.iloc[0]

                    fon_adi = str(satir.get("title", "")) if pd.notna(satir.get("title")) else ""
                    tarih_str = str(satir.get("date", ""))[:10]

                    # Portfoy dagilimi ve risk degeri yeni TEFAS API'sinde
                    # artik yayinlanmiyor; sema uyumu icin bos birakilir.
                    return kod, {
                        "fon_adi": fon_adi,
                        "risk_degeri": "",
                        "portfoy": {
                            "tarih": tarih_str,
                            "dagilim": {}
                        }
                    }
                return kod, None
            except Exception:
                time.sleep(1)
        return kod, None

    sonuclar = {}
    basarili = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_one, k): k for k in kodlar}
        for fut in as_completed(futures):
            kod, data = fut.result()
            if data:
                sonuclar[kod] = data
                basarili += 1

    print(f"Basarili: {basarili}/{len(kodlar)}")

    meta = {
        "guncelleme_zamani": datetime.datetime.now().isoformat(),
        "fon_sayisi": basarili
    }

    with open(CIKTI_YOLU, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "veriler": sonuclar}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
