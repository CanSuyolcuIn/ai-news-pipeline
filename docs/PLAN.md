# AI Haber Pipeline — Proje Planı

## Proje Amacı
Son 72 saatteki önemli AI haberlerini otomatik toplayıp, tekrarları temizleyip, LLM ile filtreleyerek temiz bir JSON çıktısı üretmek.

Downstream (başka kişi/sistem tarafından yapılacak): n8n ile otomasyon, email gönderimi.

---

## Mimari

```
fetch.py → dedup.py → filter.py → [ileride: summarize.py]
              ↓
         results.json → deduped.json → output.json → [summary.json]
```

### Klasör Yapısı
```
ai_news/
├── pipeline/               # Tüm Python scriptleri
│   ├── fetch.py            # RSS + Exa'dan veri çekme
│   ├── dedup.py            # Tekrar temizleme + tarih filtresi
│   ├── filter.py           # LLM ile başlık filtreleme (1. pass)
│   ├── sources.yaml        # RSS kaynakları ve Exa sorguları
│   ├── .env                # API anahtarları (git'e gitmiyor)
│   ├── .env.example        # API anahtarı şablonu
│   └── data/
│       └── YYYY-MM-DD/
│           ├── results.json    # Ham toplanan haberler
│           ├── rss_stats.json  # RSS kaynakları istatistiği
│           ├── exa_stats.json  # Exa sorgu istatistiği
│           ├── deduped.json    # Tekrarsız haberler
│           └── output.json     # LLM filtre sonrası temiz liste
├── docs/
│   ├── PLAN.md             # Bu dosya
│   └── PROGRESS.md         # Oturum notları ve kaldığımız yer
└── [eski dosyalar - silinebilir]
    ├── generate_plan.js
    ├── filter_rules.json
    └── filtered_2026-04-16.json
```

---

## Script Detayları

### `fetch.py`
- **RSS kaynakları**: HuggingFace, OpenAI, Google DeepMind, Google AI, Microsoft Research, Weaviate, The Decoder, VentureBeat, MIT Tech Review, TechCrunch, Import AI, HackerNews
- **Exa sorguları**: 33 adet (model, framework, altyapı, github, x_twitter kategorileri)
- **Ayarlar**: `HOURS_BACK = 72`, `num_results = 30` (Exa başına)
- **Çıktı**: `results.json`, `rss_stats.json`, `exa_stats.json`

### `dedup.py`
- **Tarih filtresi**: Son 72 saat dışındakileri atar. Parse edilemeyen tarihler → **atar** (False)
- **URL normalize**: locale prefix temizleme (`/en-US/`, `/tr/` vb.), query string, trailing slash
- **Başlık benzerliği**: Jaccard similarity, eşik = 0.55
- **Desteklenen tarih formatları**: ISO 8601, RFC 2822, GMT, `%Y-%m-%d`

### `filter.py`
- **Model**: `minimax-m2.5` (reasoning model) via opencode.ai proxy
- **API**: `https://opencode.ai/zen/go/v1`
- **Batch boyutu**: 50
- **max_tokens**: 2000 (retry: 4000)
- **Prompt**: Başlık + tarih bilgisi gönderilir, LLM KEEP/SKIP kararı verir
- **KEEP kriterleri**: Yeni AI modeli/framework/benchmark/MCP server/GitHub projesi (son 3 gün)
- **SKIP kriterleri**: Tutorial, Top 10, yatırım, CEO, 2025 öncesi, tarih_yok, GitHub release sayfaları, MCP listeleme siteleri

---

## Pipeline Çalıştırma

```bash
cd pipeline/

# 1. Veri çek
python fetch.py

# 2. Tekrar temizle
python dedup.py

# 3. LLM filtrele
python filter.py
```

Çıktı: `pipeline/data/YYYY-MM-DD/output.json`

---

## Sonraki Adımlar (Backlog)

### Öncelikli
- [ ] `summarize.py` — output.json'daki her haberi güçlü model ile özetle (2. pass)
  - Model: Claude veya GPT-4.1 (opencode proxy üzerinden)
  - Her haber için 2-3 cümle özet + kategori etiketi
  - Çıktı: `summary.json`

### İyileştirmeler
- [ ] `fetch.py`'a yield rate takibi: Exa sorgusu başına kaç haber KEEP ediliyor?
- [ ] `filter.py`'a paralel batch desteği (şu an sıralı)
- [ ] Kaynak kalitesi analizi: Hangi RSS / Exa kaynağı en çok faydalı haber veriyor?
- [ ] GitHub Actions ile günlük otomatik çalıştırma

### Değerlendirilecek
- [ ] İkinci dedup geçişi: output.json içindeki kalan tekrarlar (özellikle farklı URL, aynı haber)
- [ ] Tarihsiz Exa sonuçlarını URL'den tarih çıkararak doğrulama

---

## API Bilgileri

| Servis | Kullanım | Notlar |
|--------|----------|--------|
| Exa.ai | Semantic news search | `exa-py` kütüphanesi |
| opencode.ai | LLM proxy | `OPENCODE_API_KEY` gerekli |
| minimax-m2.5 | Filtreleme modeli | Reasoning model, `reasoning_content` alanı kullanır |
