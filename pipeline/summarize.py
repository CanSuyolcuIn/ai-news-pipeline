"""
Ozetleme scripti.
output.json'u okur, her haber icin 2-3 cumle Turkce ozet + kategori uretir.
Cikti: summary.json

Kullanim:
    python summarize.py

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

API_KEY = os.environ.get("OPENCODE_API_KEY", "")
BASE_URL = "https://opencode.ai/zen/go/v1"
MODEL = "minimax-m2.5"

BATCH_SIZE = 10


def load_output() -> tuple[list[dict], str]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, date_str, "output.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f), date_str


PROMPT_TEMPLATE = """Asagidaki AI haberlerinin her biri icin:
1. 2-3 cumle Turkce ozet yaz — teknik, somut, ozgun. "Bu makale..." gibi baslama.
2. Kategori sec (SADECE birini): Model / Yontem / Arac / Platform / Arastirma

   Model      = Yeni bir AI modeli veya versiyonu (GPT, Claude, Gemini, Llama vb.)
   Yontem     = Yeni egitim yontemi, mimari, algoritma, fine-tuning teknigi
   Arac       = Gelistirici araci, SDK, framework, API, MCP server
   Platform   = Bulut servisi, altyapi, deploy platformu
   Arastirma  = Akademik bulgu, benchmark, degerlendirime, analiz

Haberler:
{items}

SADECE asagidaki JSON formatinda yanit ver, baska hicbir sey yazma:
[
  {{"id": 0, "ozet": "...", "kategori": "Model"}},
  {{"id": 1, "ozet": "...", "kategori": "Yontem"}}
]"""


def summarize_batch(
    client: OpenAI, items: list[dict], offset: int
) -> dict[int, dict[str, str]]:
    lines = []
    for i, item in enumerate(items):
        snippet = (item.get("snippet") or "").strip()
        snippet_part = f"\n   Snippet: {snippet[:300]}" if snippet else ""
        lines.append(f"{i}: Baslik: {item['title']}{snippet_part}")

    prompt = PROMPT_TEMPLATE.format(items="\n\n".join(lines))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000,
    )

    raw = (response.choices[0].message.content or "").strip()

    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        parsed = json.loads(raw)
        return {
            offset + entry["id"]: {
                "ozet": entry.get("ozet", ""),
                "kategori": entry.get("kategori", ""),
            }
            for entry in parsed
        }
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"  [UYARI] Parse hatasi: {e}")
        print(f"  Ham yanit: {raw[:300]}")

        # Retry
        try:
            response2 = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=6000,
            )
            raw2 = (response2.choices[0].message.content or "").strip()
            match2 = re.search(r"\[.*?\]", raw2, re.DOTALL)
            if match2:
                parsed2 = json.loads(match2.group(0))
                print(f"  [RETRY basarili]")
                return {
                    offset + entry["id"]: {
                        "ozet": entry.get("ozet", ""),
                        "kategori": entry.get("kategori", ""),
                    }
                    for entry in parsed2
                }
        except Exception as e2:
            print(f"  [RETRY de basarisiz]: {e2}")

        return {}


def main():
    if not API_KEY:
        print("OPENCODE_API_KEY bulunamadi. .env dosyasini kontrol et.")
        return

    print("\n=== Ozetleme basladi ===\n")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    items, date_str = load_output()
    print(f"  Gelen kayit sayisi: {len(items)}")

    summaries: dict[int, dict[str, str]] = {}
    total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(items))
        batch = items[start:end]

        print(f"  Batch {batch_num + 1}/{total_batches} ({len(batch)} kayit)...")
        result = summarize_batch(client, batch, offset=start)
        summaries.update(result)
        print(f"    Ozetlendi: {len(result)}/{len(batch)}")

    enriched = []
    for i, item in enumerate(items):
        summary = summaries.get(i, {})
        enriched.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "published": item.get("published", ""),
            "snippet": item.get("snippet", ""),
            "ozet": summary.get("ozet", ""),
            "kategori": summary.get("kategori", ""),
        })

    out_path = os.path.join(DATA_DIR, date_str, "summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"\n  Toplam ozet: {sum(1 for e in enriched if e['ozet'])}/{len(enriched)}")
    print(f"  -> Kaydedildi: {out_path}")

    kategori_sayim: dict[str, int] = {}
    for e in enriched:
        k = e.get("kategori", "?")
        kategori_sayim[k] = kategori_sayim.get(k, 0) + 1
    print("\n  Kategori dagilimi:")
    for k, v in sorted(kategori_sayim.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
