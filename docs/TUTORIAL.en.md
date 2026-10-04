# Tutorial: your first gear in 5 minutes

🇹🇷 [Türkçe sürüm](TUTORIAL.md)

This guide walks through the app from start to finish: make a gear pair, read the results,
export it, then design a full reducer and simulate a differential.

## 0. Start the app

```bash
pip install -r requirements.txt
python uygulama/app.py
```

On Windows you can also double-click `baslat.bat`. The browser opens
`http://127.0.0.1:5050`.

## 1. The screen at a glance

![Overview](images/overview.png)

| # | Area | What it does |
|---|---|---|
| **1** | Gear type | Pick what to build: spur, helical, bevel, planetary, differential, reducer… |
| **2** | Parameters | Number of teeth, module, face width, profile shift, bore, hub… |
| **3** | 3D view | Drag to rotate, scroll to zoom, right-drag to pan. The chips at the top left show or hide parts. |
| **4** | Toolbar | ▶ animation and speed · ⤢ fit · ⊤ top view · edges · wireframe · 📷 PNG |
| **5** | Results | Export buttons, pair data (center distance, ratio, contact ratio) and **warnings** |

When you change a value, the model rebuilds automatically after a short pause. To rebuild
only when you press **Oluştur** (Build), turn off *Otomatik güncelle* (auto update).

## 2. Make a spur gear pair

1. Choose **Düz** (spur).
2. Set **z₁ = 14**, **z₂ = 29**, **module = 2 mm**.
3. Look at the **Uyarılar** (warnings) card. It says *z₁ = 14 < z_min ≈ 17: undercut,
   x₁ ≥ 0.18 recommended*.
4. Set **Profil kaydırma x₁ = 0.2** (profile shift). The warning disappears and the center
   distance updates.
5. Press **▶** to watch the pair mesh. The speed ratio is exactly z₂ / z₁.

The **Parçalar** (parts) card lists every dimension of each gear: pitch, tip, root and base
diameter.

## 3. Add a bore and export

1. Open **Dişli A — delik / göbek** (bore / hub). Set **bore = 8 mm** and
   **type = Kamalı (DIN 6885)**. The keyway is sized from the standard automatically.
2. In **Dışa aktar** (export), choose a part or *all parts*, then a format:

![Export panel](images/panel-export.png)

| Format | Use it for |
|---|---|
| **STEP** | CAD (SolidWorks, Fusion, FreeCAD). Exact smooth surfaces. "All parts" gives one coloured assembly. |
| **STL / 3MF** | 3D printing slicers |
| **DXF** | Laser / waterjet cutting. A 2D tooth profile with the bore. |

## 4. Other gear types (same workflow)

| Helical / herringbone | Bevel | Planetary |
|---|---|---|
| ![](images/helical.png) | ![](images/bevel.png) | ![](images/planetary.png) |
| **Rack & pinion** | **Worm (approx.)** | **Spline shaft + hub** |
| ![](images/rack.png) | ![](images/worm.png) | ![](images/spline.png) |

## 5. Design a reducer from requirements

Here you don't draw gears by hand. You give the requirements and the calculation sizes
everything.

![Reducer](images/reducer.png)

1. Choose **Redüktör** (reducer).
2. Enter **input power** (kW), **input speed** (rpm) and **total ratio**, e.g.
   0.25 kW · 1500 rpm · i = 9.
3. Under **Kademeler** (stages), set each stage's type (spur / helical / bevel / worm),
   material and ratio. *Oranı eşit dağıt* splits the ratio evenly.
4. Press **Oluştur**. For every stage the app:
   - picks a standard module from tooth-root and surface-pressure strength,
   - computes the face width, contact ratio and efficiency,
   - sizes the shafts (strength + deflection), keys and bearings,
   - builds the 3D assembly with shafts and keyed bores, placed without collisions.
5. The **Kademeler** table shows stress vs. allowable stress per stage (green = OK, red =
   fails). The **Rapor** tab has the full calculation sheet, which you can download as .txt:

![Report](images/report.png)

6. Not sure how to split the ratio? Under **Tasarım arama motoru** (design search), choose
   a goal (*coaxial*, *smallest volume*, *best efficiency*, *exact ratio*) and press
   *En iyi 5 tasarımı ara* (find the best 5). Click **Uygula** (apply) on a result to load
   it.

## 6. Explore the design with charts

After building a reducer, open the **Grafik** tab on the right. Pick a stage and a
parameter (profile shift, helix angle, stage ratio). Each quantity gets its own chart:
the blue line is the computed value, the red dashed line is the safety limit, the faint red
area is out of bounds and the dotted line marks the current design. Hover to read all values
at once; *Tablo olarak göster* shows the data as a table.

![Chart panel](images/panel-grafik.png)

## 7. Simulate a differential

![Differential](images/differential.png)

1. Choose **Diferansiyel**.
2. The model contains the ring gear and drive pinion, two side gears (left/right axle), 2 or
   4 spider gears and the cross pin.
3. Press **▶**. With **Viraj = 0 %** (straight road) both axles turn together with the
   carrier and the spiders stay still on their pin.
4. Set **Viraj = 30 %** (turning). The outer wheel now turns at 130 %, the inner one at
   70 %, and the spiders spin on the cross pin. That speed difference is exactly what a
   differential is for.

## TR → EN glossary

| UI (TR) | English |
|---|---|
| Düz / Helisel / Konik | Spur / Helical / Bevel |
| İç dişli / Kremayer / Sikloid | Internal (ring) / Rack / Cycloidal |
| Planet / Sonsuz vida / Kamalı mil | Planetary / Worm / Spline shaft |
| Diferansiyel / Redüktör | Differential / Reducer (gearbox) |
| Diş sayısı · Modül · Diş genişliği | Number of teeth · Module · Face width |
| Kavrama açısı · Helis açısı · Profil kaydırma | Pressure angle · Helix angle · Profile shift |
| Boşluk · Delik · Göbek · Kama | Backlash · Bore · Hub · Key |
| Eksen mesafesi · Kavrama oranı · Çevrim oranı | Center distance · Contact ratio · Gear ratio |
| Aks dişlisi · Uydu dişlisi · Ayna · Viraj | Side gear · Spider gear · Ring gear · Turn |
| Oluştur · Dışa aktar · Uyarılar · Rapor | Build · Export · Warnings · Report |
