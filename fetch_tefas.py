# -*- coding: utf-8 -*-
"""
TEFAS Veri Cekici - GitHub Actions tarafindan calistirilir.
Son 130 gunluk fiyatlari 156 fon icin ceker, JSON olarak kaydeder.
"""
import json
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tefas import Crawler

GUN_SAYISI = 130
CSV_YOLU = "accessible_alpha_funds.csv"
CIKTI_YOLU = "fiyat_cache.json"

def main():
    print(f"[{datetime.datetime.now()}] Basliyor...")

    # Fon listesini oku
    df_evren = pd.read_csv(CSV_YOLU)
    if "code" in df_evren.columns:
        kodlar = df_evren["code"].dropna().unique().tolist()
    elif "Fon Kodu" in df_evren.columns:
        kodlar = df_evren["Fon Kodu"].dropna().unique().tolist()
    else:
        kodlar = df_evren.iloc[:, 0].dropna().unique().tolist()

    kodlar = list(set(kodlar))
    if "PPZ" not in kodlar:
        kodlar.append("PPZ")

    print(f"Toplam fon: {len(kodlar)}")

    crawler = Crawler(fund_limit=2000)
    bitis = datetime.datetime.now()
    baslangic = bitis - datetime.timedelta(days=GUN_SAYISI)
    bas_str = baslangic.strftime("%Y-%m-%d")
    bit_str = bitis.strftime("%Y-%m-%d")

    def fetch_one(kod):
        try:
            df = crawler.fetch(start=bas_str, end=bit_str, name=kod)
            if df is not None and not df.empty:
                df = df.sort_values("date")
                rows = []
                for _, row in df.iterrows():
                    rows.append({
                        "date": str(row["date"])[:10],
                        "price": float(row["price"])
                    })
                return kod, rows
        except Exception as e:
            print(f"  HATA {kod}: {e}")
        return kod, None

    sonuclar = {}
    basarili = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(fetch_one, k): k for k in kodlar}
        for fut in as_completed(futures, timeout=300):
            kod, rows = fut.result()
            if rows:
                sonuclar[kod] = rows
                basarili += 1

    print(f"Basarili: {basarili}/{len(kodlar)} fon")

    meta = {
        "guncelleme_zamani": datetime.datetime.now().isoformat(),
        "guncelleme_tarihi": datetime.datetime.now().strftime("%Y-%m-%d"),
        "fon_sayisi": basarili
    }

    with open(CIKTI_YOLU, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "veriler": sonuclar}, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Kaydedildi: {CIKTI_YOLU} ({basarili} fon)")

if __name__ == "__main__":
    main()
