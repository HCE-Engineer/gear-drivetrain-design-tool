# -*- coding: utf-8 -*-
"""Mukavemet / geometri hesabı testleri (hızlı, CAD gerektirmez).

Referans değerler: çözümlü kitap örnekleri ve el hesabı (bkz. legacy/README.md).
"""
import math

import pytest

import hesap as h


# ------------------------------------------------------------------ #
#  Kitap / el hesabı örnekleri
# ------------------------------------------------------------------ #

def test_konik_cozumlu_ornek():
    """Düz konik dişli: P=5,5 kW, n=960 d/dk, i=4,5, z1=14, m=6, b=30."""
    r = h.calc_bevel_stage(1, "Çelik C45 (ref)", 5.5, 960, 4.5,
                           z1_override=14, m_pref=6, b_pref=30)
    assert r.delta01 == pytest.approx(12.53, abs=0.01)     # tan δ01 = 1/i
    assert r.mt == pytest.approx(5.535, abs=0.001)         # ortalama modül mm
    assert r.Ft == pytest.approx(1412.1, abs=0.1)
    assert r.Fa == pytest.approx(111.5, abs=0.1)
    assert r.Fr == pytest.approx(501.7, abs=0.1)


def test_kavrama_orani_duz_20_60():
    """z = 20 / 60, α = 20°, x = 0  ->  εα = 1,671 (kitap değeri)."""
    m = 1.0
    eps_a, eps_b, _ = h.contact_ratio(20 * m, 60 * m, 22 * m, 62 * m, m, 0.0, 10, 40 * m)
    assert eps_a == pytest.approx(1.671, abs=0.001)
    assert eps_b == 0.0


def test_moment_birimi():
    """T = 9550·P/n  [N·m]  ->  1 kW, 1000 d/dk = 9,55 N·m = 9550 N·mm."""
    assert h._torque_Nmm(1.0, 1000.0) == pytest.approx(9550.0)


@pytest.mark.parametrize("alpha", [0.1, 0.35, 0.6])
def test_evolvent_ters_fonksiyon(alpha):
    assert h.inv_involute(h.involute(alpha)) == pytest.approx(alpha, abs=1e-9)


# ------------------------------------------------------------------ #
#  Örnek redüktör (README / uygulama varsayılanı)
# ------------------------------------------------------------------ #

@pytest.fixture(scope="module")
def ornek():
    return h.calc_reducer(h.default_cfg())


def test_ornek_reduktor_kademe1(ornek):
    r = ornek["results"][0]
    assert (r.z1, r.z2) == (16, 48)
    assert r.mn == 2.5
    assert r.a == pytest.approx(82.82, abs=0.01)


def test_ornek_reduktor_oran_ve_verim(ornek):
    assert ornek["i_real_total"] == pytest.approx(9.0)
    assert 0.8 < ornek["eta_total"] < 1.0


def test_ornek_reduktor_tum_kontroller(ornek):
    assert all(r.root_ok for r in ornek["results"])
    assert all(s.defl_ok and s.slope_ok for s in ornek["shafts"])
    assert all(b.ok and b.L10h >= b.target for b in ornek["bearings"])


def test_raporda_ders_kalintisi_yok(ornek):
    rapor = h.report_full(ornek).lower()
    for kelime in ("puanlama", "hoca", "makel2", "-40 puan"):
        assert kelime not in rapor


# ------------------------------------------------------------------ #
#  Tutarlılık: boyutlandırılan dişli kendi kontrolünü geçmeli
# ------------------------------------------------------------------ #

DURUMLAR = [
    (P, n, i, mat, gt, beta)
    for P, n in ((0.25, 1500), (0.75, 1000), (3.0, 1450), (11.0, 960))
    for i in (2.0, 3.5, 5.0)
    for mat, gt, beta in (("PETG", "duz", 0.0), ("Çelik C45 (ref)", "helisel", 15.0),
                          ("Çelik 42CrMo4 (ref)", "helisel", 25.0))
]


@pytest.mark.parametrize("P,n,i,mat,gt,beta", DURUMLAR)
def test_boyutlandirma_kendi_kontrolunu_gecer(P, n, i, mat, gt, beta):
    """Modül σ_em·Y_N/S ile boyutlandırılır ve aynı değerle kontrol edilir; standart
    modüle yukarı yuvarlama ancak daha güvenli yapar."""
    r = h.calc_gear_stage(1, gt, mat, P, n, i, beta_deg=beta)
    assert r.sigma1 <= r.sigma_allow * (1 + 1e-9)
    assert r.sigma2 <= r.sigma_allow2 * (1 + 1e-9)


# ------------------------------------------------------------------ #
#  Profil kaydırma
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("x1,x2", [(0.4, 0.2), (0.5, 0.0), (0.3, 0.3)])
def test_bas_kisaltma_dip_boslugunu_korur(x1, x2):
    """x1+x2 > 0 iken baş kısaltma uygulanır: dip boşluğu c = 0,25·m kalmalı."""
    r = h.calc_gear_stage(1, "duz", "PETG", 0.25, 1500, 3.0, x1=x1, x2=x2, z1_override=17)
    assert r.k_short > 0
    c1 = r.a - r.da1 / 2 - r.df2 / 2          # pinyon başı ile çark dibi arası
    c2 = r.a - r.da2 / 2 - r.df1 / 2
    assert c1 == pytest.approx(0.25 * r.mn, abs=1e-6)
    assert c2 == pytest.approx(0.25 * r.mn, abs=1e-6)


def test_profil_kaydirmasiz_bas_kisaltma_yok():
    r = h.calc_gear_stage(1, "duz", "PETG", 0.25, 1500, 3.0, z1_override=17)
    assert r.k_short == 0.0
    assert r.da1 == pytest.approx(r.d01 + 2 * r.mn)


def test_x_min_helisel_esdeger_dis_sayisi():
    assert h.x_min_profile(17) == 0.0
    assert h.x_min_profile(14) == pytest.approx(3 / 17)
    # helisel: z_n = z/cos³β büyür -> daha az kaydırma gerekir
    assert h.x_min_profile(14, 20.0) < h.x_min_profile(14, 0.0)
    z_n = 14 / math.cos(math.radians(20)) ** 3
    assert h.x_min_profile(14, 20.0) == pytest.approx(max(0.0, (17 - z_n) / 17))
