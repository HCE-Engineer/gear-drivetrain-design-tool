# -*- coding: utf-8 -*-
"""3B geometri ve kinematik testleri (build123d / OpenCascade ile gerçek katılar).

Ana fikir: parçalar animasyondaki hız oranlarıyla döndürülür ve kavrayan dişliler
arasındaki CAD kesişim hacminin sıfır kaldığı kontrol edilir. Oran veya yön yanlışsa
dişler birbirine girer ve hacim sıfırdan büyük çıkar.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "uygulama"))
motor = pytest.importorskip("motor")      # build123d kurulu değilse atla
import build123d as bd  # noqa: E402


def _hareket(parca, th, ters=False):
    a, s = parca.anim, parca.shape
    if a.get("type") == "rot":
        k = -1 if ters else 1
        s = s.rotate(bd.Axis(tuple(a["origin"]), tuple(a["axis"])), math.degrees(k * a["ratio"] * th))
        if a.get("carrier"):
            s = s.rotate(bd.Axis((0, 0, 0), (0, 0, 1)), math.degrees(a["carrier"] * th))
    elif a.get("type") == "lin":
        v = a["vel"]
        s = s.moved(bd.Location((v[0] * th, v[1] * th, v[2] * th)))
    return s


def _kesisim(a, b):
    toplam = 0.0
    for x in a.solids():
        for y in b.solids():
            r = x.intersect(y)
            if r is not None:
                toplam += sum(z.volume for z in (r.solids() if hasattr(r, "solids") else r))
    return toplam


@pytest.mark.parametrize("tip,param", [
    ("duz", dict(z1=14, z2=29)),
    ("helisel", dict(z1=14, z2=29, beta=20)),
    ("ic", dict(z1=17, z_ring=48)),
    ("konik", dict(z1=14, z2=29)),
    ("kremayer", dict(z1=15, z_rack=18)),
])
def test_kavrayan_dislier_birbirine_girmez(tip, param):
    s = motor.build(tip, param)
    p1, p2 = s.parts[0], s.parts[1]
    for th in (0.0, 0.3):
        assert _kesisim(_hareket(p1, th), _hareket(p2, th)) < 0.5, f"θ={th}"
    # ters yönde döndürmek çakışma yaratmalı: test gerçekten bir şey ölçüyor
    if p2.anim.get("type") == "rot":
        assert _kesisim(_hareket(p1, 0.3), _hareket(p2, 0.3, ters=True)) > 0.5


def test_diferansiyel_virajda_cakismasiz():
    s = motor.build("diferansiyel", dict(turn=30))
    disliler = [p for p in s.parts if "dişli" in p.name.lower() or "pinyon" in p.name.lower()]
    for th in (0.0, 0.4):
        for i in range(len(disliler)):
            for j in range(i + 1, len(disliler)):
                v = _kesisim(_hareket(disliler[i], th), _hareket(disliler[j], th))
                assert v < 0.5, f"{disliler[i].name} ~ {disliler[j].name} θ={th}"


def test_duz_cift_eksen_mesafesi():
    s = motor.build("duz", dict(z1=14, z2=29, m=2, backlash=0))
    assert s.summary["a"] == pytest.approx(2 * (14 + 29) / 2, abs=0.01)


def test_bas_kisaltma_3b_ile_hesap_ayni():
    import hesap
    s = motor.build("duz", dict(z1=17, z2=51, m=2.5, x1=0.4, x2=0.2))
    r = hesap.calc_gear_stage(1, "duz", "PETG", 0.25, 1500, 3.0, x1=0.4, x2=0.2, z1_override=17)
    assert s.summary["k"] == pytest.approx(r.k_short, abs=1e-4)
    assert s.parts[0].info["da"] == pytest.approx(r.da1, abs=0.01)
    assert s.parts[1].info["da"] == pytest.approx(r.da2, abs=0.01)


def test_step_ve_stl_disa_aktarma():
    s = motor.build("duz", dict(z1=14, z2=29, a_bore_d=8, a_bore_type="kama"))
    for fmt in ("step", "stl", "dxf"):
        ad, veri, _ = motor.export_file(s, fmt, 0)
        assert ad.endswith("." + fmt) and len(veri) > 1000


def test_dxf_profili_xy_duzleminde():
    s = motor.build("duz", dict(z1=14, z2=29, width=10))
    bb = s.parts[0].dxf_wire.bounding_box()
    assert abs(bb.min.Z) < 1e-6 and abs(bb.max.Z) < 1e-6


# ------------------------------------------------------------------ #
#  Duyarlılık taraması (README grafikleri)
# ------------------------------------------------------------------ #

def test_profil_kaydirma_taramasi_egilimleri():
    """x1 arttıkça: diş dibi gerilmesi azalır (artmaz), diş ucu kalınlığı azalır."""
    cfg = dict(P_in=0.25, n_in=1500, i_total=9, stages=[
        dict(gtype="helisel", material="PETG", i_stage=3, beta=15),
        dict(gtype="duz", material="PETG", i_stage=3)])
    d = motor.sweep_analysis(cfg, 0, "x1")
    sigma, sa = d["panels"][0]["y"], d["panels"][1]["y"]
    assert all(b <= a + 1e-9 for a, b in zip(sigma, sigma[1:]))
    assert all(b < a for a, b in zip(sa, sa[1:]))
