"""
fetch_valor.py - TEFAS'tan fon valör bilgilerini çeker.

Strateji:
1. TEFAS FonAnaliz sayfasını çek (GitHub Actions IP'si kara listede değil)
2. BeautifulSoup ile hem statik HTML'den hem de script bloklarından ara
3. 0 gelirse regex ile raw HTML içinde "T+" formatında ara
4. Hepsi başarısız olursa makul varsayılan (T+1 alis, T+1 satis) kullan
"""

import requests
import json
import re
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

CSV_YOLU = "accessible_alpha_funds.csv"
CIKTI_YOLU = "valor_cache.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
    "Referer": "https://www.tefas.gov.tr/",
}

# Bilinen gerçek valör değerleri - TEFAS izahnamesinden manuel derlendi
# fetch başarısız olursa bu değerler kullanılır
BILINEN_VALORLER = {
    "PPZ": {"alis": 0, "satis": 0},  # Para piyasası - aynı gün
    # Varsayılan: T+1/T+1
}
VARSAYILAN = {"alis": 1, "satis": 1}


def parse_valor_from_html(html_text: str, fon_kodu: str):
    """HTML içinden valör değerlerini birden fazla yöntemle çıkarmaya çalışır."""
    alis_valoru = None
    satis_valoru = None

    soup = BeautifulSoup(html_text, "html.parser")

    # --- Yöntem 1: span string eşleşmesi (eski yöntem) ---
    for label, attr in [
        ("Fon Alış Valörü", "alis"),
        ("Fon Satış Valörü", "satis"),
        ("Alış Valörü", "alis"),
        ("Satış Valörü", "satis"),
    ]:
        span = soup.find("span", string=re.compile(label, re.IGNORECASE))
        if span:
            sib = span.find_next_sibling("span")
            if not sib:
                sib = span.parent.find_next_sibling()
            if sib:
                txt = sib.get_text(strip=True).replace("T+", "").replace("T", "")
                try:
                    val = int(txt)
                    if attr == "alis" and alis_valoru is None:
                        alis_valoru = val
                    elif attr == "satis" and satis_valoru is None:
                        satis_valoru = val
                except:
                    pass

    # --- Yöntem 2: li / dt / dd etiketlerinde ara ---
    if alis_valoru is None or satis_valoru is None:
        for tag in soup.find_all(["li", "dt", "th", "td", "div"]):
            txt = tag.get_text(" ", strip=True)
            if "Alış Valörü" in txt or "Alis Valoru" in txt:
                # Yanındaki değeri bul
                m = re.search(r"T\+(\d+)", txt)
                if m and alis_valoru is None:
                    alis_valoru = int(m.group(1))
                else:
                    next_el = tag.find_next_sibling()
                    if next_el:
                        m = re.search(r"T\+(\d+)", next_el.get_text())
                        if m and alis_valoru is None:
                            alis_valoru = int(m.group(1))
            if "Satış Valörü" in txt or "Satis Valoru" in txt:
                m = re.search(r"T\+(\d+)", txt)
                if m and satis_valoru is None:
                    satis_valoru = int(m.group(1))
                else:
                    next_el = tag.find_next_sibling()
                    if next_el:
                        m = re.search(r"T\+(\d+)", next_el.get_text())
                        if m and satis_valoru is None:
                            satis_valoru = int(m.group(1))

    # --- Yöntem 3: Ham regex ile tüm HTML'de T+ örüntüsü ---
    if alis_valoru is None:
        # JSON veri bloğu içinde "alisValor" veya "alisValoru" gibi alanlar olabilir
        m = re.search(r'"alisVal[oö]r[u]?"\s*:\s*(\d+)', html_text, re.IGNORECASE)
        if m:
            alis_valoru = int(m.group(1))

    if satis_valoru is None:
        m = re.search(r'"satisVal[oö]r[u]?"\s*:\s*(\d+)', html_text, re.IGNORECASE)
        if m:
            satis_valoru = int(m.group(1))

    return alis_valoru, satis_valoru


def fetch_valor(fon_kodu: str):
    """Bir fonun TEFAS'tan alış ve satış valörlerini çeker."""
    # Bilinen özel değerler
    if fon_kodu in BILINEN_VALORLER:
        return fon_kodu, BILINEN_VALORLER[fon_kodu]

    url = "https://www.tefas.gov.tr/FonAnaliz.aspx"
    
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                params={"FonKod": fon_kodu},
                headers=HEADERS,
                timeout=20,
            )
            
            # WAF bloğu kontrolü
            if "Request Rejected" in resp.text or resp.status_code != 200:
                print(f"  [WARN] {fon_kodu}: WAF veya HTTP {resp.status_code}")
                time.sleep(2)
                continue

            alis, satis = parse_valor_from_html(resp.text, fon_kodu)

            # Başarılı parse
            if alis is not None and satis is not None:
                return fon_kodu, {"alis": alis, "satis": satis}

            # Kısmi parse - en azından birini bulduk
            if alis is not None or satis is not None:
                result = {
                    "alis": alis if alis is not None else VARSAYILAN["alis"],
                    "satis": satis if satis is not None else VARSAYILAN["satis"],
                }
                print(f"  [PARTIAL] {fon_kodu}: alis={result['alis']}, satis={result['satis']}")
                return fon_kodu, result

            # Hiç bulunamadı - bir sonraki denemede biraz bekle
            print(f"  [MISS] {fon_kodu}: Etiket bulunamadi, deneme {attempt+1}/3")
            time.sleep(1.5)

        except Exception as e:
            print(f"  [ERR] {fon_kodu} deneme {attempt+1}: {e}")
            time.sleep(2)

    # Tüm denemeler başarısız → varsayılan
    print(f"  [DEFAULT] {fon_kodu}: Varsayilan deger kullanildi (T+1/T+1)")
    return fon_kodu, dict(VARSAYILAN)


def main():
    print("Fon kodlari okunuyor...")
    df_evren = pd.read_csv(CSV_YOLU)
    if "code" in df_evren.columns:
        kodlar = df_evren["code"].dropna().unique().tolist()
    else:
        kodlar = df_evren.iloc[:, 0].dropna().unique().tolist()

    kodlar = list(set(str(k).strip().upper() for k in kodlar))
    if "PPZ" not in kodlar:
        kodlar.append("PPZ")

    print(f"Toplam {len(kodlar)} fon icin valor bilgisi cekilecek...")

    # Mevcut cache varsa yükle (başarısız olanları tekrar dene, başarılıları koru)
    try:
        with open(CIKTI_YOLU, "r", encoding="utf-8") as f:
            mevcut = json.load(f)
        # Sadece 0/0 olan veya eksik olanları yeniden çek
        kodlar_cek = [
            k for k in kodlar
            if k not in mevcut
            or (mevcut[k].get("alis", 0) == 0 and mevcut[k].get("satis", 0) == 0
                and k not in BILINEN_VALORLER)
        ]
        print(f"Mevcut cache: {len(mevcut)} fon. Yeniden cekilecek: {len(kodlar_cek)} fon (eksik veya sifir)")
    except Exception:
        mevcut = {}
        kodlar_cek = kodlar
        print("Cache bulunamadi, tumu cekilecek.")

    sonuclar = dict(mevcut)

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_valor, k): k for k in kodlar_cek}
        done = 0
        for fut in as_completed(futures):
            kod, data = fut.result()
            sonuclar[kod] = data
            done += 1
            if done % 20 == 0:
                print(f"  İlerleme: {done}/{len(kodlar_cek)}")

    # Sıfır kalan fonlar için varsayılan uygula
    sifir_sayisi = 0
    for k in list(sonuclar.keys()):
        if k in BILINEN_VALORLER:
            continue  # PPZ gibi gerçekten T+0 olanlar
        if sonuclar[k].get("alis", 0) == 0:
            sonuclar[k]["alis"] = VARSAYILAN["alis"]
            sifir_sayisi += 1
        if sonuclar[k].get("satis", 0) == 0:
            sonuclar[k]["satis"] = VARSAYILAN["satis"]

    with open(CIKTI_YOLU, "w", encoding="utf-8") as f:
        json.dump(sonuclar, f, indent=4, ensure_ascii=False)

    print(f"\nTamamlandi!")
    print(f"  Toplam fon: {len(sonuclar)}")
    print(f"  Varsayilan deger uygulanan: {sifir_sayisi}")
    print(f"  Cikti: {CIKTI_YOLU}")

    # Ozet istatistik
    t0 = sum(1 for v in sonuclar.values() if v["alis"] == 0)
    t1 = sum(1 for v in sonuclar.values() if v["alis"] == 1)
    t2 = sum(1 for v in sonuclar.values() if v["alis"] == 2)
    print(f"\n  Alis valör dagilimi: T+0={t0}, T+1={t1}, T+2={t2}")


if __name__ == "__main__":
    main()
