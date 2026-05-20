"""
LLM filtreleme scripti.
deduped.json'u okur, başlıkları batch'ler halinde LLM'e gönderir,
KEEP olanları output.json'a yazar.

Kullanım:
    python filter.py

Gerekli env:
    OPENROUTER_API_KEY  (openrouter.ai API key)
"""

import json
import os
import re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INDEX_PATH = os.path.join(os.path.dirname(__file__), "published_index.json")
TITLES_PATH = os.path.join(os.path.dirname(__file__), "published_titles.json")
MAX_HISTORY_RUNS = 10

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = os.environ.get("LLM_MODEL", "minimax/minimax-01")

BATCH_SIZE = 50  # tek seferde kaç başlık gönderilsin

def _normalize_url(url: str) -> str:
    url = re.sub(r"(openai\.com)/[a-z]{2}-[A-Z]{2,4}/", r"\1/", url)
    url = re.sub(r"(openai\.com)/[a-z]{2,5}/", r"\1/", url)
    url = url.split("?")[0].split("#")[0]
    url = url.rstrip("/")
    return url.replace("http://", "https://")


def compute_source_stats(
    items: list[dict], keep_indices: list[int]
) -> list[dict]:
    keep_set = set(keep_indices)
    totals: dict[str, dict] = {}

    for i, item in enumerate(items):
        source = item.get("source", "unknown")
        stype = item.get("source_type", "unknown")
        if source not in totals:
            totals[source] = {"source": source, "source_type": stype, "total": 0, "kept": 0}
        totals[source]["total"] += 1
        if i in keep_set:
            totals[source]["kept"] += 1

    stats = []
    for s in totals.values():
        s["keep_rate"] = round(s["kept"] / s["total"], 2) if s["total"] else 0.0
        stats.append(s)

    return sorted(stats, key=lambda x: -x["keep_rate"])


def save_source_stats(stats: list[dict], date_str: str) -> None:
    path = os.path.join(DATA_DIR, date_str, "source_stats.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  -> Kaynak istatistikleri: {path}")


def update_source_quality(stats: list[dict], date_str: str) -> None:
    quality_path = os.path.join(DATA_DIR, "source_quality.json")
    if os.path.exists(quality_path):
        with open(quality_path, encoding="utf-8") as f:
            quality: dict[str, dict] = json.load(f)
    else:
        quality = {}

    for s in stats:
        source = s["source"]
        if source not in quality:
            quality[source] = {
                "source": source,
                "source_type": s["source_type"],
                "runs": 0,
                "total": 0,
                "kept": 0,
            }
        quality[source]["runs"] += 1
        quality[source]["total"] += s["total"]
        quality[source]["kept"] += s["kept"]

    for q in quality.values():
        q["keep_rate"] = round(q["kept"] / q["total"], 2) if q["total"] else 0.0
        q["last_run"] = date_str

    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(quality, f, ensure_ascii=False, indent=2)
    print(f"  -> Kümülatif kaynak kalitesi: {quality_path}")


def print_source_table(stats: list[dict]) -> None:
    print("\n  Kaynak KEEP oranları:")
    print(f"  {'Kaynak':<40} {'Tür':<5} {'Toplam':>6} {'KEEP':>5} {'Oran':>6}")
    print("  " + "-" * 66)
    for s in stats:
        print(
            f"  {s['source']:<40} {s['source_type']:<5} "
            f"{s['total']:>6} {s['kept']:>5} {s['keep_rate']:>5.0%}"
        )


def load_published_titles() -> list[str]:
    """Son MAX_HISTORY_RUNS bültenin başlıklarını düz liste olarak döndürür."""
    if not os.path.exists(TITLES_PATH):
        return []
    with open(TITLES_PATH, encoding="utf-8") as f:
        data: dict[str, list[str]] = json.load(f)
    # Tarihe göre sırala, son MAX_HISTORY_RUNS runı al
    sorted_dates = sorted(data.keys(), reverse=True)[:MAX_HISTORY_RUNS]
    titles: list[str] = []
    for date in sorted_dates:
        titles.extend(data[date])
    return titles


def update_published_titles(kept: list[dict], date_str: str) -> None:
    """Bu run'ın başlıklarını published_titles.json'a ekler, MAX_HISTORY_RUNS'u aşanları siler."""
    if os.path.exists(TITLES_PATH):
        with open(TITLES_PATH, encoding="utf-8") as f:
            data: dict[str, list[str]] = json.load(f)
    else:
        data = {}

    data[date_str] = [item.get("title", "") for item in kept if item.get("title")]

    # MAX_HISTORY_RUNS'u aşan eski kayıtları temizle
    sorted_dates = sorted(data.keys(), reverse=True)
    for old_date in sorted_dates[MAX_HISTORY_RUNS:]:
        del data[old_date]

    with open(TITLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> Published titles güncellendi: {len(data[date_str])} başlık kaydedildi ({len(data)} run saklanıyor)")


CROSS_RUN_DEDUP_PROMPT = """Asagida iki liste var:

ONCEKI BULTENLER (son {run_count} bülten, toplamda {title_count} haber):
{prev_titles}

BUGUNUN ADAYLARI:
{new_items}

Kural: Bugunun adaylarindan, onceki bultenlerde zaten kapsanmis bir konuyu veya duyuruyu ele alanlari SKIP et.
Yeni bir guncelleme, yeni bir versiyon veya farkli bir urun ise KEEP et.

Ornek: Onceki bultende "DeepSeek-V4 piyasaya suruldu" varsa, yeni "DeepSeek-V4 analizi" → SKIP.
Ama "DeepSeek-V4.1 released" → KEEP (farkli surum).

SADECE su JSON formatinda yanit ver, baska hicbir sey yazma:
{{"keep": [0, 2, 4]}}"""


def cross_run_topic_dedup(client: OpenAI, items: list[dict]) -> list[dict]:
    """Önceki bültenlerle konu örtüşmesini LLM ile kontrol eder."""
    if not items:
        return items

    prev_titles = load_published_titles()
    if not prev_titles:
        print("  Cross-run dedup: geçmiş bulunamadı, atlanıyor.")
        return items

    prev_lines = "\n".join(f"- {t}" for t in prev_titles)
    new_lines = "\n".join(f"{i}: {item.get('title', '')}" for i, item in enumerate(items))

    prompt = CROSS_RUN_DEDUP_PROMPT.format(
        run_count=min(MAX_HISTORY_RUNS, len(prev_titles) // max(1, len(prev_titles) // MAX_HISTORY_RUNS)),
        title_count=len(prev_titles),
        prev_titles=prev_lines,
        new_items=new_lines,
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=1000,
    )

    raw = (response.choices[0].message.content or "").strip()
    match = re.search(r'\{.*?"keep".*?\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        parsed = json.loads(raw)
        keep_local = parsed.get("keep", [])
        result = [items[i] for i in keep_local if i < len(items)]
        skipped = len(items) - len(result)
        print(f"  Cross-run dedup: {skipped} haber önceki bültenle örtüştü, atlandı → {len(result)} kaldı")
        return result
    except (json.JSONDecodeError, IndexError):
        print(f"  [UYARI] Cross-run dedup parse hatası, liste korunuyor: {raw[:100]}")
        return items


def update_published_index(kept: list[dict], date_str: str) -> None:
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as f:
            index: dict[str, str] = json.load(f)
    else:
        index = {}

    added = 0
    for item in kept:
        norm_url = _normalize_url(item.get("url", ""))
        if norm_url and norm_url not in index:
            index[norm_url] = date_str
            added += 1

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"  -> Published index güncellendi: +{added} yeni URL (toplam: {len(index)})")


def load_deduped():
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, date_str, "deduped.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f), date_str


PROMPT_TEMPLATE = """Asagidaki haber basliklarini incele.

Amac: SADECE gercekten piyasaya surulmus yeni AI modelleri, yeni API'lar ve yeni gelistirici araclari.

KEEP kriterleri — asagidakilerden BIRI yeterlİ:

A) Yeni model/API/arac surumu:
   Somut urun/model adi + surum sinyali (Introducing, Releases, Launches, Now available,
   Open-sourcing, Released, Announced, Debuts, Ships, Preview)
   Ornek: "Introducing GPT-Rosalind" → KEEP
   Ornek: "xAI Launches Grok Speech-to-Text API" → KEEP
   Ornek: "DeepSeek-V4: a million-token context" → KEEP

B) Yeni pratik teknik/yontem — gelistiricilerin hemen kullanabilecegi:
   Surum sinyali olmasa da olur, ama arxiv/paper/benchmark olmamali
   Ornek: "New prompting technique cuts hallucinations by 40%" → KEEP
   Ornek: "OpenAI releases new fine-tuning method for tool use" → KEEP
   Ornek: "Speculative decoding now available in vLLM" → KEEP

SKIP — asagidakilerden HERHANGI BIRI varsa SKIP:
- Arxiv makalesi, akademik paper, benchmark karsilastirmasi, leaderboard
- Is anlasması, ortaklik, tedarik sozlesmesi, donanim alimi ("signs deal", "partnership", "supply")
- Yatirim, funding, CEO degisikligi, sirket stratejisi, politika haberi
- Robotik, insansi robot, otonom arac
- Liste, siralama, rehber, tutorial, uygulama ornegi
- Genel yorum, analiz, fikir yazisi
- Kullanici deneyimi, uretkenlik haberi

Suphe duyuyorsan SKIP et.

Basliklar:
{titles}

SADECE su JSON formatinda yanit ver, baska hicbir sey yazma:
{{"keep": [0, 2, 4]}}"""


TOPIC_DEDUP_PROMPT = """Asagidaki haberler onceden filtrelenip secilmistir. Ancak bazi haberler ayni duyuruyu/modeli farkli kaynaklardan haber yapabilir.

Kural: Her bir benzersiz duyuru/model icin SADECE EN IYI 1 kaynak kalsin.
Kaynak tercih sirasi: resmi lab blogu (openai.com, anthropic.com, deepmind.google, huggingface.co/blog, developer.nvidia.com, aws.amazon.com) > teknik haber sitesi > genel haber sitesi

Ornek: Eger listede DeepSeek V4 hakkinda 4 farkli kaynak varsa, sadece en bilgilendirici/resmi 1 tanesini tut.

Haberler:
{items}

SADECE su JSON formatinda yanit ver, baska hicbir sey yazma:
{{"keep": [0, 2, 4]}}"""


def filter_batch(client: OpenAI, items: list[dict], offset: int) -> list[int]:
    """Bir batch'i LLM'e gönder, KEEP olan indeksleri döndür."""
    lines = []
    for i, item in enumerate(items):
        pub = item.get("published", "") or ""
        date_str = pub[:10] if pub else "tarih_yok"
        lines.append(f"{i}: [{date_str}] {item.get('title', '')}")

    prompt = PROMPT_TEMPLATE.format(titles="\n".join(lines))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=2000,
    )

    raw = (response.choices[0].message.content or "").strip()

    # JSON bloğu içinde olabilir, çıkart
    import re
    match = re.search(r'\{.*?"keep".*?\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        parsed = json.loads(raw)
        local_indices = parsed.get("keep", [])
        return [offset + i for i in local_indices]
    except json.JSONDecodeError:
        print(f"  [UYARI] JSON parse hatasi, ham yanit: {raw[:100]}")
        # Retry: max_tokens artirip tekrar dene
        try:
            response2 = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=4000,
            )
            raw2 = (response2.choices[0].message.content or "").strip()
            match2 = re.search(r'\{.*?"keep".*?\}', raw2, re.DOTALL)
            if match2:
                parsed2 = json.loads(match2.group(0))
                local_indices = parsed2.get("keep", [])
                print(f"  [RETRY basarili] KEEP: {len(local_indices)}")
                return [offset + i for i in local_indices]
        except Exception as e2:
            print(f"  [RETRY de basarisiz]: {e2}")
        return []


def topic_dedup(client: OpenAI, items: list[dict]) -> list[dict]:
    """Aynı konuyu farklı kaynaklardan işleyen makaleleri teke indirir."""
    if len(items) <= 1:
        return items

    lines = []
    for i, item in enumerate(items):
        lines.append(f"{i}: [{item.get('source', '')}] {item.get('title', '')}")

    prompt = TOPIC_DEDUP_PROMPT.format(items="\n".join(lines))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=1000,
    )

    raw = (response.choices[0].message.content or "").strip()
    match = re.search(r'\{.*?"keep".*?\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        parsed = json.loads(raw)
        keep_local = parsed.get("keep", [])
        result = [items[i] for i in keep_local if i < len(items)]
        print(f"  Topic dedup: {len(items)} → {len(result)} haber")
        return result
    except (json.JSONDecodeError, IndexError):
        print(f"  [UYARI] Topic dedup parse hatasi, ham liste korunuyor: {raw[:100]}")
        return items


def main():
    if not API_KEY:
        print("OPENROUTER_API_KEY bulunamadı. .env dosyasını kontrol et.")
        return

    print("\n=== Filtreleme başladı ===\n")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    items, date_str = load_deduped()
    print(f"  Gelen kayıt sayısı: {len(items)}")

    keep_indices = []
    total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(items))
        batch = items[start:end]

        print(f"  Batch {batch_num + 1}/{total_batches} ({len(batch)} kayıt)...")
        indices = filter_batch(client, batch, offset=start)
        keep_indices.extend(indices)
        print(f"    KEEP: {len(indices)}")

    kept = [items[i] for i in keep_indices]
    print(f"\n  Batch filtre sonrasi: {len(kept)} / {len(items)}")

    print("\n  Topic dedup uygulanıyor...")
    kept = topic_dedup(client, kept)

    print("\n  Cross-run topic dedup uygulanıyor...")
    kept = cross_run_topic_dedup(client, kept)

    print(f"\n  Toplam KEEP: {len(kept)} / {len(items)}")

    out_path = os.path.join(DATA_DIR, date_str, "output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    print(f"  -> Kaydedildi: {out_path}")
    update_published_index(kept, date_str)
    update_published_titles(kept, date_str)

    stats = compute_source_stats(items, keep_indices)
    print_source_table(stats)
    save_source_stats(stats, date_str)
    update_source_quality(stats, date_str)


if __name__ == "__main__":
    main()
