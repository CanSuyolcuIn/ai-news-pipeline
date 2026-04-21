"""
Deduplication scripti.
- Aynı URL'i siler
- Başlık benzerliği yüksek olanları siler (farklı dil versiyonları vb.)
- Tarih filtresi: son 72 saatin dışındakileri atar

Kullanım:
    python dedup.py
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INDEX_PATH = os.path.join(DATA_DIR, "published_index.json")
HOURS_BACK = 168  # Son 7 günün verisi
INDEX_MAX_DAYS = 30
SIMILARITY_THRESHOLD = 0.55
SUBSET_CONTAINMENT_RATIO = 0.9  # Kısa başlık uzun başlığın %90'ında geçiyorsa duplicate
SUBSET_MIN_WORDS = 3            # Daha az kelimeli başlıklara containment uygulanmaz


def load_published_index() -> dict[str, str]:
    if not os.path.exists(INDEX_PATH):
        return {}
    with open(INDEX_PATH, encoding="utf-8") as f:
        index: dict[str, str] = json.load(f)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=INDEX_MAX_DAYS)).strftime("%Y-%m-%d")
    return {url: date for url, date in index.items() if date >= cutoff}


def load_latest():
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, date_str, "results.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f), date_str


def normalize_title(title: str) -> str:
    """Başlığı karşılaştırma için normalize et."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)   # noktalama kaldır
    title = re.sub(r"\s+", " ", title).strip()
    return title


def normalize_url(url: str) -> str:
    """URL'den locale prefix ve query string'i temizle."""
    # openai.com/so-DJ/index/... → openai.com/index/...
    url = re.sub(r"(openai\.com)/[a-z]{2}-[A-Z]{2,4}/", r"\1/", url)
    url = re.sub(r"(openai\.com)/[a-z]{2,5}/", r"\1/", url)
    # query string temizle
    url = url.split("?")[0].split("#")[0]
    # trailing slash normalize
    url = url.rstrip("/")
    # http → https
    url = url.replace("http://", "https://")
    return url


def jaccard_similarity(a: str, b: str) -> float:
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def is_title_subset(a: str, b: str) -> bool:
    """Kısa başlığın kelimeleri uzun başlığın SUBSET_CONTAINMENT_RATIO oranında geçiyorsa True."""
    set_a = set(a.split())
    set_b = set(b.split())
    shorter, longer = (set_a, set_b) if len(set_a) <= len(set_b) else (set_b, set_a)
    if len(shorter) < SUBSET_MIN_WORDS:
        return False
    return len(shorter & longer) / len(shorter) >= SUBSET_CONTAINMENT_RATIO


def is_recent(item: dict, hours_back: int) -> bool:
    """Son N saatte yayınlanmış mı?"""
    pub = item.get("published", "")
    if not pub:
        return True  # Tarih yoksa dahil et

    # Exa tarihleri ISO format verir, RSS çeşitli formatlar
    pub_clean = pub.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%d"):
        try:
            dt = datetime.strptime(pub_clean, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            return dt >= cutoff
        except ValueError:
            continue

    return False  # Parse edemedik, tarihi belirsiz → dışarıda bırak


def dedup(items: list[dict], published_index: dict[str, str]) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    result = []
    cross_day_skipped = 0

    for item in items:
        # 1. Tarih filtresi
        if not is_recent(item, HOURS_BACK):
            continue

        # 2. URL dedup (aynı çalıştırma içi)
        norm_url = normalize_url(item.get("url", ""))
        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)

        # 3. Cross-day dedup (önceki günlerde zaten yayınlandı mı?)
        if norm_url in published_index:
            cross_day_skipped += 1
            continue

        # 4. Başlık benzerliği dedup
        norm_title = normalize_title(item.get("title", ""))
        is_duplicate = False
        for seen in seen_titles:
            if (jaccard_similarity(norm_title, seen) >= SIMILARITY_THRESHOLD
                    or is_title_subset(norm_title, seen)):
                is_duplicate = True
                break

        if is_duplicate:
            continue

        seen_titles.append(norm_title)
        result.append(item)

    if cross_day_skipped:
        print(f"  Cross-day dedup: {cross_day_skipped} URL daha önce yayınlandı, atlandı")

    return result


def main():
    print("\n=== Deduplication başladı ===\n")

    items, date_str = load_latest()
    print(f"  Ham kayıt sayısı: {len(items)}")

    published_index = load_published_index()
    print(f"  Published index: {len(published_index)} URL (son {INDEX_MAX_DAYS} gün)")

    cleaned = dedup(items, published_index)
    print(f"  Temizlenen kayıt sayısı: {len(cleaned)}")
    print(f"  Çıkarılan: {len(items) - len(cleaned)}")

    out_path = os.path.join(DATA_DIR, date_str, "deduped.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"\n  -> Kaydedildi: {out_path}")


if __name__ == "__main__":
    main()
