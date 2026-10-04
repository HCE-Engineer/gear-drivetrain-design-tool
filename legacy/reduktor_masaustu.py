#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  REDÜKTÖR TASARIM & HESAP UYGULAMASI  v3   (masaüstü / Tkinter, Akkurt-DIN)
================================================================================
  1..3 kademe. Tip: DÜZ / HELİSEL / DÜZ KONİK / SONSUZ VİDA (worm).

  HESAP
    - Boyutlandırma (diş dibi + yüzey basıncı), geometri, eksenler arası mesafe
    - Kuvvetler Ft/Fr/Fa (helisel, konik ve worm'da EKSENEL), profil kaydırma
    - Kavrama oranı εα/εβ/εγ            (ÖZ.2)
    - Diş ucu sivrilme kontrolü sa       (ÖZ.3)
    - Göbek kaması DIN 6885 basıncı      (ÖZ.4)
    - DÜZ KONİK dişli (ÖZ.5)
    - Mil: SCD -> Mv -> çap, + sehim/eğim ile RİJİTLİK odaklı büyütme (ÖZ.6)
    - Ömür (çevrim) faktörü Y_N ile σ_em azalması (ÖZ.7)
    - Asal diş (hunting) kontrolü        (ÖZ.8)
    - Verim: Ohlendorf H_v — geometriye bağlı (sabit değil)
    - Rulman seçimi + L10h, worm sıcaklık/geri sürülme, plastik/FDM kontrolleri

  ARAMA MOTORU (ÖZ.1 / 9 / 10)
    Amaç: koaksiyel (a'lar kapalı çokgen) | min_hacim | max_verim | oran_hassas

  GUI (tkinter, sekmeli)
    Rapor | Şema | Profil | Akış | Duyarlılık (ÖZ.16) | Ara | Karşılaştır

  CAD
    OpenSCAD .scad (düz/helisel/konik/worm; göbek: dairesel/kama/D-flat/altıgen)
    DXF 2D involüt profil (backlash işlenmiş)

  KAYNAKLAR: (1) Akkurt, Makina Elemanları Cilt II  (2) DIN / Niemann
    Hesap çekirdeği proje kökündeki hesap/ paketindedir; bu dosya yalnızca
    masaüstü arayüzü, CLI ve OpenSCAD / DXF / facetli STEP çıktısını içerir.
    [DIN/tahmini] etiketli: worm (DIN 3975), plastik (VDI 2736), rulman X-Y,
    ömür faktörü Y_N, verim H_v (Ohlendorf), mil sehim sınırı.

  ÇALIŞTIRMA
      python reduktor.py            -> GUI
      python reduktor.py --cli      -> terminal (interaktif)
      python reduktor.py --demo     -> örnek hesap
================================================================================
"""

import sys
import math
import os
import json
import struct
import datetime
import itertools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Windows konsolu varsayılan olarak cp1252 kullanır ve Türkçe karakterlerde
# (ş, ğ, ı, ç, ö, ü) UnicodeEncodeError verir -> çıktıyı UTF-8'e zorla.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass



# hesap çekirdeği artık proje kökündeki hesap/ paketinde
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hesap import *  # noqa: E402,F401,F403


# ================================================================== #
#  BÖLÜM 5 — CAD ÇIKTISI
# ================================================================== #

GEARS_SCAD_URL = "https://raw.githubusercontent.com/chrisspen/gears/master/gears.scad"


def ensure_gears_scad(folder: str) -> bool:
    path = os.path.join(folder, "gears.scad")
    if os.path.exists(path):
        return True
    try:
        import urllib.request
        urllib.request.urlretrieve(GEARS_SCAD_URL, path)
        return True
    except Exception:
        return False


def _bore_cut_scad(bore, W, bore_type):
    notes = []
    if bore <= 0:
        return "", notes
    if bore_type == "altigen":
        af = bore/math.cos(math.radians(30))
        return (f"    translate([0,0,-1]) cylinder(d={af:.3f}, h={W+2:.1f}, $fn=6);",
                [f"Göbek: altıgen delik (anahtar ağzı {bore:.1f} mm)"])
    if bore_type == "dflat":
        flat = bore*0.1
        return (f"    translate([0,0,-1]) intersection() {{\n"
                f"      cylinder(d={bore:.3f}, h={W+2:.1f}, $fn=64);\n"
                f"      translate([-{bore:.3f}, -{bore:.3f}, 0]) "
                f"cube([{2*bore:.3f}, {bore - flat + bore/2:.3f}, {W+2:.1f}]);\n"
                f"    }}",
                [f"Göbek: D-flat (yassı derinlik {flat:.2f} mm)"])
    if bore_type == "kama":
        km = din6885(bore)
        if km is None:
            notes.append(f"UYARI: d={bore:.1f} mm için DIN 6885 kama yok -> D-flat'a düşüldü.")
            code, n2 = _bore_cut_scad(bore, W, "dflat")
            return code, notes + n2
        b_k, h_k, t2 = km
        return (f"    translate([0,0,-1]) cylinder(d={bore:.3f}, h={W+2:.1f}, $fn=64);\n"
                f"    // DIN 6885 kama kanalı: b={b_k} t2={t2}\n"
                f"    translate([-{b_k/2:.2f}, {bore/2 - 0.5:.3f}, -1]) "
                f"cube([{b_k}, {t2 + 0.5:.2f}, {W+2:.1f}]);",
                [f"Göbek: DIN 6885 kama b={b_k}×{h_k}, t2={t2} (d={bore:.1f})"])
    return (f"    translate([0,0,-1]) cylinder(d={bore:.3f}, h={W+2:.1f}, $fn=64);",
            ["Göbek: dairesel delik"])


def export_scad(r: StageResult, folder, bore1=None, bore2=None, bore_type="dairesel"):
    os.makedirs(folder, exist_ok=True)
    have_lib = ensure_gears_scad(folder)
    fname = os.path.join(folder, f"kademe{r.idx}_{r.gtype}.scad")
    b1 = bore1 if bore1 else round(max(4.0, r.d01*0.25))
    b2 = bore2 if bore2 else round(max(4.0, r.d02*0.20))
    j, W = r.backlash, r.b
    cut1, n1 = _bore_cut_scad(b1, W, bore_type)
    cut2, n2 = _bore_cut_scad(b2, W, bore_type)
    hdr = [f"// Otomatik üretildi — Kademe {r.idx} ({r.gtype}), malzeme {r.material}",
           f"// montaj boşluğu j = {j:.2f} mm (FDM toleransı)"]
    hdr += ["// " + s for s in (n1 + n2)]

    if r.gtype == "worm":
        body = "\n".join(hdr) + f"""
use <gears.scad>;
// m={r.mn}, z2={r.z2}, ağız z1={r.z1}, q={r.q}, γ={r.gamma:.2f}°
// NOT: worm'da boşluk geometriye işlenmedi; slicer'da %5 clearance bırak.
worm_gear(modul={r.mn}, tooth_number={r.z2}, thread_starts={r.z1},
          width={W:.1f}, length={r.mn*10:.1f},
          worm_bore={b1}, gear_bore={b2},
          pressure_angle=20, lead_angle={r.gamma:.2f},
          optimized=false, together_built=false);
"""
    elif r.gtype == "konik":
        body = "\n".join(hdr) + f"""
use <gears.scad>;
// DIŞ modül m={r.mn}, z1={r.z1}, z2={r.z2}, eksen açısı δ={r.delta_axis:.0f}°
// δ01={r.delta01:.2f}°, δ02={r.delta02:.2f}°, R={r.R_cone:.1f} mm, b={W:.1f} mm
// NOT: konik dişlide göbek deliği bevel_gear_pair içinden veriliyor.
bevel_gear_pair(modul={r.mn}, gear_teeth={r.z2}, pinion_teeth={r.z1},
                axis_angle={r.delta_axis:.0f}, tooth_width={W:.1f},
                gear_bore={b2}, pinion_bore={b1},
                pressure_angle=20, helix_angle=0, together_built=false);
"""
    else:
        helix = r.beta if r.gtype == "helisel" else 0
        body = "\n".join(hdr) + f"""
use <gears.scad>;

// ---- PİNYON  z1={r.z1} ----
difference() {{
    spur_gear(modul={r.mn}, tooth_number={r.z1}, width={W:.1f},
              bore=0, pressure_angle=20, helix_angle={helix}, optimized=false);
{cut1}
}}

// ---- ÇARK  z2={r.z2}  (a={r.a:.2f} + boşluk {j:.2f}; helis TERS) ----
translate([{r.a + j:.2f}, 0, 0])
difference() {{
    spur_gear(modul={r.mn}, tooth_number={r.z2}, width={W:.1f},
              bore=0, pressure_angle=20, helix_angle={-helix}, optimized=false);
{cut2}
}}
"""
    with open(fname, "w", encoding="utf-8") as f:
        f.write(body)
    if not have_lib:
        with open(fname + ".README.txt", "w", encoding="utf-8") as g:
            g.write("gears.scad indirilemedi. https://github.com/chrisspen/gears "
                    "adresinden gears.scad'i bu klasöre koy, OpenSCAD'de aç -> F6.\n")
    return fname


CHORD_TOL_MM = 0.01     # tessellation kiriş toleransı (mm). CAD çekirdeklerinin
                        # kullandığı ölçüt: kiriş ile gerçek eğri arası max sapma.


def _involute_gear_points(m, z, x=0.0, alpha_deg=20.0, steps=None, j=0.0,
                          tol=CHORD_TOL_MM):
    """
    Alın kesiti involüt kontur. j = çevresel boşluk (diş j/2 inceltilir).

    ÖNEMLİ — kontur SAAT YÖNÜNÜN TERSİNE (CCW) ve açısı MONOTON ARTARAK üretilir.
    (Eski sürümde her diş saat yönünde çizilirken dişler CCW sıralanıyordu; bu,
    kendi kendini kesen zikzak bir poligon üretiyor ve ekstrüzyondan geçen katı
    bozuk çıkıyordu. Değiştirirken poligonun monotonluğunu MUTLAKA test et.)

    Örnekleme, involütün YUVARLANMA AÇISI (roll angle, ρ) üzerinden eşit adımlarla
    yapılır — yarıçapa göre eşit adım DEĞİL (chrisspen/gears · gears.scad ile aynı
    yaklaşım). Involütün eğrilik yarıçapı R=rb·ρ olduğundan kiriş sapması
    s ≈ rb·ρ·(Δρ)²/8; nokta sayısı bu bağıntıdan `tol` toleransına göre otomatik
    seçilir (steps verilirse o kullanılır). Diş üstü ve diş dibi boşluğu da düz
    kiriş değil, gerçek daire yayı olarak noktalanır.
    """
    alpha = math.radians(alpha_deg)
    d = m*z
    db = d*math.cos(alpha)
    da = d + 2*m*(1 + x)
    df = d - 2*m*(1.25 - x)
    rb, ra, rf, rp = db/2, da/2, df/2, d/2

    def inv(a):
        return math.tan(a) - a

    s_t = m*(math.pi/2 + 2*x*math.tan(alpha)) - j/2.0
    offset = s_t/d + inv(math.acos(min(1.0, rb/rp)))

    # --- involüt yanak: ρ (yuvarlanma açısı) üzerinden eşit adım ---
    r_start = max(rb, rf)
    rho_s = math.sqrt(max(0.0, (r_start/rb)**2 - 1.0))
    rho_a = math.sqrt(max(0.0, (ra/rb)**2 - 1.0))
    if steps is None:
        if rho_a > rho_s:
            d_rho = math.sqrt(8.0*tol/max(rb*rho_a, 1e-9))
            n_fl = int(max(3, min(60, math.ceil((rho_a - rho_s)/max(d_rho, 1e-9)))))
        else:
            n_fl = 3
    else:
        n_fl = max(2, int(steps))

    flank = []
    for i in range(n_fl + 1):
        rho = rho_s + (rho_a - rho_s)*i/n_fl
        flank.append((rb*math.sqrt(1.0 + rho*rho), rho - math.atan(rho)))
    theta_s = flank[0][1]
    theta_a = flank[-1][1]

    def arc_between(r, a0, a1, out):
        """a0->a1 arası r yarıçaplı yay; sadece ARA noktalar eklenir (uçlar hariç)."""
        span = a1 - a0
        if r <= 1e-9 or abs(span) < 1e-12:
            return
        d_max = 2.0*math.acos(max(-1.0, min(1.0, 1.0 - tol/r)))
        n_seg = int(max(1, math.ceil(abs(span)/max(d_max, 1e-9))))
        for k2 in range(1, n_seg):
            a = a0 + span*k2/n_seg
            out.append((r*math.cos(a), r*math.sin(a)))

    # diş üstü yarım açısı; negatifse diş sivrilmiş demektir (sa kontrolü uyarır)
    tip_half = max(0.0, offset - theta_a)
    has_root_land = rf < r_start - 1e-12      # rf<rb ise diş dibine radyal iniş var
    root_half = offset if has_root_land else max(0.0, offset - theta_s)

    pts = []
    pitch = 2*math.pi/z
    for k in range(z):
        rot = k*pitch
        if has_root_land:
            pts.append((rf*math.cos(rot - offset), rf*math.sin(rot - offset)))
        for (r_i, th_i) in flank:                       # "-" yanak: açı artarak yükselir
            a = rot - offset + th_i
            pts.append((r_i*math.cos(a), r_i*math.sin(a)))
        arc_between(ra, rot - tip_half, rot + tip_half, pts)     # diş üstü yayı
        for (r_i, th_i) in reversed(flank):             # "+" yanak: açı artarak iner
            a = rot + offset - th_i
            pts.append((r_i*math.cos(a), r_i*math.sin(a)))
        if has_root_land:
            pts.append((rf*math.cos(rot + offset), rf*math.sin(rot + offset)))
        arc_between(rf, rot + root_half, rot + pitch - root_half, pts)   # diş dibi yayı
    return pts, da, df


# ================================================================== #
#  BÖLÜM 5b — 3B KATI MODEL (extrude -> STL / STEP, harici kütüphane yok)
# ================================================================== #

def _v_sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def _v_cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _v_dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _v_norm(a):
    return math.sqrt(_v_dot(a, a))


def _v_normalize(a):
    n = _v_norm(a)
    if n < 1e-15:
        return (0.0, 0.0, 1.0)
    return (a[0]/n, a[1]/n, a[2]/n)


DEG_PER_TWIST_SLICE = 3.0   # OpenSCAD linear_extrude(twist=..) mantığı: dilim sayısı
                            # sabit değil, TOPLAM BÜKÜLME AÇISINA göre uyarlanır.


def _gear_solid_faces(m, z, x, j, width, beta_deg=0.0, bore=0.0,
                      steps=None, n_twist_slices=None, merge_quads=False):
    """
    2B involüt diş profilini (_involute_gear_points) Z ekseninde ekstrüzyon
    yaparak 3B katı yüzey listesi üretir. Helis açısı varsa (β>0) profil
    yükseklik boyunca kademeli döndürülür (yaklaşık helikoid). Delik (bore)
    verilirse düz (bükülmemiş) silindirik bir göbek deliği açılır; verilmezse
    dolu (merkez fan) kapaklar üretilir.

    n_twist_slices=None (varsayılan) -> dilim sayısı TOPLAM BÜKÜLME AÇISINA göre
    otomatik hesaplanır (her ~3° için 1 dilim, en az 1). Eskiden SABİT 24 dilim
    kullanılıyordu — kısa/az bükülmeli (örn. β=15° ama dar genişlik -> toplam
    bükülme ~10°) dişlilerde bu gereksiz yere 6-8 kat fazla üçgen üretiyordu
    (chrisspen/gears OpenSCAD kütüphanesi de aynı OpenSCAD linear_extrude(twist=)
    mantığıyla adaptif çalışıyor — bkz. proje notları). Sayı elle verilirse
    (int) o zaman AYNEN kullanılır (override).

    merge_quads=True ise, DÜZLEMSEL olduğu KESİN olan bükülmemiş (twist=0)
    duvar panelleri (dış duvar düz dişlide + delik duvarı her zaman) 2 üçgen
    yerine TEK dörtgen yüzey olarak döner (STEP çıktısını ~yarıya indirir,
    CAD'de açılışı hızlandırır). STL her zaman saf üçgen ister -> merge_quads=False.

    Dönüş: (faces, da, df) — her face 3 veya 4 noktalık bir sınır döngüsü
    ((x,y,z), ...); yön/normal tutarlılığı KENAR-YÖNÜ testleriyle doğrulanmıştır
    (bkz. proje notları) — değiştirirken mutlaka aynı testlerle tekrar kontrol et.
    """
    pts2d, da, df = _involute_gear_points(m, z, x=x, j=j, steps=steps)
    N = len(pts2d)
    beta = math.radians(beta_deg)
    r_pitch = (m*z)/2.0

    total_twist = (width*math.tan(beta)/r_pitch) if abs(beta_deg) > 1e-9 else 0.0
    if abs(beta_deg) > 1e-9:
        if n_twist_slices is None:
            n_slices = max(1, math.ceil(abs(math.degrees(total_twist))/DEG_PER_TWIST_SLICE))
        else:
            n_slices = max(1, int(n_twist_slices))
    else:
        n_slices = 1
    twisted = n_slices > 1

    rings = []
    for k in range(n_slices+1):
        zc = width*k/n_slices
        ang = total_twist*k/n_slices
        cs, sn = math.cos(ang), math.sin(ang)
        ring = [(px*cs - py*sn, px*sn + py*cs, zc) for (px, py) in pts2d]
        rings.append(ring)

    faces = []
    # dış duvar (diş yüzeyleri): ardışık halkalar arası şerit
    for k in range(n_slices):
        a_ring, b_ring = rings[k], rings[k+1]
        for i in range(N):
            i2 = (i+1) % N
            v00, v01 = a_ring[i], a_ring[i2]
            v10, v11 = b_ring[i], b_ring[i2]
            if merge_quads and not twisted:
                faces.append((v00, v10, v11, v01))
            else:
                faces.append((v00, v10, v11))
                faces.append((v00, v11, v01))

    if bore > 0:
        if bore >= df*0.95:
            raise ValueError(
                f"Delik çapı ({bore:.1f} mm) diş dibi çapına ({df:.1f} mm) çok yakın/büyük "
                f"-> geçersiz geometri (diş dibinde duvar kalmaz). Delik çapını küçült.")
        rb0 = bore/2.0
        # Delik köşeleri, dış profildeki HER noktanın gerçek açısıyla eşleştirilir
        # (sabit adımlı çember DEĞİL) — aksi halde zip üçgenleri çapraz kesişip
        # (self-intersect) hatalı/katlanmış yüzeyler üretiyordu.
        thetas = [math.atan2(py, px) for (px, py) in pts2d]
        bore_bot = [(rb0*math.cos(t), rb0*math.sin(t), 0.0) for t in thetas]
        bore_top = [(rb0*math.cos(t), rb0*math.sin(t), width) for t in thetas]
        for i in range(N):
            i2 = (i+1) % N
            v00, v01 = bore_bot[i], bore_bot[i2]
            v10, v11 = bore_top[i], bore_top[i2]
            if merge_quads:
                faces.append((v10, v00, v01, v11))
            else:
                faces.append((v00, v11, v10))
                faces.append((v00, v01, v11))

        outer_top, outer_bot = rings[-1], rings[0]
        for i in range(N):
            i2 = (i+1) % N
            faces.append((outer_top[i], bore_top[i2], outer_top[i2]))
            faces.append((outer_top[i], bore_top[i], bore_top[i2]))
            faces.append((outer_bot[i], bore_bot[i2], bore_bot[i]))
            faces.append((outer_bot[i], outer_bot[i2], bore_bot[i2]))
    else:
        outer_top, outer_bot = rings[-1], rings[0]
        c_top, c_bot = (0.0, 0.0, width), (0.0, 0.0, 0.0)
        for i in range(N):
            i2 = (i+1) % N
            faces.append((c_top, outer_top[i2], outer_top[i]))
            faces.append((c_bot, outer_bot[i], outer_bot[i2]))

    # guvenlik agi: isaretli hacim negatifse (normaller tersse) topluca cevir
    def face_vol(f):
        v0 = f[0]
        return sum(_v_dot(v0, _v_cross(f[k], f[k+1])) for k in range(1, len(f)-1))
    vol6 = sum(face_vol(f) for f in faces)
    if vol6 < 0:
        faces = [tuple(reversed(f)) for f in faces]

    return faces, da, df


def gear_solid_triangles(m, z, x, j, width, beta_deg=0.0, bore=0.0,
                         steps=None, n_twist_slices=None):
    """STL için saf üçgen mesh. Dönüş: (triangles, da, df)."""
    return _gear_solid_faces(m, z, x, j, width, beta_deg=beta_deg, bore=bore,
                             steps=steps, n_twist_slices=n_twist_slices,
                             merge_quads=False)


def gear_solid_step_faces(m, z, x, j, width, beta_deg=0.0, bore=0.0,
                          steps=None, n_twist_slices=None):
    """STEP için optimize yüz listesi (düzlemsel duvar panelleri dörtgen
    olarak birleştirilmiş — daha az entity, CAD'de daha hızlı açılış).
    Dönüş: (faces, da, df) — her face 3 veya 4 köşeli bir sınır döngüsü."""
    return _gear_solid_faces(m, z, x, j, width, beta_deg=beta_deg, bore=bore,
                             steps=steps, n_twist_slices=n_twist_slices,
                             merge_quads=True)


def write_stl_binary(tris, path, name="gear"):
    name_b = name.encode("ascii", errors="replace")[:80].ljust(80, b" ")
    with open(path, "wb") as f:
        f.write(name_b)
        f.write(struct.pack("<I", len(tris)))
        for v1, v2, v3 in tris:
            e1 = _v_sub(v2, v1)
            e2 = _v_sub(v3, v1)
            n = _v_normalize(_v_cross(e1, e2))
            f.write(struct.pack("<12fH", n[0], n[1], n[2],
                                v1[0], v1[1], v1[2],
                                v2[0], v2[1], v2[2],
                                v3[0], v3[1], v3[2], 0))


class _StepWriter:
    """Facetli BREP (ucgen -> duz yuzey) STEP AP214 yazici — bkz. stl_to_step.py."""

    def __init__(self, f):
        self.f = f
        self.next_id = 1

    def _emit(self, entity_text):
        i = self.next_id
        self.next_id += 1
        self.f.write(f"#{i}={entity_text};\n")
        return i

    def cartesian_point(self, xyz):
        return self._emit(f"CARTESIAN_POINT('',({xyz[0]:.6f},{xyz[1]:.6f},{xyz[2]:.6f}))")

    def direction(self, xyz):
        return self._emit(f"DIRECTION('',({xyz[0]:.9f},{xyz[1]:.9f},{xyz[2]:.9f}))")

    def vector(self, dir_id, magnitude):
        return self._emit(f"VECTOR('',#{dir_id},{magnitude:.6f})")

    def line(self, point_id, vector_id):
        return self._emit(f"LINE('',#{point_id},#{vector_id})")

    def vertex_point(self, point_id):
        return self._emit(f"VERTEX_POINT('',#{point_id})")

    def edge_curve(self, v_start_id, v_end_id, curve_id):
        return self._emit(f"EDGE_CURVE('',#{v_start_id},#{v_end_id},#{curve_id},.T.)")

    def oriented_edge(self, edge_curve_id, same_sense):
        s = ".T." if same_sense else ".F."
        return self._emit(f"ORIENTED_EDGE('',*,*,#{edge_curve_id},{s})")

    def edge_loop(self, oriented_edge_ids):
        refs = ",".join(f"#{i}" for i in oriented_edge_ids)
        return self._emit(f"EDGE_LOOP('',({refs}))")

    def face_outer_bound(self, loop_id):
        return self._emit(f"FACE_OUTER_BOUND('',#{loop_id},.T.)")

    def axis2_placement_3d(self, origin_id, axis_dir_id, ref_dir_id):
        return self._emit(f"AXIS2_PLACEMENT_3D('',#{origin_id},#{axis_dir_id},#{ref_dir_id})")

    def plane(self, placement_id):
        return self._emit(f"PLANE('',#{placement_id})")

    def advanced_face(self, bound_ids, surface_id):
        refs = ",".join(f"#{i}" for i in bound_ids)
        return self._emit(f"ADVANCED_FACE('',({refs}),#{surface_id},.T.)")

    def closed_shell(self, face_ids):
        refs = ",".join(f"#{i}" for i in face_ids)
        return self._emit(f"CLOSED_SHELL('',({refs}))")

    def open_shell(self, face_ids):
        refs = ",".join(f"#{i}" for i in face_ids)
        return self._emit(f"OPEN_SHELL('',({refs}))")

    def manifold_solid_brep(self, shell_id):
        return self._emit(f"MANIFOLD_SOLID_BREP('',#{shell_id})")

    def shell_based_surface_model(self, shell_id):
        return self._emit(f"SHELL_BASED_SURFACE_MODEL('',(#{shell_id}))")


def _weld_face_vertices(faces, decimals=6):
    """Aynı koordinattaki köşeleri birleştirir. Alan-sıfır (üç/dört köşesi
    çakışık olmayan ama düzlemsel/kolineer) yüzler BİLEREK atılmıyor: bunlar
    diş kökünde (rf->rb geçişi) merkezle aynı ışında kalan gerçek ama sıfır-
    alanlı kapak yamalarıdır — atılırsa komşu kenarların paylaşım sayısı
    bozulup kabuk yanlışlıkla 'açık' görünür. Sadece köşeleri KAYNAŞMA
    SONRASI 3'ten az FARKLI indekse düşen (gerçekten dejenere) yüzler elenir."""
    index = {}
    verts = []
    ifaces = []

    def vid(p):
        key = (round(p[0], decimals), round(p[1], decimals), round(p[2], decimals))
        i = index.get(key)
        if i is None:
            i = len(verts)
            index[key] = i
            verts.append(p)
        return i

    for face in faces:
        idxs = [vid(p) for p in face]
        if len(set(idxs)) < 3:
            continue
        ifaces.append(tuple(idxs))
    return verts, ifaces


def write_step_facetted(faces, path, source_name="gear", progress_cb=None):
    """Yüz listesini (üçgen VEYA dörtgen, düz yüzeyli) facetli STEP AP214
    dosyası olarak yazar. Bkz. stl_to_step.py — aynı mantık, ara STL
    dosyasına gerek kalmadan doğrudan bellekteki yüzlerden çalışır.
    progress_cb(done, total) verilirse her ~2000 yüzde bir çağrılır (GUI
    ilerleme çubuğu için; senkron çalışır, thread gerekmez)."""
    verts, ifaces = _weld_face_vertices(faces)
    tmp_path = path + ".body.tmp"
    total = len(ifaces)

    with open(tmp_path, "w", encoding="ascii", newline="\n") as f:
        w = _StepWriter(f)
        point_ids = [None]*len(verts)
        vertex_ids = [None]*len(verts)
        for i, p in enumerate(verts):
            pid = w.cartesian_point(p)
            point_ids[i] = pid
            vertex_ids[i] = w.vertex_point(pid)

        edge_cache = {}
        face_ids = []
        for fi, idxs in enumerate(ifaces):
            if progress_cb and fi % 2000 == 0:
                progress_cb(fi, total)
            n_pts = len(idxs)
            i0, i1, i2 = idxs[0], idxs[1], idxs[2]
            p0, p1 = verts[i0], verts[i1]
            e1 = _v_sub(p1, p0)
            e2 = _v_sub(verts[i2], p0)
            normal_dir = _v_normalize(_v_cross(e1, e2))
            ref_dir = _v_normalize(e1)

            oriented_edges = []
            for k in range(n_pts):
                a, b = idxs[k], idxs[(k+1) % n_pts]
                key = (a, b) if a < b else (b, a)
                cached = edge_cache.get(key)
                if cached is None:
                    pa, pb = verts[a], verts[b]
                    d = _v_sub(pb, pa)
                    mag = _v_norm(d)
                    dnorm = _v_normalize(d)
                    dir_id = w.direction(dnorm)
                    vec_id = w.vector(dir_id, mag)
                    line_id = w.line(point_ids[a], vec_id)
                    ec_id = w.edge_curve(vertex_ids[a], vertex_ids[b], line_id)
                    edge_cache[key] = [ec_id, (a, b), 1]
                    same_sense = True
                else:
                    cached[2] += 1
                    ec_id = cached[0]
                    same_sense = (a, b) == cached[1]
                oriented_edges.append(w.oriented_edge(ec_id, same_sense))

            loop_id = w.edge_loop(oriented_edges)
            bound_id = w.face_outer_bound(loop_id)
            axis_id = w.direction(normal_dir)
            ref_id = w.direction(ref_dir)
            placement_id = w.axis2_placement_3d(point_ids[i0], axis_id, ref_id)
            plane_id = w.plane(placement_id)
            face_ids.append(w.advanced_face([bound_id], plane_id))

        boundary = sum(1 for v in edge_cache.values() if v[2] == 1)
        nonmanifold = sum(1 for v in edge_cache.values() if v[2] > 2)
        is_closed = (boundary == 0 and nonmanifold == 0)
        if is_closed:
            shape_item_id = w.manifold_solid_brep(w.closed_shell(face_ids))
        else:
            shape_item_id = w.shell_based_surface_model(w.open_shell(face_ids))

        len_unit_id = w._emit("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
        ang_unit_id = w._emit("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
        solid_ang_unit_id = w._emit("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
        unc_val_id = w._emit(
            f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-06),#{len_unit_id},"
            f"'DISTANCE_ACCURACY_VALUE','Confusion accuracy')")
        geom_ctx_id = w._emit(
            f"(GEOMETRIC_REPRESENTATION_CONTEXT(3) "
            f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{unc_val_id})) "
            f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{len_unit_id},#{ang_unit_id},#{solid_ang_unit_id})) "
            f"REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY'))")
        app_ctx_id = w._emit("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
        w._emit(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#{app_ctx_id})")
        prod_ctx_id = w._emit(f"PRODUCT_CONTEXT('',#{app_ctx_id},'mechanical')")
        prod_name = source_name.replace("'", "")
        product_id = w._emit(f"PRODUCT('{prod_name}','{prod_name}','',(#{prod_ctx_id}))")
        pd_ctx_id = w._emit(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{app_ctx_id},'design')")
        pdf_id = w._emit(f"PRODUCT_DEFINITION_FORMATION('','',#{product_id})")
        pd_id = w._emit(f"PRODUCT_DEFINITION('design','',#{pdf_id},#{pd_ctx_id})")
        pds_id = w._emit(f"PRODUCT_DEFINITION_SHAPE('','',#{pd_id})")
        shape_rep_id = w._emit(f"SHAPE_REPRESENTATION('',(#{shape_item_id}),#{geom_ctx_id})")
        w._emit(f"SHAPE_DEFINITION_REPRESENTATION(#{pds_id},#{shape_rep_id})")

    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "w", encoding="ascii", newline="\n") as out:
        out.write("ISO-10303-21;\nHEADER;\n")
        out.write("FILE_DESCRIPTION((''),'2;1');\n")
        out.write(f"FILE_NAME('{source_name}','{now}',('reduktor-proje'),(''),"
                  f"'reduktor.py (pure python)','','');\n")
        out.write("FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\n")
        out.write("ENDSEC;\nDATA;\n")
        with open(tmp_path, "r", encoding="ascii") as body:
            for line in body:
                out.write(line)
        out.write("ENDSEC;\nEND-ISO-10303-21;\n")
    os.remove(tmp_path)
    return dict(n_verts=len(verts), n_faces=len(ifaces), is_closed=is_closed)


def stage_gear_profile_params(r: StageResult, which: str):
    """Kademe + (pinyon/çark) için ekstrüzyona uygun (m, z, x, beta, bore_suggest) döner."""
    if r.gtype == "worm":
        return None
    if r.gtype == "konik":
        m_eff = r.mt
        if which == "pinyon":
            z_eff = max(1, int(round(r.ze1)))
        else:
            ze2 = r.z2/math.cos(math.radians(r.delta02)) if r.delta02 else r.z2
            z_eff = max(1, int(round(ze2)))
        x_eff, beta_eff = 0.0, 0.0
        d_ref = r.d01 if which == "pinyon" else r.d02
    else:
        m_eff = r.mt if r.gtype == "helisel" else r.mn
        z_eff = r.z1 if which == "pinyon" else r.z2
        x_eff = r.x1 if which == "pinyon" else r.x2
        beta_eff = r.beta if which == "pinyon" else -r.beta
        d_ref = r.d01 if which == "pinyon" else r.d02
    bore_suggest = round(max(4.0, d_ref*(0.25 if which == "pinyon" else 0.20)))
    return dict(m=m_eff, z=z_eff, x=x_eff, beta=beta_eff, width=r.b,
                j=r.backlash, bore_suggest=bore_suggest)


def export_dxf(r: StageResult, folder, bore1=None, bore_type="dairesel"):
    if r.gtype == "worm":
        return None
    os.makedirs(folder, exist_ok=True)
    fname = os.path.join(folder, f"kademe{r.idx}_pinyon_z{r.z1}_profil.dxf")
    if r.gtype == "konik":
        m_eff, z_eff = r.mt, max(1, int(round(r.ze1)))   # Tredgold eşdeğeri
    else:
        m_eff, z_eff = (r.mt if r.gtype == "helisel" else r.mn), r.z1
    pts, da, df = _involute_gear_points(m_eff, z_eff, x=r.x1, j=r.backlash)

    def poly(points):
        s = ["0", "POLYLINE", "8", "0", "66", "1", "70", "1"]
        for (px, py) in points:
            s += ["0", "VERTEX", "8", "0", "10", f"{px:.4f}", "20", f"{py:.4f}"]
        return s + ["0", "SEQEND"]

    lines = ["0", "SECTION", "2", "ENTITIES"] + poly(pts)
    bore = bore1 if bore1 else max(4.0, r.d01*0.25)
    lines += ["0", "CIRCLE", "8", "0", "10", "0", "20", "0", "40", f"{bore/2:.3f}"]
    if bore_type == "kama":
        km = din6885(bore)
        if km:
            b_k, h_k, t2 = km
            y0, y1 = bore/2 - 0.5, bore/2 - 0.5 + t2 + 0.5
            cs = [(-b_k/2, y0), (b_k/2, y0), (b_k/2, y1), (-b_k/2, y1), (-b_k/2, y0)]
            for p, q_ in zip(cs[:-1], cs[1:]):
                lines += ["0", "LINE", "8", "0", "10", f"{p[0]:.3f}", "20", f"{p[1]:.3f}",
                          "11", f"{q_[0]:.3f}", "21", f"{q_[1]:.3f}"]
    lines += ["0", "ENDSEC", "0", "EOF"]
    with open(fname, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fname


def export_all_cad(res: dict, folder, bore_type="dairesel"):
    files = []
    for i, r in enumerate(res['results']):
        b1 = res['shafts'][i].d_sec if i < len(res['shafts']) else None
        b2 = res['shafts'][i+1].d_sec if i+1 < len(res['shafts']) else None
        files.append(export_scad(r, folder, bore1=b1, bore2=b2, bore_type=bore_type))
        d = export_dxf(r, folder, bore1=b1, bore_type=bore_type)
        if d:
            files.append(d)
    return files


# ================================================================== #
#  BÖLÜM 6 — DEMO / CLI
# ================================================================== #


def demo():
    cfg = default_cfg()
    res = calc_reducer(cfg)
    print(report_full(res))
    folder = os.path.join(os.getcwd(), "cad_out")
    for f in export_all_cad(res, folder, bore_type="kama"):
        print("  CAD:", f)


def cli():
    print("="*60)
    print(" REDÜKTÖR HESAP v3 — CLI  (Enter = varsayılan)")
    print("="*60)

    def ask(p, d, cast=str):
        v = input(f"{p} [{d}]: ").strip()
        return cast(v) if v else d

    cfg = default_cfg()
    cfg['P_in'] = ask("Giriş gücü P (kW)", 0.25, float)
    cfg['n_in'] = ask("Giriş devri n (rpm)", 1500, float)
    cfg['i_total'] = ask("Toplam oran i", 9.0, float)
    cfg['n_stages'] = ask("Kademe sayısı (1-3)", 2, int)
    cfg['lubricated'] = ask("Gres yağlama? (e/h)", "h") in ("e", "E", "evet")
    cfg['backlash'] = ask("Boşluk j (mm)", 0.15, float)
    cfg['bed_size'] = ask("Baskı yatağı (mm)", 220.0, float)
    cfg['Lh_target'] = ask("Hedef ömür (saat)", 10000.0, float)

    print("\nMalzemeler:", ", ".join(MATERIALS.keys()))
    dist = distribute_ratio(cfg['i_total'], cfg['n_stages'])
    stages = []
    for k in range(cfg['n_stages']):
        print(f"\n--- Kademe {k+1} (önerilen oran {dist[k]:.2f}) ---")
        t = ask("Tip (duz/helisel/konik/worm)", "helisel")
        sc = dict(gtype=t, material=ask("Malzeme", "PETG"),
                  i_stage=ask("Bu kademe oranı", round(dist[k], 3), float))
        if t == "helisel":
            sc['beta'] = ask("Helis açısı β (°)", 15.0, float)
        if t == "konik":
            sc['delta_axis'] = ask("Eksen açısı δ (°)", 90.0, float)
            sc['phi_m'] = ask("φm = b/mm (≤10)", 10.0, float)
        if t == "worm":
            sc['z1'] = ask("Vida ağız sayısı z1", 2, int)
            sc['q'] = ask("Çap faktörü q", 10.0, float)
        if t in ("duz", "helisel"):
            sc['x1'] = ask("Profil kaydırma x1", 0.0, float)
        stages.append(sc)
    cfg['stages'] = stages

    res = calc_reducer(cfg)
    print("\n" + report_full(res))

    if ask("Tasarım araması yapılsın mı? (e/h)", "h") in ("e", "E", "evet"):
        obj = ask("Amaç (koaksiyel/min_hacim/max_verim/oran_hassas)", "koaksiyel")
        best = search_designs(cfg, objective=obj, n_best=5)
        print("\n" + report_search(best, obj))

    if ask("CAD üretilsin mi? (e/h)", "e") in ("e", "E", "evet"):
        bt = ask("Göbek tipi (dairesel/kama/dflat/altigen)", "kama")
        folder = os.path.join(os.getcwd(), "cad_out")
        for f in export_all_cad(res, folder, bore_type=bt):
            print("  ", f)


# ================================================================== #
#  BÖLÜM 7 — GUI
# ================================================================== #

def _is_float(s):
    try:
        float(s)
        return True
    except Exception:
        return False


def _is_int(s):
    try:
        int(float(s))
        return True
    except Exception:
        return False


def _ui_cfg_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reduktor_ui.json")


def _load_ui_cfg():
    try:
        with open(_ui_cfg_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ui_cfg(cfg):
    try:
        with open(_ui_cfg_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def gui():
    import tkinter as tk
    from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
    import threading
    import queue as _queue

    ui_cfg = _load_ui_cfg()

    root = tk.Tk()
    root.title("Redüktör Tasarım Aracı v3 — Akkurt / DIN")
    root.geometry(ui_cfg.get("geometry", "1400x900"))

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    BG, CARD, ACC, TXT, CVBG = "#1a1d23", "#242832", "#4ea1ff", "#e6e6e6", "#0f1115"
    WARN, ERR, OK = "#ffa657", "#ff6b6b", "#57d6a0"
    root.configure(bg=BG)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TXT, font=("Segoe UI", 9))
    style.configure("Card.TLabel", background=CARD, foreground=TXT, font=("Segoe UI", 8))
    style.configure("Head.TLabel", background=BG, foreground=ACC,
                    font=("Segoe UI", 11, "bold"))
    style.configure("CardHead.TLabel", background=CARD, foreground=ACC,
                    font=("Segoe UI", 9, "bold"))
    style.configure("TButton", font=("Segoe UI", 9, "bold"))
    style.configure("TCheckbutton", background=BG, foreground=TXT)
    style.configure("TEntry", fieldbackground="#2a2f3a", foreground=TXT,
                    insertcolor=TXT)
    style.configure("Invalid.TEntry", fieldbackground="#4a1f24", foreground="#ffb3b3")
    style.configure("Status.TLabel", background=CARD, foreground="#8892a4",
                    font=("Segoe UI", 8))

    # ---------------- alt durum çubuğu (önce paketlenir ki alanı ayrılsın) ---
    status_var = tk.StringVar(value="Hazır.")
    statusbar = ttk.Frame(root, style="Card.TFrame")
    statusbar.pack(side="bottom", fill="x")
    status_lbl = ttk.Label(statusbar, textvariable=status_var, style="Status.TLabel",
                           anchor="w")
    status_lbl.pack(side="left", fill="x", expand=True, padx=8, pady=3)

    def set_status(msg, kind="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        status_var.set(f"[{ts}] {msg}")
        color = {"info": "#8892a4", "ok": OK, "warn": WARN, "error": ERR}.get(kind, "#8892a4")
        try:
            status_lbl.configure(foreground=color)
        except Exception:
            pass

    # ---------------- son kullanılan klasörler (dosya diyalogları için) -----
    def dlg_dir(key):
        d = ui_cfg.get("dirs", {}).get(key)
        return d if d and os.path.isdir(d) else os.getcwd()

    def remember_dir(key, path):
        if not path:
            return
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if d:
            ui_cfg.setdefault("dirs", {})[key] = d

    main = ttk.Frame(root)
    main.pack(fill="both", expand=True, padx=8, pady=8)

    # ---------------- SOL: girdiler (kaydırılabilir) ----------------
    left_outer = ttk.Frame(main, width=440)
    left_outer.pack(side="left", fill="y")
    left_outer.pack_propagate(False)
    lcanvas = tk.Canvas(left_outer, bg=BG, highlightthickness=0, width=420)
    lscroll = ttk.Scrollbar(left_outer, orient="vertical", command=lcanvas.yview)
    left = ttk.Frame(lcanvas)
    left.bind("<Configure>",
              lambda e: lcanvas.configure(scrollregion=lcanvas.bbox("all")))
    lcanvas.create_window((0, 0), window=left, anchor="nw")
    lcanvas.configure(yscrollcommand=lscroll.set)
    lcanvas.pack(side="left", fill="both", expand=True)
    lscroll.pack(side="right", fill="y")

    def _mw(e):
        lcanvas.yview_scroll(int(-1*(e.delta/120)), "units")
    left_outer.bind("<Enter>", lambda e: lcanvas.bind_all("<MouseWheel>", _mw))
    left_outer.bind("<Leave>", lambda e: lcanvas.unbind_all("<MouseWheel>"))

    # ---------------- basit tooltip (balon ipucu) ----------------
    class Tooltip:
        def __init__(self, widget, text):
            self.widget, self.text, self.tip = widget, text, None
            widget.bind("<Enter>", self._show)
            widget.bind("<Leave>", self._hide)

        def _show(self, _e=None):
            if self.tip or not self.text:
                return
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            tk.Label(self.tip, text=self.text, justify="left", bg="#33394a",
                    fg="#e6e6e6", font=("Segoe UI", 8), padx=6, pady=3,
                    wraplength=260, relief="solid", borderwidth=1
                    ).pack()

        def _hide(self, _e=None):
            if self.tip:
                self.tip.destroy()
                self.tip = None

    def tip(widget, text):
        if text:
            Tooltip(widget, text)
        return widget

    ttk.Label(left, text="⚙  REDÜKTÖR GİRİŞLERİ", style="Head.TLabel").pack(anchor="w")
    gf = ttk.Frame(left)
    gf.pack(fill="x", pady=3)

    def row(parent, label, default, width=10, tip_text=None, cast="float"):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=1)
        lbl = ttk.Label(f, text=label, width=24)
        lbl.pack(side="left")
        e = ttk.Entry(f, width=width)
        e.insert(0, str(default))
        e.pack(side="left")
        checker = _is_float if cast == "float" else _is_int
        e.bind("<KeyRelease>", lambda ev: e.configure(
            style="TEntry" if checker(e.get().strip()) else "Invalid.TEntry"))
        tip(lbl, tip_text)
        return e

    e_P = row(gf, "Giriş gücü P (kW)", 0.25, tip_text="Motor/kaynak çıkış gücü. Kademe 1'e giren güç budur.")
    e_n = row(gf, "Giriş devri n (rpm)", 1500, tip_text="Giriş milinin devir sayısı (dakikada devir).")
    e_i = row(gf, "Toplam oran i", 9.0, tip_text="Hedeflenen toplam redüksiyon oranı = n_giriş/n_çıkış. Kademelere otomatik dağıtılır.")

    f_ns = ttk.Frame(gf); f_ns.pack(fill="x", pady=2)
    _lbl_ns = ttk.Label(f_ns, text="Kademe sayısı", width=24); _lbl_ns.pack(side="left")
    ns_var = tk.IntVar(value=2)
    ns_combo = ttk.Combobox(f_ns, values=[1, 2, 3], textvariable=ns_var, width=6,
                            state="readonly")
    ns_combo.pack(side="left")
    tip(_lbl_ns, "1-3 kademe. Her kademe kendi tipini (düz/helisel/konik/worm) ve oranını alır.")

    f_app = ttk.Frame(gf); f_app.pack(fill="x", pady=2)
    _lbl_app = ttk.Label(f_app, text="Uygulama (K0)", width=24); _lbl_app.pack(side="left")
    app_var = tk.StringVar(value=list(K0_TABLE.keys())[0])
    ttk.Combobox(f_app, values=list(K0_TABLE.keys()), textvariable=app_var,
                 width=22, state="readonly").pack(side="left")
    tip(_lbl_app, "Dinamik yük faktörü K0 — yük darbeliliğine göre diş dibi/yüzey hesabını büyütür.")

    lub_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(gf, text="Gres yağlama (μ↓, verim↑)", variable=lub_var
                    ).pack(anchor="w", pady=2)

    e_j = row(gf, "Boşluk j (mm)", 0.15, tip_text="Diş yanakları arası montaj/backlash boşluğu (FDM toleransı).")
    e_bed = row(gf, "Baskı yatağı (mm)", 220, tip_text="3D yazıcı tabla boyutu — tasarım aramasında parça sığdırma kontrolü için.")
    e_Lh = row(gf, "Hedef ömür (saat)", 10000, tip_text="Hedeflenen çalışma ömrü (saat) — σ_em ve rulman L10h buna göre kontrol edilir.")
    e_sig = row(gf, "Mil σ_em (N/mm²)", 60, tip_text="Mil malzemesinin izin verilen emniyet gerilmesi.")
    e_Emil = row(gf, "Mil E (N/mm²)", 210000, tip_text="Mil malzemesinin elastisite modülü (sehim hesabı için; çelik ~210000).")
    e_S = row(gf, "Emniyet katsayısı S", 1.5, tip_text="Diş dibi/mil kontrollerinde σ_em üzerine uygulanan emniyet payı.")

    f_bt = ttk.Frame(gf); f_bt.pack(fill="x", pady=2)
    _lbl_bt = ttk.Label(f_bt, text="Göbek tipi", width=24); _lbl_bt.pack(side="left")
    bore_var = tk.StringVar(value="kama")
    ttk.Combobox(f_bt, values=["dairesel", "kama", "dflat", "altigen"],
                 textvariable=bore_var, width=12, state="readonly").pack(side="left")
    tip(_lbl_bt, "CAD (.scad/.dxf) çıktısındaki mil deliği şekli: dairesel/kama (DIN 6885)/D-flat/altıgen.")

    ttk.Separator(left).pack(fill="x", pady=5)
    ttk.Label(left, text="KADEMELER", style="Head.TLabel").pack(anchor="w")
    stage_box = ttk.Frame(left)
    stage_box.pack(fill="x", pady=2)
    stage_widgets = []

    def build_stage_rows(*_):
        for w in stage_box.winfo_children():
            w.destroy()
        stage_widgets.clear()
        ns = ns_var.get()
        try:
            itot = float(e_i.get())
        except Exception:
            itot = 9.0
        dist = distribute_ratio(itot, ns)
        for k in range(ns):
            card = ttk.Frame(stage_box, style="Card.TFrame")
            card.pack(fill="x", pady=3, ipady=3)
            ttk.Label(card, text=f"  Kademe {k+1}", style="CardHead.TLabel").pack(anchor="w")
            f1 = ttk.Frame(card, style="Card.TFrame"); f1.pack(fill="x", padx=5)
            ttk.Label(f1, text="Tip", style="Card.TLabel").pack(side="left")
            tvar = tk.StringVar(value="helisel" if k == 0 else "duz")
            ttk.Combobox(f1, values=["duz", "helisel", "konik", "worm"],
                         textvariable=tvar, width=8, state="readonly"
                         ).pack(side="left", padx=3)
            ttk.Label(f1, text="Malz.", style="Card.TLabel").pack(side="left")
            mvar = tk.StringVar(value="PETG")
            ttk.Combobox(f1, values=list(MATERIALS.keys()), textvariable=mvar,
                         width=14, state="readonly").pack(side="left", padx=3)

            f2 = ttk.Frame(card, style="Card.TFrame"); f2.pack(fill="x", padx=5, pady=1)
            ent = {}
            for lbl, key, w_, dflt, ttext in [
                    ("oran", "i", 6, f"{dist[k]:.2f}", "Bu kademenin redüksiyon oranı (n_giriş/n_çıkış)."),
                    ("β°", "b", 5, "15", "Helis açısı — sadece 'helisel' tipte kullanılır (0=düz gibi davranır)."),
                    ("x1", "x", 5, "0", "Pinyon profil kaydırması. + diş dibini kalınlaştırır/alttan kesilmeyi önler."),
                    ("x2", "x2", 5, "0", "Çark profil kaydırması.")]:
                _l = ttk.Label(f2, text=lbl, style="Card.TLabel"); _l.pack(side="left")
                e = ttk.Entry(f2, width=w_); e.insert(0, dflt)
                e.pack(side="left", padx=2)
                tip(_l, ttext)
                ent[key] = e

            f3 = ttk.Frame(card, style="Card.TFrame"); f3.pack(fill="x", padx=5)
            for lbl, key, w_, dflt, ttext in [
                    ("worm z1", "z1", 4, "2", "Sonsuz vida ağız sayısı (sadece 'worm' tipte)."),
                    ("q", "q", 5, "10", "Worm çap oranı q=d1/m (sadece 'worm' tipte)."),
                    ("konik δ°", "da", 5, "90", "Eksenler arası açı (sadece 'konik' tipte; genelde 90°)."),
                    ("φm", "pm", 4, "10", "Konik dişlide b/mm oranı sınırı (sadece 'konik' tipte, ≤10 olmalı).")]:
                _l = ttk.Label(f3, text=lbl, style="Card.TLabel"); _l.pack(side="left")
                tip(_l, ttext)
                e = ttk.Entry(f3, width=w_); e.insert(0, dflt)
                e.pack(side="left", padx=2)
                ent[key] = e

            d = dict(t=tvar, m=mvar)
            d.update(ent)
            stage_widgets.append(d)

    ns_combo.bind("<<ComboboxSelected>>", build_stage_rows)
    build_stage_rows()
    ttk.Button(left, text="🔄 Kademeleri Yenile", command=build_stage_rows
               ).pack(anchor="w", pady=5)

    # ---------------- SAĞ: Notebook ----------------
    right = ttk.Frame(main)
    right.pack(side="left", fill="both", expand=True, padx=(8, 0))
    nb = ttk.Notebook(right)
    nb.pack(fill="both", expand=True)

    def add_text_tab(title):
        t = ttk.Frame(nb); nb.add(t, text=title)
        w = scrolledtext.ScrolledText(t, wrap="none", font=("Consolas", 9),
                                      bg=CVBG, fg="#d8e0ea", insertbackground=TXT)
        w.pack(fill="both", expand=True)
        return t, w

    def add_canvas_tab(title):
        t = ttk.Frame(nb); nb.add(t, text=title)
        c = tk.Canvas(t, bg=CVBG, highlightthickness=0)
        c.pack(fill="both", expand=True)
        return t, c

    def canvas_toolkit(cv, redraw_fn, name_hint):
        """Her çizim (canvas) sekmesine: fare tekerleği=yakınlaştır, sürükle=kaydır,
        + 'sıfırla' ve '.eps görsel kaydet' butonları ekler (harici kütüphane yok —
        gerçek PNG için Tk'nin desteklemediği bir dönüştürücü gerekir; PostScript/EPS
        çoğu görüntüleyicide/Illustrator/Inkscape'te açılır, PNG'ye çevrilebilir)."""
        bar = ttk.Frame(cv.master, style="Card.TFrame")
        bar.pack(side="top", fill="x", before=cv)
        ttk.Button(bar, text="🔍 Sıfırla", command=lambda: redraw_fn()
                  ).pack(side="left", padx=3, pady=2)

        def _export():
            p = filedialog.asksaveasfilename(
                defaultextension=".eps", initialfile=name_hint + ".eps",
                filetypes=[("PostScript/EPS", "*.eps")], initialdir=dlg_dir("images"))
            if not p:
                return
            try:
                cv.postscript(file=p, colormode="color")
                remember_dir("images", p)
                set_status(f"Görsel kaydedildi: {p}", "ok")
            except Exception as ex:
                messagebox.showerror("Hata", str(ex))
        ttk.Button(bar, text="💾 Görsel (.eps)", command=_export).pack(side="left", padx=3)
        ttk.Label(bar, text="  fare tekerleği: yakınlaştır · sürükle: kaydır",
                 style="Card.TLabel").pack(side="left", padx=6)

        def _wheel(e):
            factor = 1.1 if (getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4) else 0.9
            cv.scale("all", e.x, e.y, factor, factor)
        cv.bind("<ButtonPress-1>", lambda e: cv.scan_mark(e.x, e.y))
        cv.bind("<B1-Motion>", lambda e: cv.scan_dragto(e.x, e.y, gain=1))
        cv.bind("<MouseWheel>", _wheel)
        cv.bind("<Button-4>", _wheel)
        cv.bind("<Button-5>", _wheel)

    tab_rep, txt = add_text_tab("  📊 Rapor  ")
    tab_sch, cv_sch = add_canvas_tab("  🔧 Şema  ")
    canvas_toolkit(cv_sch, lambda: draw_schematic(), "sema")
    tab_prof, cv_prof0 = add_canvas_tab("  ⚙ Profil  ")
    # profil sekmesine combobox ekle
    cv_prof0.destroy()
    ptop = ttk.Frame(tab_prof); ptop.pack(fill="x", pady=2)
    ttk.Label(ptop, text="Dişli:").pack(side="left", padx=4)
    prof_var = tk.StringVar()
    prof_combo = ttk.Combobox(ptop, textvariable=prof_var, width=30, state="readonly")
    prof_combo.pack(side="left")
    cv_prof = tk.Canvas(tab_prof, bg=CVBG, highlightthickness=0)
    cv_prof.pack(fill="both", expand=True)
    canvas_toolkit(cv_prof, lambda: draw_profile(), "profil")

    # --- 3B KATI MODEL sekmesi (STL / STEP çıktısı, MANUEL girdi) ---
    tab_3d = ttk.Frame(nb); nb.add(tab_3d, text="  🧩 3B Model  ")

    m3d_fill = ttk.Frame(tab_3d); m3d_fill.pack(fill="x", padx=4, pady=(6, 2))
    ttk.Label(m3d_fill, text="Kademeden doldur (opsiyonel):").pack(side="left", padx=4)
    m3d_var = tk.StringVar()
    m3d_combo = ttk.Combobox(m3d_fill, textvariable=m3d_var, width=28, state="readonly")
    m3d_combo.pack(side="left")

    m3d_form = ttk.Frame(tab_3d); m3d_form.pack(fill="x", padx=4, pady=4)

    def _m3d_field(parent, label, default, width=8):
        f = ttk.Frame(parent); f.pack(side="left", padx=(0, 12))
        ttk.Label(f, text=label).pack(anchor="w")
        e = ttk.Entry(f, width=width)
        e.insert(0, str(default))
        e.pack()
        return e

    m3d_m = _m3d_field(m3d_form, "Modül m (mm)", 2.0)

    _f_mt = ttk.Frame(m3d_form); _f_mt.pack(side="left", padx=(0, 12))
    ttk.Label(_f_mt, text="Modül tipi").pack(anchor="w")
    m3d_mtype = tk.StringVar(value="normal (mn)")
    m3d_mtype_cb = ttk.Combobox(_f_mt, textvariable=m3d_mtype, width=12, state="readonly",
                                values=["normal (mn)", "alın (mt)"])
    m3d_mtype_cb.pack()

    m3d_z = _m3d_field(m3d_form, "Diş sayısı z", 20)
    m3d_x = _m3d_field(m3d_form, "Kaydırma x", 0.0)
    m3d_beta = _m3d_field(m3d_form, "Helis açısı β (°)", 0.0)
    m3d_width = _m3d_field(m3d_form, "Genişlik b (mm)", 15.0)
    m3d_j = _m3d_field(m3d_form, "Boşluk j (mm)", 0.15)
    m3d_bore = _m3d_field(m3d_form, "Delik Ø (mm, 0=yok)", 0.0)

    # ---- canlı 2B profil önizleme + bilgi paneli (yan yana) ----
    m3d_mid = ttk.Frame(tab_3d); m3d_mid.pack(fill="both", expand=True, padx=4, pady=(0, 4))
    m3d_info = scrolledtext.ScrolledText(m3d_mid, wrap="word", font=("Consolas", 9),
                                         bg=CVBG, fg="#d8e0ea", width=48)
    m3d_info.pack(side="left", fill="y", padx=(0, 4))
    m3d_preview = tk.Canvas(m3d_mid, bg=CVBG, highlightthickness=0)
    m3d_preview.pack(side="left", fill="both", expand=True)

    def draw_m3d_preview(*_):
        cv = m3d_preview
        cv.delete("all")
        W, H = cv.winfo_width(), cv.winfo_height()
        if W < 40 or H < 40:
            return
        try:
            m_in = float(m3d_m.get())
            z = int(float(m3d_z.get()))
            x = float(m3d_x.get())
            beta = float(m3d_beta.get())
            j = float(m3d_j.get())
            bore = max(0.0, float(m3d_bore.get()))
            if m_in <= 0 or z < 5:
                raise ValueError
            m_t = (m_in/math.cos(math.radians(beta))
                  if m3d_mtype.get().startswith("normal") else m_in)
        except Exception:
            cv.create_text(W//2, H//2, text="Geçerli m / z(≥5) / β gir",
                           fill="#667", font=("Segoe UI", 10))
            return
        try:
            pts, da, df = _involute_gear_points(m_t, z, x=x, j=j)
        except Exception as ex:
            cv.create_text(W//2, H//2, text=f"Profil üretilemedi:\n{ex}",
                           fill=ERR, font=("Segoe UI", 9))
            return
        s = 0.8*min(W, H)/da
        cx, cy = W/2, H/2

        def P(p):
            return (cx + p[0]*s, cy - p[1]*s)
        flat = []
        for p in pts:
            flat.extend(P(p))
        flat.extend(P(pts[0]))
        cv.create_line(*flat, fill=ACC, width=2)
        d = m_t*z
        rr = d/2*s
        cv.create_oval(cx-rr, cy-rr, cx+rr, cy+rr, outline=OK, dash=(4, 3))
        if bore > 0:
            rb_ = bore/2*s
            cv.create_oval(cx-rb_, cy-rb_, cx+rb_, cy+rb_, outline=WARN, width=2)
        cv.create_text(8, 8, anchor="nw", fill="#c8d2e0", font=("Consolas", 8),
                       text=f"mt={m_t:.4f}  d={d:.2f}\nda={da:.2f}  df={df:.2f}")

    for _e in (m3d_m, m3d_z, m3d_x, m3d_beta, m3d_j, m3d_bore):
        _e.bind("<KeyRelease>", draw_m3d_preview)
    m3d_mtype_cb.bind("<<ComboboxSelected>>", draw_m3d_preview)
    m3d_preview.bind("<Configure>", draw_m3d_preview)

    m3d_info.insert(
        "1.0",
        "Değerleri elle gir (m, z, x, β, b, j, delik) ve doğrudan STL/STEP üret — "
        "önce HESAPLA yapmana gerek yok. İstersen üstteki listeden bir kademe/dişli "
        "seçip 'Doldur'a basarak o kademenin değerlerini alanlara kopyalayabilirsin, "
        "sonra dilediğin gibi değiştirebilirsin.\n\n"
        "NOT: Konik/worm gerçek koni/vida geometrisi burada YOK — sadece düz/helisel "
        "silindirik dişli üretiliyor (β=0 düz, β≠0 helisel).\n\n"
        "MODÜL TİPİ: Helisel dişlide modül standart olarak NORMAL kesitte (mn, kesici "
        "takım modülü) verilir; hazır dişli/katalog eşleştireceksen bunu kullan. "
        "'alın (mt)' seçersen değer doğrudan alın kesitine uygulanır. β=0'da ikisi aynıdır."
    )
    m3d_btns = ttk.Frame(tab_3d); m3d_btns.pack(fill="x", padx=4, pady=(0, 6))

    def _set_entry(e, val):
        e.delete(0, "end")
        e.insert(0, str(val))

    def do_fill_from_stage():
        res = state["res"]
        if not res or not m3d_var.get():
            messagebox.showwarning("Seçim yok", "Önce HESAPLA'ya bas ve bir kademe/dişli seç.")
            return
        t = m3d_var.get()
        k = int(t.split()[1]) - 1
        r = res['results'][k]
        which = "pinyon" if "Pinyon" in t else "cark"
        params = stage_gear_profile_params(r, which)
        if params is None:
            messagebox.showwarning("Desteklenmiyor",
                                   "Worm kademesi için otomatik doldurma yok — "
                                   "değerleri elle gir.")
            return
        # kademe hesabı ALIN (transverse) modül verir -> seçici de öyle olmalı,
        # aksi halde mn->mt dönüşümü ikinci kez uygulanır.
        m3d_mtype.set("alın (mt)")
        _set_entry(m3d_m, f"{params['m']:.4f}")
        _set_entry(m3d_z, params['z'])
        _set_entry(m3d_x, params['x'])
        _set_entry(m3d_beta, f"{params['beta']:.2f}")
        _set_entry(m3d_width, f"{params['width']:.2f}")
        _set_entry(m3d_j, params['j'])
        _set_entry(m3d_bore, params['bore_suggest'])
        draw_m3d_preview()
        if r.gtype == "konik":
            messagebox.showinfo("Konik — eşdeğer değerler",
                                "Bu değerler Tredgold EŞDEĞERİ düz/helisel dişliye ait "
                                "(gerçek koni açısı yok, temsili).")

    ttk.Button(m3d_fill, text="⬇ Doldur", command=do_fill_from_stage).pack(side="left", padx=6)

    def _read_3d_form():
        m_in = float(m3d_m.get())
        z = int(float(m3d_z.get()))
        x = float(m3d_x.get())
        beta = float(m3d_beta.get())
        width = float(m3d_width.get())
        j = float(m3d_j.get())
        bore = max(0.0, float(m3d_bore.get()))
        if m_in <= 0 or z < 5 or width <= 0:
            raise ValueError("m>0, z≥5 ve genişlik>0 olmalı.")
        # Profil ALIN (transverse) kesitte çiziliyor. Helisel dişlide modül
        # standart olarak NORMAL kesitte verilir (kesici takım modülü) ->
        # mt = mn/cos β. β=0'da ikisi aynıdır.
        if m3d_mtype.get().startswith("normal"):
            m_t = m_in/math.cos(math.radians(beta))
        else:
            m_t = m_in
        return m_t, z, x, beta, width, j, bore, m_in

    def _read_params_for_save():
        try:
            m, z, x, beta, width, j, bore, m_in = _read_3d_form()
        except Exception as ex:
            messagebox.showerror("Geçersiz değer", f"Girdileri kontrol et:\n{ex}")
            return None
        tag = "mn" if m3d_mtype.get().startswith("normal") else "mt"
        name = f"disli_{tag}{m_in:g}_z{z}_b{beta:g}"
        return m, z, x, beta, width, j, bore, name

    m3d_prog = ttk.Progressbar(m3d_btns, mode="determinate", length=160)
    m3d_prog_lbl = ttk.Label(m3d_btns, text="")

    def do_save_stl3d():
        params = _read_params_for_save()
        if not params:
            return
        m, z, x, beta, width, j, bore, name = params
        try:
            tris, da, df = gear_solid_triangles(m, z, x, j, width, beta_deg=beta, bore=bore)
        except ValueError as ex:
            messagebox.showerror("Geçersiz geometri", str(ex))
            set_status(f"3B model hatası: {ex}", "error")
            return
        p = filedialog.asksaveasfilename(defaultextension=".stl", initialfile=name + ".stl",
                                         filetypes=[("STL", "*.stl")],
                                         initialdir=dlg_dir("model3d"))
        if not p:
            return
        remember_dir("model3d", p)
        write_stl_binary(tris, p, name=name)
        messagebox.showinfo("Kaydedildi", f"{p}\n\n{len(tris)} üçgen.")
        set_status(f"STL kaydedildi: {p} ({len(tris)} üçgen)", "ok")

    def do_save_step3d():
        params = _read_params_for_save()
        if not params:
            return
        m, z, x, beta, width, j, bore, name = params
        try:
            faces, da, df = gear_solid_step_faces(m, z, x, j, width, beta_deg=beta, bore=bore)
        except ValueError as ex:
            messagebox.showerror("Geçersiz geometri", str(ex))
            set_status(f"3B model hatası: {ex}", "error")
            return
        p = filedialog.asksaveasfilename(defaultextension=".step", initialfile=name + ".step",
                                         filetypes=[("STEP", "*.step;*.stp")],
                                         initialdir=dlg_dir("model3d"))
        if not p:
            return
        remember_dir("model3d", p)
        m3d_prog['value'] = 0
        m3d_prog.pack(side="left", padx=(10, 4))
        m3d_prog_lbl.pack(side="left")
        root.config(cursor="watch")

        def _cb(done, total):
            if total:
                m3d_prog['value'] = 100.0*done/total
                m3d_prog_lbl.configure(text=f"{done}/{total}")
            root.update_idletasks()

        try:
            stats = write_step_facetted(faces, p, source_name=name, progress_cb=_cb)
        finally:
            root.config(cursor="")
            m3d_prog.pack_forget()
            m3d_prog_lbl.pack_forget()
        kind = "kapalı katı (solid)" if stats['is_closed'] else "açık kabuk (shell)"
        messagebox.showinfo("Kaydedildi", f"{p}\n\n{stats['n_faces']} yüz, {kind}.")
        set_status(f"STEP kaydedildi: {p} ({stats['n_faces']} yüz, {kind})", "ok")

    ttk.Button(m3d_btns, text="💾 STL kaydet", command=do_save_stl3d).pack(side="left", padx=4)
    ttk.Button(m3d_btns, text="💾 STEP kaydet", command=do_save_step3d).pack(side="left", padx=4)

    tab_flow, cv_flow = add_canvas_tab("  ➡ Akış  ")
    canvas_toolkit(cv_flow, lambda: draw_flow(), "akis")

    # --- ÖZELLİK 16: Duyarlılık sekmesi ---
    tab_sens = ttk.Frame(nb); nb.add(tab_sens, text="  📈 Duyarlılık  ")
    stop = ttk.Frame(tab_sens); stop.pack(fill="x", pady=2)
    ttk.Label(stop, text="Kademe:").pack(side="left", padx=4)
    sens_stage = tk.StringVar()
    sens_stage_cb = ttk.Combobox(stop, textvariable=sens_stage, width=10,
                                 state="readonly")
    sens_stage_cb.pack(side="left")
    ttk.Label(stop, text="  Tarama:").pack(side="left", padx=4)
    sens_kind = tk.StringVar(value=list(SWEEPS.keys())[0])
    sens_cb = ttk.Combobox(stop, textvariable=sens_kind, width=36,
                           values=list(SWEEPS.keys()), state="readonly")
    sens_cb.pack(side="left")
    cv_sens = tk.Canvas(tab_sens, bg=CVBG, highlightthickness=0)
    cv_sens.pack(fill="both", expand=True)
    canvas_toolkit(cv_sens, lambda: draw_sens(), "duyarlilik")

    # --- ÖZELLİK 1/9/10: Arama sekmesi ---
    tab_srch = ttk.Frame(nb); nb.add(tab_srch, text="  🔍 Ara  ")
    sr_top = ttk.Frame(tab_srch); sr_top.pack(fill="x", pady=3)
    ttk.Label(sr_top, text="Amaç:").pack(side="left", padx=4)
    obj_var = tk.StringVar(value="koaksiyel")
    ttk.Combobox(sr_top, textvariable=obj_var, width=14, state="readonly",
                 values=["koaksiyel", "min_hacim", "max_verim", "oran_hassas"]
                 ).pack(side="left")
    srch_prog = ttk.Progressbar(sr_top, mode="determinate", length=200)
    srch_prog_lbl = ttk.Label(sr_top, text="")
    txt_srch = scrolledtext.ScrolledText(tab_srch, wrap="none", font=("Consolas", 9),
                                         bg=CVBG, fg="#d8e0ea")
    txt_srch.pack(fill="both", expand=True)

    # --- Karşılaştır sekmesi (çoklu senaryo) ---
    tab_cmp = ttk.Frame(nb); nb.add(tab_cmp, text="  ⚖ Karşılaştır  ")
    cmp_left = ttk.Frame(tab_cmp, width=200); cmp_left.pack(side="left", fill="y", padx=4, pady=4)
    cmp_left.pack_propagate(False)
    ttk.Label(cmp_left, text="Senaryolar", style="CardHead.TLabel").pack(anchor="w")
    cmp_list = tk.Listbox(cmp_left, bg=CVBG, fg="#d8e0ea", selectmode="extended",
                          selectbackground=ACC, exportselection=False)
    cmp_list.pack(fill="both", expand=True, pady=3)
    cmp_btns = ttk.Frame(cmp_left); cmp_btns.pack(fill="x")
    txt_cmp = scrolledtext.ScrolledText(tab_cmp, wrap="none", font=("Consolas", 9),
                                        bg=CVBG, fg="#d8e0ea")
    txt_cmp.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=4)

    state = {"res": None, "best": None, "scenarios": []}   # scenarios: [(ad, res), ...]

    # ---------------- ÇİZİM: şema ----------------
    def draw_schematic(*_):
        cv = cv_sch
        cv.delete("all")
        res = state["res"]
        W, H = cv.winfo_width(), cv.winfo_height()
        if not res or W < 50:
            cv.create_text(max(W//2, 100), max(H//2, 60), text="Önce HESAPLA",
                           fill="#667", font=("Segoe UI", 12))
            return
        rs = res['results']
        y_sh = [0.0]
        sign = 1
        for r in rs:
            y_sh.append(y_sh[-1] + sign*r.layout_off)
            sign *= -1
        xs = []
        x = max(rs[0].da1, rs[0].da2)/2 + 10
        for k, r in enumerate(rs):
            if k > 0:
                x += (max(rs[k-1].da1, rs[k-1].da2) + max(r.da1, r.da2))/2 + 15
            xs.append(x)
        w_mm = xs[-1] + max(rs[-1].da1, rs[-1].da2)/2 + 10
        ys = []
        for k, r in enumerate(rs):
            ys += [y_sh[k] - r.da1/2, y_sh[k] + r.da1/2,
                   y_sh[k+1] - r.da2/2, y_sh[k+1] + r.da2/2]
        y_min, y_max = min(ys), max(ys)
        s = min((W-70)/max(w_mm, 1), (H-80)/max(y_max - y_min, 1))

        def px(v): return 35 + v*s
        def py(v): return 40 + (v - y_min)*s

        for k, ysh in enumerate(y_sh):
            cv.create_line(20, py(ysh), W-20, py(ysh), fill="#3a4150")
            cv.create_text(24, py(ysh)-9, text=f"mil {k}", fill="#5a6373",
                           font=("Segoe UI", 7), anchor="w")
        COL = {"duz": "#4ea1ff", "helisel": "#57d6a0", "konik": "#c792ea",
               "worm": "#ffa657"}
        for k, r in enumerate(rs):
            xc, yp, yg = xs[k], y_sh[k], y_sh[k+1]
            col = COL[r.gtype]
            if r.gtype == "worm":
                Lw = 10*r.mn
                cv.create_rectangle(px(xc-Lw/2), py(yp-r.da1/2), px(xc+Lw/2),
                                    py(yp+r.da1/2), outline=col, width=2)
                cv.create_text(px(xc), py(yp-r.da1/2)-8, text=f"vida z1={r.z1}",
                               fill=col, font=("Segoe UI", 7))
            elif r.gtype == "konik":
                # pinyon: koni (üçgen), çark: ayrıt görünüş (dikdörtgen)
                cv.create_polygon(px(xc-r.b/2), py(yp-r.da1/2), px(xc+r.b/2), py(yp),
                                  px(xc-r.b/2), py(yp+r.da1/2),
                                  outline=col, fill="", width=2)
                cv.create_text(px(xc), py(yp-r.da1/2)-8,
                               text=f"konik pinyon z1={r.z1}", fill=col,
                               font=("Segoe UI", 7))
            else:
                cv.create_oval(px(xc-r.da1/2), py(yp-r.da1/2), px(xc+r.da1/2),
                               py(yp+r.da1/2), outline=col, dash=(3, 2))
                cv.create_oval(px(xc-r.d01/2), py(yp-r.d01/2), px(xc+r.d01/2),
                               py(yp+r.d01/2), outline=col, width=2)
                cv.create_text(px(xc), py(yp), text=f"z={r.z1}\nd={r.d01:.0f}",
                               fill="#c8d2e0", font=("Segoe UI", 7))
            # çark
            if r.gtype == "konik":
                cv.create_rectangle(px(xc-r.b/2), py(yg-r.da2/2), px(xc+r.b/2),
                                    py(yg+r.da2/2), outline=col, width=2)
                cv.create_text(px(xc), py(yg), text=f"z={r.z2}\n⊥90°",
                               fill="#c8d2e0", font=("Segoe UI", 7))
            else:
                cv.create_oval(px(xc-r.da2/2), py(yg-r.da2/2), px(xc+r.da2/2),
                               py(yg+r.da2/2), outline=col, dash=(3, 2))
                cv.create_oval(px(xc-r.d02/2), py(yg-r.d02/2), px(xc+r.d02/2),
                               py(yg+r.d02/2), outline=col, width=2)
                cv.create_text(px(xc), py(yg), text=f"z={r.z2}\nd={r.d02:.0f}",
                               fill="#c8d2e0", font=("Segoe UI", 7))
            cv.create_line(px(xc), py(yp), px(xc), py(yg), fill="#8892a4", dash=(2, 2))
            lbl = f"R={r.R_cone:.0f}" if r.gtype == "konik" else f"a={r.a:.1f}"
            cv.create_text(px(xc)+4, (py(yp)+py(yg))/2, text=lbl, fill="#8892a4",
                           font=("Segoe UI", 7), anchor="w")

        cv.create_text(28, py(y_sh[0])+12, text=f"▶ GİRİŞ n={res['n_in']:.0f}",
                       fill="#57d6a0", font=("Segoe UI", 8, "bold"), anchor="w")
        cv.create_text(W-28, py(y_sh[-1])+12, text=f"ÇIKIŞ n={rs[-1].n_out:.0f} ▶",
                       fill="#ff6b6b", font=("Segoe UI", 8, "bold"), anchor="e")
        coax = res.get('coax') or {}
        msg = coax.get('msg', '')
        colr = "#57d6a0" if coax.get('feasible') else "#ffa657"
        cv.create_text(W//2, H-12, text=("✓ " if coax.get('feasible') else "⚠ ") + msg,
                       fill=colr, font=("Segoe UI", 8, "bold"), width=W-40)
        if any(r.gtype == "konik" for r in rs):
            cv.create_text(W//2, 14, text="konik kademe var — görünüm açılmıştır "
                                          "(eksen 90° döner)",
                           fill="#c792ea", font=("Segoe UI", 8))

    # ---------------- ÇİZİM: profil ----------------
    def draw_profile(*_):
        cv = cv_prof
        cv.delete("all")
        res = state["res"]
        W, H = cv.winfo_width(), cv.winfo_height()
        if not res or W < 50 or not prof_var.get():
            return
        try:
            t = prof_var.get()
            k = int(t.split()[1]) - 1
            r = res['results'][k]
            is_pin = "Pinyon" in t
        except Exception:
            return
        if r.gtype == "worm":
            cv.create_text(W//2, H//2, text="Worm profili desteklenmiyor\n"
                                            "(vida helisi 3B — .scad dosyasına bak)",
                           fill="#ffa657", font=("Segoe UI", 11))
            return
        if r.gtype == "konik":
            m_eff = r.mt
            z = int(round(r.ze1)) if is_pin else int(round(r.z2/math.cos(
                math.radians(r.delta02))))
            x = 0.0
            hdr_extra = "  [Tredgold eşdeğer düz dişli]"
        else:
            m_eff = r.mt if r.gtype == "helisel" else r.mn
            z = r.z1 if is_pin else r.z2
            x = r.x1 if is_pin else r.x2
            hdr_extra = ""
        z = max(z, 5)
        pts, da, df = _involute_gear_points(m_eff, z, x=x, j=r.backlash, steps=10)
        s = 0.85*min(W, H)/da
        cx, cy = W/2, H/2

        def P(p):
            return (cx + p[0]*s, cy - p[1]*s)
        flat = []
        for p in pts:
            flat.extend(P(p))
        flat.extend(P(pts[0]))
        cv.create_line(*flat, fill="#4ea1ff", width=2)
        d = m_eff*z
        db = d*math.cos(ALPHA_N)
        for dia, col in [(d, "#57d6a0"), (db, "#ffa657"), (df, "#ff6b6b")]:
            rr = dia/2*s
            cv.create_oval(cx-rr, cy-rr, cx+rr, cy+rr, outline=col, dash=(4, 3))
        sa = tip_thickness(m_eff, z, x, da, 0 if r.gtype != "helisel" else r.beta)
        cv.create_text(10, 10, anchor="nw", fill="#c8d2e0", font=("Consolas", 9),
                       text=(f"m={m_eff:.3f}  z={z}  x={x:+.2f}  j={r.backlash:.2f}{hdr_extra}\n"
                             f"d={d:.2f}  db={db:.2f}  da={da:.2f}  df={df:.2f}\n"
                             f"sa={sa:.3f} mm (sınır {r.sa_lim:.2f})   εα={r.eps_a:.3f}\n"
                             f"— taksimat(yeşil) · temel(turuncu) · dip(kırmızı)"))
        if x > 0:
            cv.create_text(10, H-22, anchor="sw", fill="#57d6a0", font=("Segoe UI", 9),
                           text="x>0: diş dibi kalın, alttan kesilme yok, diş ucu sivrilir")
        elif x < 0:
            cv.create_text(10, H-22, anchor="sw", fill="#ff6b6b", font=("Segoe UI", 9),
                           text="x<0: diş dibi ince — alttan kesilme riski")

    # ---------------- ÇİZİM: akış ----------------
    def draw_flow(*_):
        cv = cv_flow
        cv.delete("all")
        res = state["res"]
        W, H = cv.winfo_width(), cv.winfo_height()
        if not res or W < 50:
            return
        rs = res['results']
        n_box = len(rs) + 2
        bw = min(130, (W-40)/n_box - 25)
        bh = 54
        gap = ((W-40) - n_box*bw)/(n_box-1) if n_box > 1 else 0
        y = H/2
        Tmax = max([r.T2 for r in rs] + [rs[0].T1])
        COL = {"duz": "#4ea1ff", "helisel": "#57d6a0", "konik": "#c792ea",
               "worm": "#ffa657"}

        def box(i, title, sub, col):
            x0 = 20 + i*(bw+gap)
            cv.create_rectangle(x0, y-bh/2, x0+bw, y+bh/2, outline=col, width=2)
            cv.create_text(x0+bw/2, y-10, text=title, fill=col,
                           font=("Segoe UI", 9, "bold"))
            cv.create_text(x0+bw/2, y+10, text=sub, fill="#c8d2e0",
                           font=("Segoe UI", 8))
            return x0, x0+bw

        def arrow(xf, xt, n, T):
            wd = 1 + 4*(T/Tmax if Tmax else 0)
            cv.create_line(xf, y, xt, y, fill="#8892a4", width=wd, arrow=tk.LAST)
            xm = (xf+xt)/2
            cv.create_text(xm, y-18, text=f"n={n:.0f}", fill="#57d6a0",
                           font=("Segoe UI", 8))
            cv.create_text(xm, y+18, text=f"T={T/1000:.2f} N·m", fill="#ffa657",
                           font=("Segoe UI", 8))

        _, xr = box(0, "MOTOR", f"{res['P_in']:.2f} kW", "#57d6a0")
        prev = xr
        for k, r in enumerate(rs):
            x0, x1 = box(k+1, f"K{k+1}·{r.gtype}", f"i={r.i_real:.2f} η={r.eta:.3f}",
                         COL[r.gtype])
            arrow(prev, x0, r.n_in, r.T1)
            prev = x1
        x0, _ = box(n_box-1, "ÇIKIŞ", f"{rs[-1].P_out:.2f} kW", "#ff6b6b")
        arrow(prev, x0, rs[-1].n_out, rs[-1].T2)
        cv.create_text(W/2, H-16, fill="#667", font=("Segoe UI", 8),
                       text=f"Ok kalınlığı ∝ moment  |  toplam η={res['eta_total']:.4f}")

    # ---------------- ÇİZİM: duyarlılık (ÖZELLİK 16) ----------------
    def _plot_xy(cv, data, title):
        """Bağımsız XY çizer (matplotlib gerekmez)."""
        cv.delete("all")
        W, H = cv.winfo_width(), cv.winfo_height()
        if W < 60 or H < 60:
            return
        L, Rr, Tp, Bt = 60, 20, 40, 46
        xs = data["x"]
        series = [(nm, [v for v in ys]) for nm, ys in data["series"]]
        allv = [v for _, ys in series for v in ys
                if v == v and v not in (float('inf'), float('-inf'))]
        if not allv or not xs:
            return
        ymin, ymax = min(allv), max(allv)
        if ymax - ymin < 1e-9:
            ymax = ymin + 1.0
        pad = (ymax - ymin)*0.08
        ymin -= pad; ymax += pad
        xmin, xmax = min(xs), max(xs)

        def PX(v): return L + (v - xmin)/(xmax - xmin + 1e-12)*(W - L - Rr)
        def PY(v): return H - Bt - (v - ymin)/(ymax - ymin)*(H - Tp - Bt)

        # ızgara + eksen
        for k in range(6):
            yv = ymin + (ymax-ymin)*k/5
            cv.create_line(L, PY(yv), W-Rr, PY(yv), fill="#242832")
            cv.create_text(L-6, PY(yv), text=f"{yv:.2f}", fill="#8892a4",
                           font=("Consolas", 7), anchor="e")
            xv = xmin + (xmax-xmin)*k/5
            cv.create_line(PX(xv), Tp, PX(xv), H-Bt, fill="#242832")
            cv.create_text(PX(xv), H-Bt+6, text=f"{xv:.2f}", fill="#8892a4",
                           font=("Consolas", 7), anchor="n")
        cv.create_line(L, Tp, L, H-Bt, fill="#5a6373")
        cv.create_line(L, H-Bt, W-Rr, H-Bt, fill="#5a6373")
        cv.create_text(W/2, 16, text=title, fill="#4ea1ff",
                       font=("Segoe UI", 10, "bold"))
        cv.create_text(W/2, H-14, text=data["xlabel"], fill="#8892a4",
                       font=("Segoe UI", 8))
        cols = ["#4ea1ff", "#57d6a0", "#ffa657"]
        for si, (nm, ys) in enumerate(series):
            pts = []
            for xv, yv in zip(xs, ys):
                if yv != yv:
                    continue
                pts.extend([PX(xv), PY(yv)])
            if len(pts) >= 4:
                cv.create_line(*pts, fill=cols[si % 3], width=2)
            cv.create_line(W-Rr-120, Tp+4+si*13, W-Rr-100, Tp+4+si*13,
                           fill=cols[si % 3], width=2)
            cv.create_text(W-Rr-96, Tp+4+si*13, text=nm, fill=cols[si % 3],
                           font=("Segoe UI", 8), anchor="w")

    def draw_sens(*_):
        cv = cv_sens
        res = state["res"]
        if not res:
            cv.delete("all")
            cv.create_text(cv.winfo_width()//2 or 150, cv.winfo_height()//2 or 60,
                           text="Önce HESAPLA", fill="#667", font=("Segoe UI", 12))
            return
        try:
            k = int(sens_stage.get().split()[-1]) - 1
        except Exception:
            k = 0
        name = sens_kind.get()
        spec = SWEEPS[name]
        gt = res['results'][k].gtype
        if gt not in spec["gtypes"]:
            cv.delete("all")
            cv.create_text(cv.winfo_width()//2, cv.winfo_height()//2,
                           text=f"Bu tarama '{gt}' kademesine uygulanmaz.\n"
                                f"Uygun tip: {', '.join(spec['gtypes'])}",
                           fill="#ffa657", font=("Segoe UI", 11))
            return
        try:
            data = sweep_stage(res['cfg'], k, name)
            _plot_xy(cv, data, f"Kademe {k+1} — {name}")
        except Exception as ex:
            cv.delete("all")
            cv.create_text(cv.winfo_width()//2, cv.winfo_height()//2,
                           text=f"Tarama hatası: {ex}", fill="#ff6b6b")

    def redraw_all():
        draw_schematic(); draw_profile(); draw_flow(); draw_sens()

    for c, fn in [(cv_sch, draw_schematic), (cv_prof, draw_profile),
                  (cv_flow, draw_flow), (cv_sens, draw_sens)]:
        c.bind("<Configure>", lambda e, f=fn: f())
    prof_combo.bind("<<ComboboxSelected>>", draw_profile)
    sens_cb.bind("<<ComboboxSelected>>", draw_sens)
    sens_stage_cb.bind("<<ComboboxSelected>>", draw_sens)
    nb.bind("<<NotebookTabChanged>>", lambda e: redraw_all())

    # ---------------- config ----------------
    def collect_config():
        stages = []
        for sw in stage_widgets:
            t = sw['t'].get()
            sc = dict(gtype=t, material=sw['m'].get(), i_stage=float(sw['i'].get()),
                      K0=K0_TABLE[app_var.get()])
            if t in ("duz", "helisel"):
                sc['x1'] = float(sw['x'].get())
                sc['x2'] = float(sw['x2'].get())
            if t == "helisel":
                sc['beta'] = float(sw['b'].get())
            if t == "worm":
                sc['z1'] = int(sw['z1'].get())
                sc['q'] = float(sw['q'].get())
            if t == "konik":
                sc['delta_axis'] = float(sw['da'].get())
                sc['phi_m'] = float(sw['pm'].get())
            stages.append(sc)
        return dict(P_in=float(e_P.get()), n_in=float(e_n.get()),
                    i_total=float(e_i.get()), n_stages=ns_var.get(),
                    lubricated=lub_var.get(), backlash=float(e_j.get()),
                    bed_size=float(e_bed.get()), sigma_em_mil=float(e_sig.get()),
                    E_shaft=float(e_Emil.get()), S=float(e_S.get()),
                    Lh_target=float(e_Lh.get()), T_amb=25.0,
                    bore_type=bore_var.get(), stages=stages)

    def apply_config(cfg):
        for e, key in [(e_P, 'P_in'), (e_n, 'n_in'), (e_i, 'i_total'),
                       (e_j, 'backlash'), (e_bed, 'bed_size'), (e_sig, 'sigma_em_mil'),
                       (e_Emil, 'E_shaft'), (e_S, 'S'), (e_Lh, 'Lh_target')]:
            e.delete(0, "end")
            e.insert(0, str(cfg.get(key, "")))
        lub_var.set(cfg.get('lubricated', False))
        bore_var.set(cfg.get('bore_type', 'kama'))
        ns_var.set(cfg.get('n_stages', 2))
        build_stage_rows()
        for sw, sc in zip(stage_widgets, cfg.get('stages', [])):
            sw['t'].set(sc.get('gtype', 'duz'))
            sw['m'].set(sc.get('material', 'PETG'))
            for e, key, d in [(sw['i'], 'i_stage', 3.0), (sw['b'], 'beta', 15.0),
                              (sw['x'], 'x1', 0.0), (sw['x2'], 'x2', 0.0),
                              (sw['z1'], 'z1', 2), (sw['q'], 'q', 10.0),
                              (sw['da'], 'delta_axis', 90.0), (sw['pm'], 'phi_m', 10.0)]:
                e.delete(0, "end")
                e.insert(0, str(sc.get(key, d)))

    def _tag_report(widget):
        widget.tag_configure("warn", foreground=WARN)
        widget.tag_configure("err", foreground=ERR)
        widget.tag_configure("okline", foreground=OK)
        content = widget.get("1.0", "end-1c").split("\n")
        for i, line in enumerate(content, start=1):
            if "ÇALIŞMAZ" in line or "❌" in line:
                widget.tag_add("err", f"{i}.0", f"{i}.end")
            elif "⚠" in line or "UYARI" in line:
                widget.tag_add("warn", f"{i}.0", f"{i}.end")
            elif "✓" in line or "TAMAM" in line:
                widget.tag_add("okline", f"{i}.0", f"{i}.end")

    def do_calc():
        try:
            cfg = collect_config()
            res = calc_reducer(cfg)
            state["res"] = res
            txt.delete("1.0", "end")
            txt.insert("1.0", report_full(res))
            _tag_report(txt)
            items = []
            for k, r in enumerate(res['results'], 1):
                items += [f"Kademe {k} - Pinyon (z={r.z1})",
                          f"Kademe {k} - Çark (z={r.z2})"]
            prof_combo['values'] = items
            if items:
                prof_var.set(items[0])
            m3d_combo['values'] = items
            if items:
                m3d_var.set(items[0])
            sens_stage_cb['values'] = [f"Kademe {k+1}"
                                       for k in range(len(res['results']))]
            sens_stage.set("Kademe 1")
            redraw_all()
            n_warn = sum(len(r.warnings) for r in res['results'])
            set_status(f"Hesaplandı: {len(res['results'])} kademe, toplam η={res['eta_total']:.4f}"
                       + (f", {n_warn} uyarı" if n_warn else ""),
                       "warn" if n_warn else "ok")
        except Exception as ex:
            messagebox.showerror("Hata", f"Hesap hatası:\n{ex}")
            set_status(f"Hesap hatası: {ex}", "error")

    def do_search():
        if not state["res"]:
            messagebox.showwarning("Önce hesapla", "Önce 'HESAPLA'ya bas.")
            return
        cfg = collect_config()
        q = _queue.Queue()
        srch_btn.configure(state="disabled")
        srch_prog['value'] = 0
        srch_prog.pack(side="left", padx=(10, 4))
        srch_prog_lbl.pack(side="left")
        txt_srch.delete("1.0", "end")
        txt_srch.insert("1.0", "Aranıyor...\n")
        set_status("Tasarım aranıyor (arka planda)...")

        def worker():
            try:
                def cb(idx, total):
                    q.put(("progress", idx, total))
                best = search_designs(cfg, objective=obj_var.get(), n_best=5, progress=cb)
                q.put(("done", best))
            except Exception as ex:
                q.put(("error", str(ex)))

        def finish():
            srch_btn.configure(state="normal")
            srch_prog.pack_forget()
            srch_prog_lbl.pack_forget()

        def poll():
            try:
                while True:
                    item = q.get_nowait()
                    if item[0] == "progress":
                        _, idx, total = item
                        if total:
                            srch_prog['value'] = 100.0*idx/total
                            srch_prog_lbl.configure(text=f"{idx}/{total}")
                    elif item[0] == "done":
                        best = item[1]
                        state["best"] = best
                        txt_srch.delete("1.0", "end")
                        txt_srch.insert("1.0", report_search(best, obj_var.get()))
                        nb.select(tab_srch)
                        finish()
                        set_status(f"Arama tamam: {len(best)} sonuç bulundu.", "ok")
                        return
                    elif item[0] == "error":
                        messagebox.showerror("Hata", f"Arama hatası:\n{item[1]}")
                        finish()
                        set_status(f"Arama hatası: {item[1]}", "error")
                        return
            except _queue.Empty:
                pass
            root.after(80, poll)

        threading.Thread(target=worker, daemon=True).start()
        root.after(80, poll)

    def apply_best():
        if not state["best"]:
            messagebox.showwarning("Arama yok", "Önce 'TASARIM ARA'ya bas.")
            return
        apply_config(state["best"][0]['cfg'])
        do_calc()
        messagebox.showinfo("Uygulandı", "En iyi tasarım forma yüklendi ve hesaplandı.")

    srch_btn = ttk.Button(sr_top, text="🔍 TASARIM ARA", command=do_search)
    srch_btn.pack(side="left", padx=6)
    ttk.Button(sr_top, text="✔ En iyiyi uygula", command=apply_best).pack(side="left")

    def do_cad():
        if not state["res"]:
            messagebox.showwarning("Önce hesapla", "Önce 'HESAPLA'ya bas.")
            return
        folder = filedialog.askdirectory(title="CAD dosyaları nereye?", initialdir=dlg_dir("cad"))
        if not folder:
            return
        remember_dir("cad", folder)
        files = export_all_cad(state["res"], folder, bore_type=bore_var.get())
        messagebox.showinfo("CAD üretildi",
                            "\n".join(os.path.basename(f) for f in files)
                            + "\n\nOpenSCAD'de .scad aç -> F6 -> STL export.")
        set_status(f"CAD üretildi: {len(files)} dosya -> {folder}", "ok")

    def do_save_report():
        if not state["res"]:
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                         filetypes=[("Metin", "*.txt")],
                                         initialdir=dlg_dir("report"))
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(report_full(state["res"]))
            remember_dir("report", p)
            set_status(f"Rapor kaydedildi: {p}", "ok")

    def do_save_json():
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                         filetypes=[("JSON", "*.json")],
                                         initialdir=dlg_dir("design"))
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(collect_config(), f, indent=2, ensure_ascii=False)
            remember_dir("design", p)
            _add_recent_file(p)
            set_status(f"Tasarım kaydedildi: {p}", "ok")
        except Exception as ex:
            messagebox.showerror("Hata", str(ex))
            set_status(f"Kaydetme hatası: {ex}", "error")

    def _load_json_path(p):
        try:
            with open(p, encoding="utf-8") as f:
                apply_config(json.load(f))
            remember_dir("design", p)
            _add_recent_file(p)
            set_status(f"Tasarım yüklendi: {p} — HESAPLA'ya bas.", "ok")
        except Exception as ex:
            messagebox.showerror("Hata", str(ex))
            set_status(f"Yükleme hatası: {ex}", "error")

    def do_load_json():
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")],
                                       initialdir=dlg_dir("design"))
        if p:
            _load_json_path(p)

    def _add_recent_file(p):
        rf = ui_cfg.setdefault("recent_files", [])
        if p in rf:
            rf.remove(p)
        rf.insert(0, p)
        del rf[8:]

    def do_open_recent():
        rf = [p for p in ui_cfg.get("recent_files", []) if os.path.exists(p)]
        if not rf:
            messagebox.showinfo("Son dosyalar", "Henüz kayıtlı/erişilebilir dosya yok.")
            return
        m = tk.Menu(root, tearoff=0)
        for p in rf:
            m.add_command(label=os.path.basename(p), command=lambda pp=p: _load_json_path(pp))
        m.tk_popup(root.winfo_pointerx(), root.winfo_pointery())

    def do_reset():
        if not messagebox.askyesno("Sıfırla", "Tüm girdiler varsayılan değerlere dönecek. "
                                   "Emin misin?"):
            return
        apply_config(default_cfg())
        set_status("Girdiler varsayılana sıfırlandı.", "ok")

    # ---------------- KARŞILAŞTIR: çoklu senaryo ----------------
    def refresh_scenario_list():
        cmp_list.delete(0, "end")
        for name, _r in state["scenarios"]:
            cmp_list.insert("end", name)

    def do_add_scenario():
        if not state["res"]:
            messagebox.showwarning("Önce hesapla", "Önce 'HESAPLA'ya bas.")
            return
        default_name = f"Senaryo {len(state['scenarios'])+1}"
        name = simpledialog.askstring("Senaryo adı", "Bu senaryoya bir ad ver:",
                                      initialvalue=default_name, parent=root)
        if not name:
            return
        state["scenarios"].append((name, state["res"]))
        refresh_scenario_list()
        set_status(f"Senaryo eklendi: {name} (toplam {len(state['scenarios'])})", "ok")

    def do_remove_scenario():
        sel = list(cmp_list.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del state["scenarios"][i]
        refresh_scenario_list()

    def _scenario_summary_table(scn):
        lines = ["="*100, "ÇOKLU SENARYO ÖZET KARŞILAŞTIRMA", "="*100,
                 f"{'Senaryo':<22}{'P_giriş(kW)':>12}{'i_hedef':>10}{'i_gerçek':>10}{'η_toplam':>10}",
                 "-"*100]
        for name, res in scn:
            lines.append(f"{name:<22}{res['P_in']:>12.3f}{res['i_target']:>10.2f}"
                        f"{res['i_real_total']:>10.2f}{res['eta_total']:>10.4f}")
        lines.append("")
        for name, res in scn:
            lines.append(f"--- {name} ---")
            for k, r in enumerate(res['results'], 1):
                lines.append(f"  K{k} {r.gtype:<8} z1={r.z1:<4} z2={r.z2:<4} "
                             f"mn={r.mn:<7.3f} a={r.a:<8.2f} η={r.eta:.4f}")
            lines.append("")
        return "\n".join(lines)

    def do_compare_selected():
        sel = list(cmp_list.curselection())
        if len(sel) < 2:
            messagebox.showwarning("Seçim yetersiz",
                                   "Karşılaştırmak için en az 2 senaryo seç "
                                   "(Ctrl/Shift ile çoklu seçim).")
            return
        picked = [state["scenarios"][i] for i in sel]
        txt_cmp.delete("1.0", "end")
        if len(picked) == 2:
            (_nA, A), (_nB, B) = picked
            txt_cmp.insert("1.0", compare_report(A, B))
        else:
            txt_cmp.insert("1.0", _scenario_summary_table(picked))
        set_status(f"{len(picked)} senaryo karşılaştırıldı.", "ok")

    ttk.Button(cmp_btns, text="➕ Ekle", command=do_add_scenario).pack(side="left", padx=2, pady=3)
    ttk.Button(cmp_btns, text="🗑 Sil", command=do_remove_scenario).pack(side="left", padx=2)
    ttk.Button(cmp_left, text="⚖ Karşılaştır", command=do_compare_selected).pack(fill="x", pady=4)

    b1f = ttk.Frame(left); b1f.pack(fill="x", pady=(8, 2))
    ttk.Button(b1f, text="▶  HESAPLA", command=do_calc).pack(side="left", padx=2)
    ttk.Button(b1f, text="🔍 TASARIM ARA", command=do_search).pack(side="left", padx=2)
    b2f = ttk.Frame(left); b2f.pack(fill="x", pady=2)
    ttk.Button(b2f, text="🧩 CAD ÜRET", command=do_cad).pack(side="left", padx=2)
    ttk.Button(b2f, text="💾 Rapor", command=do_save_report).pack(side="left", padx=2)
    b3f = ttk.Frame(left); b3f.pack(fill="x", pady=2)
    ttk.Button(b3f, text="💾 Tasarım", command=do_save_json).pack(side="left", padx=2)
    ttk.Button(b3f, text="📂 Aç", command=do_load_json).pack(side="left", padx=2)
    ttk.Button(b3f, text="🕘 Son", command=do_open_recent, width=5).pack(side="left", padx=2)
    b4f = ttk.Frame(left); b4f.pack(fill="x", pady=2)
    ttk.Button(b4f, text="➕ Senaryo olarak ekle", command=do_add_scenario
              ).pack(side="left", padx=2)
    b5f = ttk.Frame(left); b5f.pack(fill="x", pady=(2, 8))
    ttk.Button(b5f, text="🗑 Sıfırla", command=do_reset).pack(side="left", padx=2)

    # ---------------- klavye kısayolları ----------------
    root.bind("<Control-Return>", lambda e: do_calc())
    root.bind("<F5>", lambda e: do_calc())
    root.bind("<Control-s>", lambda e: do_save_json())
    root.bind("<Control-S>", lambda e: do_save_report())
    root.bind("<Control-Shift-S>", lambda e: do_save_report())
    root.bind("<Control-o>", lambda e: do_load_json())

    def on_close():
        ui_cfg["geometry"] = root.geometry()
        _save_ui_cfg(ui_cfg)
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    root.mainloop()


# ================================================================== #
#  BÖLÜM 8 — GİRİŞ NOKTASI
# ================================================================== #

if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--cli" in sys.argv:
        cli()
    else:
        try:
            gui()
        except Exception as e:
            print(f"[GUI açılamadı: {e}]  -> CLI moduna geçiliyor.\n")
            cli()
