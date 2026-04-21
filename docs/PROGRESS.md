# AI Haber Pipeline — İlerleme Notları

## Son Güncelleme: 2026-04-21

---

## Tamamlanan Adımlar

### fetch.py ✅
- RSS + Exa entegrasyonu çalışıyor
- **2026-04-21 düzeltmesi**: `max_age_hours` → `start_published_date` (ISO format) — Exa artık tarih filtresini doğru uyguluyor, tarihi olmayan sonuç yok
- **2026-04-21 düzeltmesi**: `HOURS_BACK` 72 → 168 (7 gün)
- **2026-04-21**: Exa stats'a `no_date` alanı eklendi — tarihsiz sonuç takibi
- **2026-04-21**: 6 yeni RSS kaynağı eklendi: Meta AI Engineering, Ai2, NVIDIA Developer, AWS ML, MarkTechPost, Ahead of AI, Simon Willison
- **2026-04-21**: Çalışmayan RSS'ler kaldırıldı (VentureBeat, Weaviate, Hacker News)
- **2026-04-21**: Anthropic, Mistral, Cohere → RSS yok, `site:` Exa sorgusu ile kapsandı
- **2026-04-21**: Evergreen Exa sorguları temizlendi (LoRA/QLoRA, AutoGPT, LangChain, TensorRT vb.)
- **2026-04-21**: Duyuru odaklı Exa sorguları eklendi ("introducing", "we are open sourcing", "released 2026" vb.)
- Çıktı: ~650 ham kayıt (2026-04-21 çalıştırması)

### dedup.py ✅
- Tarih filtresi (son 168 saat / 7 gün)
- URL normalizasyonu (locale prefix, query string, trailing slash)
- Başlık Jaccard benzerliği (eşik: 0.55)
- **2026-04-21 düzeltmesi**: `is_title_subset()` fonksiyonu eklendi — kısa başlık uzun başlığın %90'ında geçiyorsa duplicate sayılır (min 3 kelime)
- **2026-04-21 düzeltmesi**: Gemini TTS gibi "kısa başlık = uzun başlığın özeti" tekrarları artık yakalanıyor
- Çıktı: ~108 kayıt (2026-04-21 çalıştırması)

### filter.py ✅
- minimax-m2.5 modeli (opencode.ai)
- 50'lik batch'ler, başarısız batch'ler için retry
- **2026-04-21 düzeltmesi**: Prompt tamamen yeniden yazıldı
  - KEEP oranı kısıtlaması kaldırıldı — mantıklı olan her şey geçebilir
  - İki KEEP yolu: Yol A (duyuru sinyali) VEYA Yol B (model adı + teknik detay)
  - "takes on", "outperforms" gibi rekabet dili içeren gerçek model haberlerini artık yakalıyor
  - Kimi K2.6 gibi başlıklar artık KEEP ediliyor
  - SKIP öncelikli: model adı geçse bile funding/robotik SKIP kalıyor
- Çıktı: 28 kayıt (2026-04-21 çalıştırması)

---

## 2026-04-21 Oturumu — Özet

| Adım | Önce | Sonra |
|------|------|-------|
| Ham kayıt | 1014 | ~650 |
| Tarihi olmayan Exa sonucu | 955/1000 (%95) | 0/925 (%0) |
| Dedup sonrası | 57 | 108 |
| Filter sonrası | 5 | 28 |
| Gerçek yeni içerik | 5/5 ✅ ama az | 28 (çoğu kaliteli) |

---

## Sırada Yapılacaklar

### Kısa vadeli (öncelikli)

1. **Cross-day dedup** — Aynı haber ertesi gün tekrar gelmesin
   - `published_index.json` dosyası: her gün filter çıktısındaki URL'leri buraya ekle
   - Fetch → dedup aşamasında bu index'e bak, daha önce yayınlananları çıkar
   - Index'i 30 günde bir temizle

2. **summarize.py** — Her haber için özet + kategori üret
   - Her haber: 2-3 cümle Türkçe özet
   - Kategori: Model / Yöntem / Araç / Platform / Araştırma
   - Çıktı: `summary.json`

3. **output.py / format.py** — Nihai çıktıyı formatla
   - Markdown, e-posta veya webhook formatında yayına hazır hale getir

### Orta vadeli

4. **Kaynak kalitesi izleme** — Her çalıştırmada kaynak başına KEEP oranını logla
   - Hangi RSS/Exa kaynakları gerçek içerik getiriyor, hangisi gürültü?

5. **filter.py ince ayarı** — Tartışmalı SKIP/KEEP kararları
   - NVIDIA teknik bloglardan "How to Build..." rehberleri hâlâ geçiyor
   - AWS billing/maliyet haberleri (granular cost attribution) model haberi değil

---

## Bilinen Sorunlar

- [ ] NVIDIA Blog "How to Build..." rehber yazıları filter'dan geçiyor — SKIP kriterleri güçlendirilebilir
- [ ] AWS billing/maliyet haberleri KEEP oluyor (özellik haberi ama teknik değil)
- [ ] MarkTechPost bazı çalıştırmalarda 0 sonuç döndürüyor (geçici görünüyor)
- [ ] Microsoft Research Blog son 7 günde 0 AI haberi — pasif kaynak

---

## Pipeline Parametreleri (Güncel)

| Parametre | Değer | Dosya |
|-----------|-------|-------|
| HOURS_BACK | 168 (7 gün) | fetch.py, dedup.py |
| start_published_date | HOURS_BACK kadar geriye | fetch.py |
| Exa num_results | 30 | fetch.py |
| SIMILARITY_THRESHOLD | 0.55 | dedup.py |
| SUBSET_CONTAINMENT_RATIO | 0.90 | dedup.py |
| SUBSET_MIN_WORDS | 3 | dedup.py |
| BATCH_SIZE | 50 | filter.py |
| MODEL | minimax-m2.5 | filter.py |
| max_tokens | 2000 (retry: 4000) | filter.py |
| BASE_URL | https://opencode.ai/zen/go/v1 | filter.py |

---

## Klasör Yapısı (Güncel)

```
ai_news/
├── pipeline/
│   ├── fetch.py
│   ├── dedup.py
│   ├── filter.py
│   ├── sources.yaml
│   ├── .env
│   └── data/
│       └── YYYY-MM-DD/
│           ├── results.json     (~650 kayıt)
│           ├── rss_stats.json
│           ├── exa_stats.json
│           ├── deduped.json     (~108 kayıt)
│           └── output.json      (~28 kayıt)
└── docs/
    ├── PLAN.md
    └── PROGRESS.md
```
