"""
Formatlama scripti.
summary.json'u okur, kategori bazli gruplandirarak Markdown ve JSON bülten cikarir.

Kullanim:
    python format.py

Ciktilar:
    data/YYYY-MM-DD/bulletin.md   — Markdown bülten (e-posta / Obsidian)
    data/YYYY-MM-DD/bulletin.json — n8n / webhook icin yapilandirilmis JSON
"""

import json
import os
from collections import defaultdict
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

CATEGORY_ORDER = ["Model", "Yöntem", "Araç", "Platform", "Araştırma"]

CATEGORY_EMOJI = {
    "Model": "🤖",
    "Yöntem": "🔬",
    "Araç": "🛠️",
    "Platform": "☁️",
    "Araştırma": "📄",
}


def load_summary() -> tuple[list[dict], str]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, date_str, "summary.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f), date_str


def group_by_category(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        kategori = item.get("kategori", "").strip()
        if kategori not in CATEGORY_ORDER:
            kategori = "Araştırma"
        groups[kategori].append(item)
    return groups


def format_date(published: str) -> str:
    if not published:
        return ""
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(published.strip(), fmt)
            return dt.strftime("%-d %B %Y")
        except (ValueError, AttributeError):
            continue
    return published[:10]


def build_markdown(groups: dict[str, list[dict]], date_str: str) -> str:
    lines = [
        f"# AI Haber Bülteni — {date_str}",
        "",
        f"**{sum(len(v) for v in groups.values())} haber** | "
        + " · ".join(
            f"{CATEGORY_EMOJI.get(k, '')} {k} ({len(groups[k])})"
            for k in CATEGORY_ORDER
            if k in groups
        ),
        "",
        "---",
        "",
    ]

    for kategori in CATEGORY_ORDER:
        items = groups.get(kategori)
        if not items:
            continue

        emoji = CATEGORY_EMOJI.get(kategori, "")
        lines.append(f"## {emoji} {kategori}")
        lines.append("")

        for item in items:
            tarih = format_date(item.get("published", ""))
            tarih_str = f" · {tarih}" if tarih else ""
            lines.append(f"### [{item['title']}]({item['url']})")
            lines.append(f"*{item.get('source', '')}{tarih_str}*")
            lines.append("")
            if item.get("ozet"):
                lines.append(item["ozet"])
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def build_bulletin_json(groups: dict[str, list[dict]], date_str: str) -> dict:
    sections = []
    for kategori in CATEGORY_ORDER:
        items = groups.get(kategori)
        if not items:
            continue
        sections.append({
            "kategori": kategori,
            "emoji": CATEGORY_EMOJI.get(kategori, ""),
            "haberler": [
                {
                    "baslik": item["title"],
                    "url": item["url"],
                    "kaynak": item.get("source", ""),
                    "tarih": item.get("published", "")[:10],
                    "ozet": item.get("ozet", ""),
                }
                for item in items
            ],
        })

    return {
        "tarih": date_str,
        "toplam_haber": sum(len(v) for v in groups.values()),
        "sections": sections,
    }


def main():
    print("\n=== Formatlama basladi ===\n")

    items, date_str = load_summary()
    print(f"  Gelen kayit sayisi: {len(items)}")

    ozetsiz = [i for i in items if not i.get("ozet")]
    if ozetsiz:
        print(f"  [UYARI] {len(ozetsiz)} haberin ozeti yok, yine de dahil ediliyor")

    groups = group_by_category(items)
    print(f"  Kategori dagilimi: " + ", ".join(f"{k}:{len(v)}" for k, v in groups.items()))

    out_dir = os.path.join(DATA_DIR, date_str)

    md_path = os.path.join(out_dir, "bulletin.md")
    markdown = build_markdown(groups, date_str)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"  -> {md_path}")

    json_path = os.path.join(out_dir, "bulletin.json")
    bulletin = build_bulletin_json(groups, date_str)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(bulletin, f, ensure_ascii=False, indent=2)
    print(f"  -> {json_path}")


if __name__ == "__main__":
    main()
