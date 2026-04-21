"""
3 günlük veri toplama scripti.
Amaç: Hangi RSS kaynakları ve Exa sorguları sonuç veriyor, hangisi boş geliyor?

Çalıştırma:
    pip install feedparser exa-py pyyaml
    python fetch.py

Her çalıştırmada temp/data/YYYY-MM-DD/ klasörüne JSON kaydeder.
"""

import json
import os
import feedparser
import yaml
from datetime import datetime, timezone, timedelta
from exa_py import Exa
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# --- Konfigürasyon ---
EXA_API_KEY = os.environ.get("EXA_API_KEY", "")
SOURCES_FILE = os.path.join(os.path.dirname(__file__), "sources.yaml")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HOURS_BACK = 168  # Son 7 günün verisi


def load_sources():
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def today_dir():
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, date_str)
    os.makedirs(path, exist_ok=True)
    return path


def is_recent(entry, hours_back):
    """Son N saatte yayınlanmış mı?"""
    for field in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field, None)
        if t:
            pub = datetime(*t[:6], tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            return pub >= cutoff
    return True  # Tarih yoksa dahil et


def fetch_rss(feeds):
    results = []
    stats = []

    for feed in feeds:
        name = feed["name"]
        url = feed["url"]
        category = feed.get("category", "")

        try:
            headers = feed.get("headers", {})
            parsed = feedparser.parse(url, request_headers=headers)
            entries = [e for e in parsed.entries if is_recent(e, HOURS_BACK)]

            for e in entries:
                results.append({
                    "source": name,
                    "source_type": "rss",
                    "category": category,
                    "title": e.get("title", ""),
                    "url": e.get("link", ""),
                    "snippet": e.get("summary", "")[:300],
                    "published": str(e.get("published", "")),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })

            stats.append({
                "source": name,
                "url": url,
                "fetched": len(entries),
                "status": "ok" if len(entries) > 0 else "empty",
            })
            print(f"  [RSS] {name}: {len(entries)} kayıt")

        except Exception as ex:
            stats.append({"source": name, "url": url, "fetched": 0, "status": f"error: {ex}"})
            print(f"  [RSS] {name}: HATA — {ex}")

    return results, stats


EXA_CATEGORY_MAP = {
    "model": "news",
    "framework": "news",
    "altyapi": "news",
    "github": None,           # genel web, category yok
    "x_twitter": None,        # genel web, category yok
    "akademik": "research paper",
}


def fetch_exa(queries):
    if not EXA_API_KEY:
        print("  [EXA] EXA_API_KEY bulunamadı, atlanıyor.")
        return [], []

    exa = Exa(api_key=EXA_API_KEY)
    results = []
    stats = []

    for q in queries:
        query = q["query"]
        category = q.get("category", "")
        exa_category = EXA_CATEGORY_MAP.get(category)

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
            kwargs = {
                "num_results": 30,
                "type": "auto",
                "start_published_date": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "highlights": {"max_characters": 400},
            }
            if exa_category:
                kwargs["category"] = exa_category

            response = exa.search_and_contents(query, **kwargs)
            items = response.results if hasattr(response, "results") else []

            for item in items:
                highlight = ""
                if hasattr(item, "highlights") and item.highlights:
                    highlight = " ".join(item.highlights)[:400]

                results.append({
                    "source": "exa",
                    "source_type": "exa",
                    "category": category,
                    "keyword": query,
                    "title": item.title or "",
                    "url": item.url or "",
                    "snippet": highlight,
                    "published": str(getattr(item, "published_date", "")),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })

            no_date_count = sum(1 for i in items if not getattr(i, "published_date", None))
            stats.append({
                "query": query,
                "category": category,
                "exa_category": exa_category,
                "fetched": len(items),
                "no_date": no_date_count,
                "status": "ok" if len(items) > 0 else "empty",
            })
            print(f"  [EXA] '{query}': {len(items)} kayıt")

        except Exception as ex:
            stats.append({"query": query, "category": category, "fetched": 0, "status": f"error: {ex}"})
            print(f"  [EXA] '{query}': HATA — {ex}")

    return results, stats


def save(out_dir, filename, data):
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> Kaydedildi: {path}")


def main():
    print(f"\n=== Fetch başladı: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

    sources = load_sources()
    out_dir = today_dir()

    # RSS
    print("--- RSS Kaynakları ---")
    rss_results, rss_stats = fetch_rss(sources.get("rss_feeds", []))

    # Exa
    print("\n--- Exa.ai Sorguları ---")
    exa_results, exa_stats = fetch_exa(sources.get("exa_queries", []))

    # Tüm sonuçları birleştir
    all_results = rss_results + exa_results

    # Kaydet
    print("\n--- Kayıt ---")
    save(out_dir, "results.json", all_results)
    save(out_dir, "rss_stats.json", rss_stats)
    save(out_dir, "exa_stats.json", exa_stats)

    # Özet
    print(f"\n=== Özet ===")
    print(f"  RSS toplam: {len(rss_results)} kayıt")
    print(f"  Exa toplam: {len(exa_results)} kayıt")
    print(f"  Genel toplam: {len(all_results)} kayıt")

    empty_rss = [s["source"] for s in rss_stats if s["fetched"] == 0]
    empty_exa = [s["query"] for s in exa_stats if s["fetched"] == 0]

    if empty_rss:
        print(f"\n  Boş gelen RSS kaynakları ({len(empty_rss)}):")
        for s in empty_rss:
            print(f"    - {s}")

    if empty_exa:
        print(f"\n  Boş gelen Exa sorguları ({len(empty_exa)}):")
        for q in empty_exa:
            print(f"    - {q}")


if __name__ == "__main__":
    main()
