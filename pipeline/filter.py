"""
LLM filtreleme scripti.
deduped.json'u okur, başlıkları batch'ler halinde LLM'e gönderir,
KEEP olanları output.json'a yazar.

Kullanım:
    python filter.py

Gerekli env:
    OPENCODE_API_KEY  (opencode.ai API key)
"""

import json
import os
import re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INDEX_PATH = os.path.join(DATA_DIR, "published_index.json")

API_KEY = os.environ.get("OPENCODE_API_KEY", "")
BASE_URL = "https://opencode.ai/zen/go/v1"
MODEL = "minimax-m2.5"

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

Amacimiz: okuyuculara SADECE gercekten yeni cikan modeller, yontemler ve teknolojileri iletmek.
Eger bir baslik bu kriterlere giriyorsa KEEP et, girecek kadar varsa hepsini KEEP et.

KEEP — asagidaki yollardan biri yeterlİ:

YOL A (duyuru): Baslikta yeni bir seyin adi + duyuru sinyali
  Duyuru sinyalleri: Introducing, Releasing, Launches, Announces, Open-sourcing, Released, Now available
  Ornek: "Introducing GPT-Rosalind for life sciences research" → KEEP
  Ornek: "xAI Launches Grok Speech-to-Text API" → KEEP

YOL B (teknik haber): Baslikta somut model/yontem/teknoloji adi + teknik detay/yetenek
  (Duyuru sinyali olmasa da olur)
  Ornek: "Open-weight Kimi K2.6 takes on GPT-5.4 with agent swarms" → KEEP (model adi + teknik detay)
  Ornek: "Gemini 3.1 Flash TTS: the next generation of expressive AI speech" → KEEP
  Ornek: "New fine-tuning method lets LLMs learn new skills without forgetting" → KEEP (yeni yontem)
  Ornek: "NVIDIA Ising: AI-Powered Workflows for Fault-Tolerant Quantum Systems" → KEEP

SKIP — asagidakilerden HERHANGI BIRI varsa SKIP (model adi gecse bile):
- Is, yatirim, funding, CEO, sirket haberi ("raises $2B", "files for IPO", "pours $33B")
- Robotik, insansi robot, otonom arac ("humanoid", "robotaxi", "robot marathon")
- Liste, siralama ("Top 10", "Best X in 2026")
- Rehber, tutorial, uygulama ornegi ("How to", "Guide", "Explained", "Coding Implementation")
- Genel analiz, yorum, fikir ("Why AI is...", "tokenmaxxing", "The 12-month window")
- Politika, guvenlik, strateji haberi ("NSA", "Trump", "regulation", "builds elite team")
- Kullanici deneyimi, uretkenlik, is sureci haberleri

SKIP onceliklİdİr: KEEP kriterleri saglansa bile SKIP kosullari varsa SKIP et.
Negatif ornek: "Anthropic raises $10B for Claude Opus 4.7" → SKIP (model adi gecse de funding)
Suphe duyuyorsan SKIP et.

Basliklar:
{titles}

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


def main():
    if not API_KEY:
        print("OPENCODE_API_KEY bulunamadı. .env dosyasını kontrol et.")
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
    print(f"\n  Toplam KEEP: {len(kept)} / {len(items)}")

    out_path = os.path.join(DATA_DIR, date_str, "output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    print(f"  -> Kaydedildi: {out_path}")
    update_published_index(kept, date_str)

    stats = compute_source_stats(items, keep_indices)
    print_source_table(stats)
    save_source_stats(stats, date_str)
    update_source_quality(stats, date_str)


if __name__ == "__main__":
    main()
