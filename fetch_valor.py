import requests
import json
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

CSV_YOLU = "accessible_alpha_funds.csv"
CIKTI_YOLU = "valor_cache.json"

def main():
    print("Fon kodlari okunuyor...")
    df_evren = pd.read_csv(CSV_YOLU)
    if "code" in df_evren.columns:
        kodlar = df_evren["code"].dropna().unique().tolist()
    else:
        kodlar = df_evren.iloc[:, 0].dropna().unique().tolist()
        
    kodlar = list(set(kodlar))
    if "PPZ" not in kodlar: kodlar.append("PPZ")

    print(f"Toplam {len(kodlar)} fon icin valor bilgisi cekilecek...")

    def fetch_valor(fon_kodu):
        for _ in range(3):
            try:
                url = "https://www.tefas.gov.tr/FonAnaliz.aspx"
                resp = requests.get(url, params={"FonKod": fon_kodu}, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, "html.parser")
                    
                    # Alis Valoru
                    alis_li = soup.find("span", string="Fon Alış Valörü")
                    alis_valoru = 0
                    if alis_li:
                        span = alis_li.find_next_sibling("span")
                        if span:
                            val_str = span.text.strip().replace("T+", "")
                            try: alis_valoru = int(val_str)
                            except: pass
                            
                    # Satis Valoru
                    satis_li = soup.find("span", string="Fon Satış Valörü")
                    satis_valoru = 0
                    if satis_li:
                        span = satis_li.find_next_sibling("span")
                        if span:
                            val_str = span.text.strip().replace("T+", "")
                            try: satis_valoru = int(val_str)
                            except: pass
                            
                    return fon_kodu, {"alis": alis_valoru, "satis": satis_valoru}
            except Exception:
                time.sleep(1)
        return fon_kodu, {"alis": 1, "satis": 2}

    sonuclar = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_valor, k): k for k in kodlar}
        for fut in as_completed(futures):
            kod, data = fut.result()
            sonuclar[kod] = data

    with open(CIKTI_YOLU, "w", encoding="utf-8") as f:
        json.dump(sonuclar, f, indent=4)
        
    print(f"\nValor bilgileri {CIKTI_YOLU} dosyasina kaydedildi.")

if __name__ == "__main__":
    main()
