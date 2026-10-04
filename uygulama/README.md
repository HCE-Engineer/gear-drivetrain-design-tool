# Çark Oluşturucu — web arayüzü

geargen.xyz tarzı dişli üretici: solda parametreler, ortada 3B önizleme + animasyon,
sağda ölçüler / uyarılar / dışa aktarma.

- **Geometri:** `py_gearworks` (build123d / OpenCascade) → gerçek B-rep katılar
- **Redüktör hesabı:** proje kökündeki `hesap/` paketi (Akkurt / DIN)
- **Kamalı mil:** `araclar/mil_spline.py` profilinin parametrik hâli

## Çalıştırma

Proje kökündeki `baslat.bat` dosyasına çift tıkla (ilk seferde paketleri kurar), ya da:

```
pip install -r uygulama/requirements.txt
python uygulama/app.py          # http://127.0.0.1:5050 açılır
```

`py_gearworks` ayrıca kurulmak zorunda değil; `app.py` onu
`vendor/py_gearworks` klasöründen yükler.

## Dişli tipleri

| Tip | Not |
|---|---|
| Düz / Helisel | Tek veya çift, profil kaydırma, balıksırtı, alttan kesilme, boşluk |
| İç dişli | Halka + pinyon |
| Konik | Σ eksen açısı, yaklaşık spiral |
| Kremayer | Düz / helisel, ileri-geri animasyon |
| Sikloid | Yuvarlanma çemberi ayarlı |
| Planet | Güneş + n gezegen + halka, taşıyıcı dönüşü animasyonda |
| Sonsuz vida | Çapraz helisel ile **yaklaşık** model (py_gearworks'te gerçek worm yok) |
| Kamalı mil | 30° evolvent mil + boşluklu eş göbek |
| Diferansiyel | Ayna + tahrik pinyonu, 2 aks dişlisi, 2/4 uydu; viraj (%) ile tekerlek hız farkı animasyonu |
| Redüktör | `hesap/` hesabı → kademeler, miller, kamalı göbek delikleri, rapor, tasarım arama |

Her dişliye delik (dairesel / DIN 6885 kamalı / D-kesit / altıgen) ve göbek eklenebilir.

## Grafik

Redüktör modunda **Grafik** sekmesi: seçilen kademenin bir parametresi (x₁, β, i, q, φm)
taranır, her büyüklük emniyet sınırıyla ayrı grafikte çizilir.

## Dışa aktarma

STL, STEP (tek parça ya da renkli montaj), DXF (2B diş profili + delik), 3MF.

## Notlar

- py_gearworks'ün kremayer `mesh_to` fonksiyonu pinyonu yanlış fazda yerleştirebiliyor;
  `motor.py` pinyonu çakışma hacmi sıfır olacak şekilde döndürerek düzeltir.
- Redüktör montajında her kademe bir önceki çarkın miline oturtulur; mil etrafındaki açı
  ve eksenel mesafe, parçalar çakışmayacak şekilde otomatik seçilir.
- Tüm animasyon hız oranları taksimat noktası hız eşitliğinden hesaplanır.
