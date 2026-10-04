# Redüktör Tasarım Aracı v3 — MAKEL2 (Akkurt/DIN)

Tek dosya Python + tkinter. **Harici kütüphane gerekmez** (matplotlib bile yok — grafikler Canvas'a çiziliyor).
1–3 kademe, tip: **düz / helisel / düz konik / sonsuz vida (worm)**.

```bash
python reduktor.py          # GUI
python reduktor.py --cli    # terminal (interaktif)
python reduktor.py --demo   # örnek hesap
```

## GUI sekmeleri
| Sekme | İçerik |
|---|---|
| 📊 Rapor | Tam hesap, kutulu sonuçlar, ASCII çözüm akışı, uyarılar |
| 🔧 Şema | Orantılı yan görünüş; konik ⊥, worm dikdörtgen; eş eksenlilik kontrolü |
| ⚙ Profil | İnvolüt profil + taksimat/temel/dip daireleri; konikte Tredgold eşdeğeri |
| ➡ Akış | MOTOR→K1→…→ÇIKIŞ; ok kalınlığı ∝ moment |
| 📈 Duyarlılık | β→Fa/εβ · x1→σ1/sa/εα · q→η/γ · φm→mm/b/σ1 |
| 🔍 Ara | Tasarım araması: koaksiyel / min_hacim / max_verim / oran_hassas + "En iyiyi uygula" |
| ⚖ Karşılaştır | A/B senaryo tablosu + otomatik yorum |

## Bu sürümde eklenenler (1–10 + 16)
| # | Özellik | Not |
|---|---|---|
| 1 | **Koaksiyellik çözücü** | Koşul vektörel: a'lar kapalı çokgen. 2 kademe→a1=a2; 3 kademe→üçgen eşitsizliği + yerleşim açıları |
| 2 | **Kavrama oranı** εα/εβ/εγ | Boşluk j eklenmiş hali de ayrı raporlanır |
| 3 | **Diş ucu sivrilme** sa | Sınır: metal 0,2·mn, FDM max(0,4·mn; 0,8 mm) |
| 4 | **Kama basıncı** DIN 6885 | p=2T/(d·t2·l_eff); **plastik göbekte genelde belirleyici** |
| 5 | **Düz konik dişli** | Hocanın slaytı birebir (aşağıda doğrulama) |
| 6 | **Mil sehim/eğim** | Sadece uyarmıyor: f≤0,01·mn ve eğim≤1 mrad için **çapı büyütüyor**, belirleyici kriteri yazıyor |
| 7 | **Ömür → σ_em** | N=60·n·Lh → Y_N; σ_em ömre göre azalır |
| 8 | **Asal diş (hunting)** | gcd≠1 ise z2±1 önerir |
| 9 | **Otomatik tarama** | min hacim / max verim |
| 10 | **Oran sapması araması** | z kombinasyonlarını tarar |
| 16 | **Duyarlılık grafiği** | Canvas'a çizilir, bağımlılık yok |

**Ayrıca düzeltildi:** verim artık **sabit değil** — Ohlendorf H_v ile geometriye bağlı
(z1↑→η↑, gres μ↓→η↑). Rulman kataloğu 80 mm'ye genişletildi, ağır seriye (62xx)
otomatik geçiş ve "mili büyüt" önerisi eklendi. "Verilen m/b ile kontrol" modu (sınav soruları için).

## Formül kaynakları
- **Silindirik** diş dibi + yüzey basıncı + boyutlandırma: **hoca slaytı** (MAKEL2_DISLI_2, s.19)
- **Konik**: **hoca slaytı** (MAKEL2_KONİK_DISLI_2) — `tan δ01=sinδ/(i+cosδ)`, `m=mm+(b/z1)sinδ01`,
  `Ft=2Md/(z1·mm)`, `Fa=Ft·tanα·sinδ01`, `Fr=Ft·tanα·cosδ01`, `σ1=Ft/(b·mm)·K0·KF·Kv`, **φm=b/mm≤10**, `b≤R/3`
  ⚠️ Konikte **Km YOK**, ψd değil **φm**, ve **db=BAŞ / dt=TABAN** (temel daire değil!)
- Standart modül DIN 780; mil `Mv=√(M²+0,75(α₀T)²)` Akkurt
- `[DIN/tahmini]` (hoca slaytında yok, düzenlenebilir): worm DIN 3975, plastik VDI 2736,
  rulman X-Y, ömür Y_N, verim H_v (Ohlendorf), sehim sınırı

## Doğrulama
**Konik — hocanın çözümlü problemi** (P=5,5 kW, n=960, i=4,5, z1=14, m=6, b=30):

| | Kod | El hesabı |
|---|---|---|
| δ01 | 12,53° | 12,53° |
| mm | 5,535 | 5,535 |
| Ft | 1412,1 N | 1412,1 N |
| Fa | 111,5 N | 111,5 N |
| Fr | 501,7 N | 501,7 N |

Diğer: backlash j=0,3 → diş 0,430° inceldi (teorik 0,430°) · εα=1,671 (düz 20/60, kitap değeri) ·
DXF max yarıçap = da/2 · GUI konik+helisel+worm 3 kademede tüm sekmeler çiziyor.

⚠️ Hocanın el yazısı çözüm sayfasındaki sayıları okuyamadım (tarama görüntüsü açılmadı);
yukarıdaki karşılaştırma **slayttaki formüllerle yapılan bağımsız el hesabına** karşıdır.
Hocanın kendi sonuçlarıyla bir kez karşılaştırman iyi olur.

## Bilinçli basitleştirmeler (rapora da yazılır)
- **Mil modeli:** dişliler aynı faz düzleminde kabul (kuvvetler üst üste biner) — muhafazakâr.
  Sınav SCD'sinden farklı; proje raporuna elle kurman gerekir.
- **Kf** Akkurt grafiğine yaklaşık eğri — kesin iş için grafikten okuyup `Kf` gir.
- Sehimde tekil momentlerin (Fa·d/2) katkısı ihmal.
- Konikte yüzey basıncı formülü slaytta verilmemiş → sadece diş dibi kontrolü var.

## Düzenlenebilir varsayılanlar
`MATERIALS` (σ_em, P_Hem, E, μ, μ_gresli, Tg, p_key, sn_exp), `BEARINGS`, `DIN6885`,
ψd=0,8 · S=1,5 · Kv=1,15 · Km=1,2 · mil L=3·b · α₀c=0,7 · k=15 W/m²K
