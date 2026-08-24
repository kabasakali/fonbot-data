# -*- coding: utf-8 -*-
"""
TEFAS Fon Detay ve Dagilim Cekici
GitHub Actions tarafindan her gun calistirilir.
"""
import json
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tefas import Crawler
import time

CSV_YOLU = "accessible_alpha_funds.csv"
CIKTI_YOLU = "portfoy_cache.json"

dagilim_map = {
    "stock": "Hisse Senetleri",
    "gov_bond": "Devlet Tahvili",
    "private_sector_bond": "Özel Sektör Borc. Aracı",
    "eurobond": "Eurobond",
    "currency": "Yabancı Para/Döviz",
    "gold": "Altın/Emtia",
    "real_estate": "Gayrimenkul",
    "fund": "Fon Sepeti",
    "repo": "Repo",
    "foreign_equity": "Yabancı Hisse",
    "foreign_debt": "Yabancı Borc. Aracı",
    "other": "Diğer"
}

def main():
    print("Portfoy dagilimlari cekiliyor...")
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
                    risk = str(int(satir.get("risk_value", 0))) if pd.notna(satir.get("risk_value")) else ""
                    tarih_str = str(satir.get("date", ""))[:10]
                    
                    dagilim = {}
                    for kolon, etiket in dagilim_map.items():
                        if kolon in df.columns:
                            deger = satir.get(kolon)
                            if pd.notna(deger) and float(deger) > 0.001:
                                dagilim[etiket] = round(float(deger), 2)
                                
                    return kod, {
                        "fon_adi": fon_adi,
                        "risk_degeri": risk,
                        "portfoy": {
                            "tarih": tarih_str,
                            "dagilim": dagilim
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
