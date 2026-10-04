# Redüktör Tasarım Aracı — masaüstü sürüm (Tkinter)

Projenin ilk sürümü olan masaüstü uygulaması. Hesap çekirdeği artık proje kökündeki
[`hesap/`](../hesap) paketinde; bu klasörde yalnızca Tkinter arayüzü, terminal (CLI) modu
ve OpenSCAD / DXF / facetli STEP çıktısı kaldı. Ana uygulama artık
[web arayüzüdür](../uygulama).

```bash
python legacy/reduktor_masaustu.py          # masaüstü arayüz
python legacy/reduktor_masaustu.py --cli    # terminal (etkileşimli)
python legacy/reduktor_masaustu.py --demo   # örnek hesap
```

Harici kütüphane gerektirmez; grafikler doğrudan Tkinter Canvas'a çizilir.

## Arayüz sekmeleri

| Sekme | İçerik |
|---|---|
| 📊 Rapor | Tam hesap, kutulu sonuçlar, adım adım çözüm akışı, uyarılar |
| 🔧 Şema | Orantılı yan görünüş, eş eksenlilik kontrolü |
| ⚙ Profil | Evolvent profil + taksimat / temel / dip daireleri |
| ➡ Akış | MOTOR → K1 → … → ÇIKIŞ; ok kalınlığı momentle orantılı |
| 📈 Duyarlılık | β → Fa / εβ · x₁ → σ₁ / sₐ / εα · q → η / γ · φm → mm / b / σ₁ |
| 🔍 Ara | Tasarım araması: eş eksenli / en küçük hacim / en yüksek verim / oran hassasiyeti |
| ⚖ Karşılaştır | A/B senaryo tablosu ve otomatik yorum |

## Formül kaynakları

- **Alın dişliler** (diş dibi + yüzey basıncı ile boyutlandırma), **düz konik dişliler**,
  mil (`Mv = √(M² + 0,75(α₀T)²)`): Akkurt, *Makina Elemanları Cilt II*.
- Standart modül serisi: DIN 780. Kama: DIN 6885.
- `[DIN/tahmini]` olarak işaretlenen kısımlar: sonsuz vida (DIN 3975 / Niemann), plastik
  dişli kontrolleri (VDI 2736), rulman X-Y katsayıları, ömür faktörü Y_N, verim
  (Ohlendorf H_v), sehim sınırı.
- Konik dişli notasyonu: db = baş çapı, dt = taban çapı (temel daire değil); φm = b/mm ≤ 10.

## Doğrulama

**Düz konik dişli, çözümlü örnek** (P = 5,5 kW, n = 960 d/dk, i = 4,5, z₁ = 14, m = 6,
b = 30). Bu değerler [`tests/`](../tests) altında otomatik test olarak da kontrol edilir.

| | Kod | El hesabı |
|---|---|---|
| δ01 | 12,53° | 12,53° |
| mm | 5,535 mm | 5,535 mm |
| Ft | 1412,1 N | 1412,1 N |
| Fa | 111,5 N | 111,5 N |
| Fr | 501,7 N | 501,7 N |

Ayrıca: düz 20/60 dişli çiftinde εα = 1,671 (kitap değeri).

## Bilinçli basitleştirmeler

- **Mil modeli:** dişlilerin aynı düzlemde olduğu kabul edilir, yani kuvvetler üst üste
  biner. Bu kabul güvenli taraftadır.
- **Kf (form faktörü):** Akkurt grafiğine yaklaşık bir eğri kullanılır. Kesin hesap için
  değer grafikten okunup `Kf` olarak girilmelidir.
- Sehim hesabında tekil momentlerin (Fa·d/2) katkısı ihmal edilir.
- Konik dişlide yalnızca diş dibi kontrolü vardır, yüzey basıncı kontrolü yoktur.

## Düzenlenebilir varsayılanlar

`hesap/veriler.py`: `MATERIALS` (σ_em, P_Hem, E, μ, μ_gresli, Tg, p_key, sn_exp),
`BEARINGS`, `DIN6885` · varsayılanlar: ψd = 0,8 · S = 1,5 · Kv = 1,15 · Km = 1,2 ·
mil L = 3·b · α₀c = 0,7 · k = 15 W/m²K
