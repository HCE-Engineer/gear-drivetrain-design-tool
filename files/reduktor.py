#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  REDÜKTÖR TASARIM & HESAP UYGULAMASI  v3   (MAKEL2 - Akkurt/DIN convention)
================================================================================
  1..3 kademe. Tip: DÜZ / HELİSEL / DÜZ KONİK / SONSUZ VİDA (worm).

  HESAP
    - Boyutlandırma (diş dibi + yüzey basıncı), geometri, eksenler arası mesafe
    - Kuvvetler Ft/Fr/Fa (helisel, konik ve worm'da EKSENEL), profil kaydırma
    - Kavrama oranı εα/εβ/εγ            (ÖZ.2)
    - Diş ucu sivrilme kontrolü sa       (ÖZ.3)
    - Göbek kaması DIN 6885 basıncı      (ÖZ.4)
    - DÜZ KONİK dişli — hocanın slaytı birebir (ÖZ.5)
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

  KAYNAK ÖNCELİĞİ: (1) hoca slaytı  (2) Akkurt  (3) DIN/genel
    Silindirik diş dibi + yüzey basıncı : hoca slaytı (MAKEL2_DISLI_2, s.19)
    Konik (δ01, mm, Ft/Fr/Fa, σ1, φm≤10, b≤R/3) : hoca slaytı (MAKEL2_KONİK_DISLI_2)
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


# ================================================================== #
#  BÖLÜM 0 — STANDART VERİLER
# ================================================================== #

STD_MODULES = [0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0,
               5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 25.0]     # DIN 780

MIN_MODULE_FDM = 1.0
ALPHA_N = math.radians(20.0)
E_SHAFT_DEFAULT = 210000.0     # çelik mil E (N/mm²)

# --- MALZEME VERİTABANI ---
#  sigma_em : diş dibi tasarım gerilmesi (N/mm²)     [10^6 çevrimde referans]
#  P_Hem    : müsaade edilen Hertz basıncı (N/mm²)
#  E        : elastisite modülü (N/mm²)
#  mu / mu_greased : sürtünme katsayısı (kuru / gresli)
#  Tg       : servis üst sıcaklık işareti (°C)
#  pv_lim   : plastik pV tarama sınırı               [VDI 2736 tahmini]
#  p_key    : göbek kama yüzey basıncı emniyeti (N/mm²)
#  sn_exp   : Wöhler (S-N) eğim üsteli — ömür faktörü Y_N = (1e6/N)^(1/sn_exp)
MATERIALS = {
    "PLA":  dict(sigma_em=18, P_Hem=25, E=3300, mu=0.35, mu_greased=0.12,
                 Tg=57,  pv_lim=0.10, p_key=25,  sn_exp=9,  plastic=True),
    "PETG": dict(sigma_em=16, P_Hem=22, E=2100, mu=0.32, mu_greased=0.10,
                 Tg=80,  pv_lim=0.16, p_key=22,  sn_exp=9,  plastic=True),
    "ABS":  dict(sigma_em=15, P_Hem=20, E=2100, mu=0.35, mu_greased=0.12,
                 Tg=105, pv_lim=0.14, p_key=20,  sn_exp=9,  plastic=True),
    "Çelik C45 (ref)": dict(sigma_em=200, P_Hem=520, E=210000, mu=0.08,
                            mu_greased=0.05, Tg=9999, pv_lim=99, p_key=100,
                            sn_exp=30, plastic=False),
    "Çelik 42CrMo4 (ref)": dict(sigma_em=320, P_Hem=650, E=210000, mu=0.08,
                                mu_greased=0.05, Tg=9999, pv_lim=99, p_key=120,
                                sn_exp=30, plastic=False),
}

K0_TABLE = {
    "Sakin (elektrik motoru, düzgün yük)": 1.00,
    "Orta (hafif darbeli)": 1.25,
    "Darbeli (ağır darbeli)": 1.50,
}

# (ad, d, D, B, C_dyn[N], C0[N], tip)   [SKF mertebesinde — katalogla doğrula]
# Aynı iç çapta önce hafif seri (60xx), sonra ağır seri (62xx) gelir:
# ömür yetmezse kod otomatik olarak aynı çapta ağır seriye geçer.
BEARINGS = [
    ("608",   8, 22,  7,  3450,  1370, "bilyeli"),
    ("6000", 10, 26,  8,  4750,  1960, "bilyeli"),
    ("6200", 10, 30,  9,  5070,  2360, "bilyeli"),
    ("6001", 12, 28,  8,  5400,  2360, "bilyeli"),
    ("6201", 12, 32, 10,  6890,  3100, "bilyeli"),
    ("6002", 15, 32,  9,  5850,  2850, "bilyeli"),
    ("6202", 15, 35, 11,  7800,  3750, "bilyeli"),
    ("6003", 17, 35, 10,  6000,  3250, "bilyeli"),
    ("6203", 17, 40, 12,  9560,  4750, "bilyeli"),
    ("6004", 20, 42, 12,  9950,  5000, "bilyeli"),
    ("6204", 20, 47, 14, 12700,  6550, "bilyeli"),
    ("6005", 25, 47, 12, 11200,  6550, "bilyeli"),
    ("6205", 25, 52, 15, 14000,  7800, "bilyeli"),
    ("6006", 30, 55, 13, 13300,  8300, "bilyeli"),
    ("6206", 30, 62, 16, 19500, 11200, "bilyeli"),
    ("6007", 35, 62, 14, 16000, 10200, "bilyeli"),
    ("6207", 35, 72, 17, 25500, 15300, "bilyeli"),
    ("6008", 40, 68, 15, 17800, 11600, "bilyeli"),
    ("6208", 40, 80, 18, 30700, 19000, "bilyeli"),
    ("6009", 45, 75, 16, 21200, 14600, "bilyeli"),
    ("6209", 45, 85, 19, 32500, 21600, "bilyeli"),
    ("6010", 50, 80, 16, 21600, 16000, "bilyeli"),
    ("6210", 50, 90, 20, 35100, 23200, "bilyeli"),
    ("6011", 55, 90, 18, 28100, 21200, "bilyeli"),
    ("6211", 55, 100, 21, 43600, 29000, "bilyeli"),
    ("6012", 60, 95, 18, 29600, 23200, "bilyeli"),
    ("6212", 60, 110, 22, 47500, 32500, "bilyeli"),
    ("6013", 65, 100, 18, 30700, 25000, "bilyeli"),
    ("6014", 70, 110, 20, 37700, 31000, "bilyeli"),
    ("6016", 80, 125, 22, 47600, 40000, "bilyeli"),
]
BEARINGS.sort(key=lambda b: (b[1], b[4]))     # önce çap, sonra hafif->ağır seri
STD_BORE = [8, 10, 12, 15, 17, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80]

# DIN 6885 A: (d_min, d_max, b, h, t1_mil, t2_göbek)
DIN6885 = [
    (6, 8, 2, 2, 1.2, 1.0), (8, 10, 3, 3, 1.8, 1.4), (10, 12, 4, 4, 2.5, 1.8),
    (12, 17, 5, 5, 3.0, 2.3), (17, 22, 6, 6, 3.5, 2.8), (22, 30, 8, 7, 4.0, 3.3),
    (30, 38, 10, 8, 5.0, 3.3), (38, 44, 12, 8, 5.0, 3.3), (44, 50, 14, 9, 5.5, 3.8),
    (50, 58, 16, 10, 6.0, 4.3), (58, 65, 18, 11, 7.0, 4.4), (65, 75, 20, 12, 7.5, 4.9),
    (75, 85, 22, 14, 9.0, 5.4),
]


def din6885(d: float):
    for lo, hi, b, h, t1, t2 in DIN6885:
        if lo < d <= hi:
            return b, h, t2
    return None


# ================================================================== #
#  BÖLÜM 1 — YARDIMCI FONKSİYONLAR
# ================================================================== #

def involute(a: float) -> float:
    return math.tan(a) - a


def inv_involute(inv_target: float, a0: float = 0.35) -> float:
    """inv(α)=hedef denklemini Newton ile çöz."""
    a = max(a0, 1e-3)
    for _ in range(80):
        f = involute(a) - inv_target
        df = (1.0/math.cos(a))**2 - 1.0
        if abs(df) < 1e-12:
            break
        a -= f/df
        a = min(max(a, 1e-4), 1.5)
    return a


def std_module(m_min: float, plastic: bool) -> float:
    floor = MIN_MODULE_FDM if plastic else 0.0
    for m in STD_MODULES:
        if m >= m_min and m >= floor:
            return m
    return STD_MODULES[-1]


def distribute_ratio(i_total: float, n_stages: int) -> List[float]:
    per = i_total ** (1.0 / n_stages)
    return [per] * n_stages


def zmin_no_undercut(beta_deg: float) -> float:
    return 17.0 * (math.cos(math.radians(beta_deg)) ** 3)


def x_min_profile(z: int, beta_deg: float = 0.0) -> float:
    return max(0.0, (17.0 - z) / 17.0)


def form_factor_Kf(z_eq: float, x: float = 0.0) -> float:
    """Diş dibi form faktörü — Akkurt grafiğine YAKLAŞIK eğri.
    Kesin iş için grafikten okuyup Kf_override ile gir."""
    z = max(z_eq, 8.0)
    Kf = 2.10 + 6.0 / z
    Kf -= 0.6 * max(0.0, x)
    return max(1.9, Kf)


def _torque_Nmm(P_kW: float, n_rpm: float) -> float:
    if n_rpm <= 0:
        return 0.0
    return 9550.0 * P_kW / n_rpm * 1000.0


def pick_std_bore(d_min: float) -> float:
    for d in STD_BORE:
        if d >= d_min:
            return float(d)
    return float(math.ceil(d_min))


# ---------- ÖZELLİK 7: ömür (çevrim) faktörü ----------
def life_factor(n_rpm: float, Lh: float, sn_exp: float) -> Tuple[float, float]:
    """
    N = 60·n·Lh  (dişli tur başına 1 temas)
    Y_N = (10^6/N)^(1/sn_exp) ,  [0.40 .. 1.30] arasında sınırlanır
    [VDI 2736 / Wöhler mantığı — hoca slaytında YOK, tahmini]
    """
    N = 60.0 * max(n_rpm, 1e-9) * max(Lh, 1e-9)
    if N <= 0:
        return 1.0, 0.0
    YN = (1e6 / N) ** (1.0 / max(sn_exp, 1e-6))
    YN = min(1.30, max(0.40, YN))
    return YN, N


# ---------- ÖZELLİK 2: kavrama oranı ----------
def contact_ratio(d01, d02, da1, da2, mn, beta_deg, b, a_w):
    """
    εα = [√(ra1²-rb1²) + √(ra2²-rb2²) - a_w·sin α_tw] / (π·mt·cos α_t)
    εβ = b·sin β / (π·mn)        (helisel örtüşme oranı)
    εγ = εα + εβ
    """
    eps_a, eps_b, eps_g, _, _ = contact_ratio_full(d01, d02, da1, da2, mn,
                                                   beta_deg, b, a_w)
    return eps_a, eps_b, eps_g


def contact_ratio_full(d01, d02, da1, da2, mn, beta_deg, b, a_w):
    """
    contact_ratio + yaklaşma/uzaklaşma bileşenleri:
      εα1 = z1/(2π)·(tan α_a1 - tan α_tw)     (yaklaşma)
      εα2 = z2/(2π)·(tan α_a2 - tan α_tw)     (uzaklaşma)
      εα  = εα1 + εα2
    Bunlar verim (H_v) hesabında gerekir.
    """
    beta = math.radians(beta_deg)
    alpha_t = math.atan(math.tan(ALPHA_N)/math.cos(beta)) if beta_deg > 0 else ALPHA_N
    mt = mn/math.cos(beta) if beta_deg > 0 else mn
    a_ref = (d01 + d02)/2.0
    if a_w <= 0:
        a_w = a_ref
    cos_atw = min(1.0, a_ref*math.cos(alpha_t)/a_w)
    atw = math.acos(cos_atw)
    rb1 = d01*math.cos(alpha_t)/2.0
    rb2 = d02*math.cos(alpha_t)/2.0
    ra1, ra2 = da1/2.0, da2/2.0
    num = (math.sqrt(max(0.0, ra1**2 - rb1**2)) + math.sqrt(max(0.0, ra2**2 - rb2**2))
           - a_w*math.sin(atw))
    eps_a = num / (math.pi * mt * math.cos(alpha_t))
    eps_b = b*math.sin(beta)/(math.pi*mn) if beta_deg > 0 else 0.0
    # yaklaşma / uzaklaşma bileşenleri
    z1 = d01/mt if mt > 0 else 1.0
    z2 = d02/mt if mt > 0 else 1.0
    aa1 = math.acos(min(1.0, rb1/ra1)) if ra1 > rb1 else 0.0
    aa2 = math.acos(min(1.0, rb2/ra2)) if ra2 > rb2 else 0.0
    e1 = z1/(2*math.pi)*(math.tan(aa1) - math.tan(atw))
    e2 = z2/(2*math.pi)*(math.tan(aa2) - math.tan(atw))
    return eps_a, eps_b, eps_a + eps_b, max(e1, 0.0), max(e2, 0.0)


def mesh_efficiency(z1, z2, beta_deg, eps_a, eps_a1, eps_a2, mu):
    """
    Diş kavrama verimi — Niemann/Ohlendorf diş kayıp faktörü H_v
    [DIN / ISO-TR 14179 mantığı — hoca slaytında YOK, tahmini]
      H_v = π·(u+1)/(z1·u·cos β_b) · (1 - εα + εα1² + εα2²)
      η_z = 1 - μ_mz · H_v
    Böylece verim GEOMETRİYE bağlı olur (z1, β, εα) ve yağlama gerçek etki eder.
    """
    if z1 <= 0 or z2 <= 0:
        return 0.97
    u = z2/z1
    beta = math.radians(beta_deg)
    sin_bb = math.sin(beta)*math.cos(ALPHA_N)
    cos_bb = math.sqrt(max(1e-9, 1.0 - sin_bb**2))
    Hv = (math.pi*(u + 1.0)/(z1*u*cos_bb))*(1.0 - eps_a + eps_a1**2 + eps_a2**2)
    Hv = max(0.0, Hv)
    eta = 1.0 - mu*Hv
    return min(0.995, max(0.50, eta))


# ---------- ÖZELLİK 3: diş ucu sivrilme ----------
def tip_thickness(mn, z, x, da, beta_deg=0.0):
    """
    s_t = mt·(π/2 + 2·x·tan α_n)              (taksimatta, alın)
    α_at = arccos(db/da)
    s_at = da·[s_t/d + inv(α_t) - inv(α_at)]  (diş ucunda, alın)
    s_an ≈ s_at·cos β                          (normal kesitte, yaklaşık)
    """
    beta = math.radians(beta_deg)
    alpha_t = math.atan(math.tan(ALPHA_N)/math.cos(beta)) if beta_deg > 0 else ALPHA_N
    mt = mn/math.cos(beta) if beta_deg > 0 else mn
    d = mt*z
    db = d*math.cos(alpha_t)
    if da <= db:
        return 0.0
    s_t = mt*(math.pi/2.0 + 2.0*x*math.tan(ALPHA_N))
    alpha_at = math.acos(min(1.0, db/da))
    s_at = da*(s_t/d + involute(alpha_t) - involute(alpha_at))
    return max(0.0, s_at*math.cos(beta))


def tip_thickness_limit(mn: float, plastic: bool) -> float:
    """Sivrilme sınırı: metal 0,2·mn ; FDM plastik max(0,4·mn ; 0,8 mm)
    (0,4 mm nozzle ile en az 2 duvar basılabilsin)."""
    return max(0.4*mn, 0.8) if plastic else 0.2*mn


# ---------- ÖZELLİK 4: kama yüzey basıncı ----------
def key_check(T_Nmm, bore, hub_width, p_em):
    """
    p = 2·T / (d · t2 · l_taşıyıcı)  ≤  p_em
    Form A kama: l_taşıyıcı = l - b   (l ≈ göbek genişliği)
    """
    km = din6885(bore)
    if km is None or bore <= 0:
        return None
    b_k, h_k, t2 = km
    l_eff = max(hub_width - b_k, 1e-6)
    p = 2.0*T_Nmm/(bore * t2 * l_eff)
    return dict(b=b_k, h=h_k, t2=t2, l=hub_width, l_eff=l_eff,
                p=p, p_em=p_em, ok=(p <= p_em))


# ---------- ÖZELLİK 8: asal diş (hunting) ----------
def hunting_check(z1, z2):
    g = math.gcd(int(z1), int(z2))
    if g == 1:
        return True, ""
    for dz in (1, -1, 2, -2):
        if math.gcd(int(z1), int(z2+dz)) == 1:
            return False, f"z2={z2} ile z1={z1} ortak bölen {g} -> z2={z2+dz} yap (asal)"
    return False, f"z1={z1}, z2={z2} ortak bölen {g}"


# ================================================================== #
#  BÖLÜM 2 — SONUÇ YAPILARI
# ================================================================== #

@dataclass
class StageResult:
    idx: int
    gtype: str                 # "duz" | "helisel" | "konik" | "worm"
    material: str
    P_in: float
    n_in: float
    i_stage: float
    beta: float = 0.0
    z1: int = 0
    z2: int = 0
    i_real: float = 0.0
    mn: float = 0.0            # (konikte: DIŞ modül m)
    mt: float = 0.0            # (konikte: ORTALAMA modül mm)
    d01: float = 0.0
    d02: float = 0.0
    da1: float = 0.0
    da2: float = 0.0
    df1: float = 0.0
    df2: float = 0.0
    db1: float = 0.0
    a: float = 0.0
    b: float = 0.0
    x1: float = 0.0
    x2: float = 0.0
    T1: float = 0.0
    T2: float = 0.0
    Ft: float = 0.0
    Fr: float = 0.0
    Fa: float = 0.0
    v: float = 0.0
    mn_root: float = 0.0
    mn_hertz: float = 0.0
    sigma1: float = 0.0
    sigma_allow: float = 0.0
    root_ok: bool = True
    # ÖZELLİK 7 — ömür
    YN: float = 1.0
    N_cycles: float = 0.0
    sigma_em_eff: float = 0.0
    # ÖZELLİK 2 — kavrama oranı
    eps_a: float = 0.0
    eps_b: float = 0.0
    eps_g: float = 0.0
    eps_a1: float = 0.0        # yaklaşma bileşeni (verim H_v için)
    eps_a2: float = 0.0        # uzaklaşma bileşeni
    eps_a_built: float = 0.0   # boşluk eklenmiş (a+j) haliyle
    # ÖZELLİK 3 — diş ucu
    sa1: float = 0.0
    sa2: float = 0.0
    sa_lim: float = 0.0
    # ÖZELLİK 4 — kama
    key1: Optional[dict] = None
    key2: Optional[dict] = None
    # ÖZELLİK 8 — asal diş
    hunting: bool = True
    # ÖZELLİK 5 — konik
    delta_axis: float = 90.0   # eksenler arası açı δ
    delta01: float = 0.0       # pinyon taksimat koni açısı
    delta02: float = 0.0
    R_cone: float = 0.0        # taksimat konisi yarıçapı (koni mesafesi)
    d0m1: float = 0.0          # ortalama taksimat çapı
    d0m2: float = 0.0
    ze1: float = 0.0           # Tredgold eşdeğer diş sayısı
    phi_m: float = 10.0
    # worm
    gamma: float = 0.0
    q: float = 0.0
    eta_mesh: float = 1.0
    self_locking: bool = False
    eta_reverse: float = 0.0
    T_steady: float = 0.0
    P_loss: float = 0.0
    # genel
    lubricated: bool = False
    mu_used: float = 0.0
    backlash: float = 0.15
    eta: float = 0.99
    P_out: float = 0.0
    n_out: float = 0.0
    layout_off: float = 0.0    # şema yerleşimi için düşey ofset
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ShaftResult:
    idx: int
    name: str = ""
    L: float = 0.0
    n_rpm: float = 0.0
    RA_y: float = 0.0
    RA_z: float = 0.0
    RB_y: float = 0.0
    RB_z: float = 0.0
    RA: float = 0.0
    RB: float = 0.0
    Fa_net: float = 0.0
    M_max: float = 0.0
    T: float = 0.0
    Mv: float = 0.0
    d_min: float = 0.0
    d_sec: float = 0.0
    # ÖZELLİK 6 — sehim / eğim
    defl: float = 0.0          # dişli konumundaki max sehim (mm)
    defl_lim: float = 0.0
    defl_ok: bool = True
    slope_A: float = 0.0       # yatak eğimi (rad)
    slope_B: float = 0.0
    slope_lim: float = 0.001
    slope_ok: bool = True
    governing: str = "mukavemet"   # çapı belirleyen kriter
    d_strength: float = 0.0        # sadece mukavemetten gelen çap
    warnings: List[str] = field(default_factory=list)


@dataclass
class BearingResult:
    shaft_idx: int
    name: str = "-"
    d: float = 0.0
    D: float = 0.0
    B: float = 0.0
    C: float = 0.0
    Fr: float = 0.0
    Fa: float = 0.0
    P: float = 0.0
    L10h: float = 0.0
    target: float = 0.0
    ok: bool = False
    notes: List[str] = field(default_factory=list)


# ================================================================== #
#  BÖLÜM 3 — HESAP ÇEKİRDEĞİ
# ================================================================== #

def _common_post(r: StageResult, mat: dict, S: float, Lh: float):
    """Ortak son kontroller: ömür, kavrama oranı, sivrilme, asal diş, plastik."""
    # ÖZELLİK 8 — asal diş
    ok, msg = hunting_check(r.z1, r.z2)
    r.hunting = ok
    if not ok:
        r.notes.append(f"Asal diş (hunting) değil: {msg}. Aşınma belirli diş "
                       f"çiftlerinde toplanır — mümkünse düzelt.")


def calc_gear_stage(idx, gtype, material, P_in, n_in, i_stage,
                    beta_deg=0.0, psi_d=0.8, K0=1.25, Kv=1.15, Km=1.2,
                    x1=0.0, x2=0.0, z1_override=None, Kf_override=None,
                    eta_gear=None, lubricated=False, backlash=0.15,
                    S=1.5, Lh=10000.0) -> StageResult:
    """
    DÜZ / HELİSEL kademe.  Formüller: hoca slaytı (MAKEL2_DISLI_2 s.19)
      mn ≥ [2·Mb/(z1²·ψd·σem)·cos²β·Kf·K0·Kv·Km]^(1/3)
      σ1 = Ft/(b·mn)·Kf·K0·Kv·Km ≤ σD*/S
      mn ≥ (cosβ/z1)·[2Mb/(ψd·P_Hem²)·K0·Kv·Km·0,348·E·(i+1)/i·1/(cos²α0·tanα)]^(1/3)
    ÖZELLİK 7: σem, ömür faktörü Y_N ile azaltılır.
    """
    mat = MATERIALS[material]
    r = StageResult(idx=idx, gtype=gtype, material=material, P_in=P_in, n_in=n_in,
                    i_stage=i_stage, beta=beta_deg, lubricated=lubricated,
                    backlash=backlash)
    beta = math.radians(beta_deg)
    Mb = _torque_Nmm(P_in, n_in)
    r.T1 = Mb

    # diş sayıları
    z1 = int(z1_override) if z1_override else (17 if beta_deg < 8 else 16)
    z2 = max(1, round(z1 * i_stage))
    r.z1, r.z2 = z1, z2
    r.i_real = z2 / z1

    z_eq1 = z1 / (math.cos(beta) ** 3) if beta_deg > 0 else z1
    Kf = Kf_override if Kf_override else form_factor_Kf(z_eq1, x1)

    # ÖZELLİK 7 — ömür faktörü
    r.YN, r.N_cycles = life_factor(n_in, Lh, mat["sn_exp"])
    sigma_em = mat["sigma_em"] * r.YN
    r.sigma_em_eff = sigma_em

    # boyutlandırma — diş dibi
    inside = (2.0*Mb)/(z1**2 * psi_d * sigma_em) * (math.cos(beta)**2) * Kf*K0*Kv*Km
    r.mn_root = inside ** (1.0/3.0)

    # boyutlandırma — yüzey basıncı
    E, P_Hem = mat["E"], mat["P_Hem"]
    alpha_t = math.atan(math.tan(ALPHA_N)/math.cos(beta)) if beta_deg > 0 else ALPHA_N
    i12 = r.i_real
    inside_h = (2.0*Mb)/(psi_d * P_Hem**2) * K0*Kv*Km * 0.348*E * (i12+1.0)/i12 \
               * 1.0/((math.cos(ALPHA_N)**2) * math.tan(alpha_t))
    r.mn_hertz = (math.cos(beta)/z1) * (inside_h ** (1.0/3.0))

    mn = std_module(max(r.mn_root, r.mn_hertz), mat["plastic"])
    r.mn = mn
    r.mt = mn/math.cos(beta) if beta_deg > 0 else mn

    # geometri
    d01 = mn*z1/math.cos(beta) if beta_deg > 0 else mn*z1
    d02 = mn*z2/math.cos(beta) if beta_deg > 0 else mn*z2
    r.d01, r.d02 = d01, d02
    r.b = psi_d * d01
    r.da1 = d01 + 2.0*mn*(1.0 + x1)
    r.da2 = d02 + 2.0*mn*(1.0 + x2)
    r.df1 = d01 - 2.0*mn*(1.25 - x1)
    r.df2 = d02 - 2.0*mn*(1.25 - x2)
    r.db1 = d01*math.cos(alpha_t)
    r.x1, r.x2 = x1, x2

    # eksenler arası
    a_ref = (d01 + d02)/2.0
    if (x1 + x2) != 0.0:
        inv_atw = involute(alpha_t) + 2.0*math.tan(ALPHA_N)*(x1+x2)/(z1+z2)
        atw = inv_involute(inv_atw, alpha_t)
        r.a = a_ref*math.cos(alpha_t)/math.cos(atw)
        r.notes.append(f"Profil kaydırmalı: çalışma α_tw={math.degrees(atw):.2f}°, "
                       f"a={r.a:.2f} mm (kaydırmasız {a_ref:.2f})")
    else:
        r.a = a_ref
    r.layout_off = r.a

    # kuvvetler
    r.Ft = 2.0*Mb/d01
    if beta_deg > 0:
        r.Fr = r.Ft*math.tan(alpha_t)
        r.Fa = r.Ft*math.tan(beta)
    else:
        r.Fr = r.Ft*math.tan(ALPHA_N)
        r.Fa = 0.0
    r.v = math.pi*d01*n_in/60000.0

    # diş dibi kontrolü
    r.sigma1 = r.Ft/(r.b*mn)*Kf*K0*Kv*Km
    r.sigma_allow = sigma_em/S
    r.root_ok = r.sigma1 <= r.sigma_allow
    if not r.root_ok:
        r.warnings.append(f"Diş dibi σ1={r.sigma1:.1f} > σ_em(N)/S={r.sigma_allow:.1f} "
                          f"N/mm² -> modülü/ψd'yi artır veya malzeme değiştir.")

    # ÖZELLİK 2 — kavrama oranı (verim hesabı da buna dayanıyor)
    r.eps_a, r.eps_b, r.eps_g, e1, e2 = contact_ratio_full(d01, d02, r.da1, r.da2,
                                                           mn, beta_deg, r.b, r.a)
    r.eps_a1, r.eps_a2 = e1, e2
    r.eps_a_built, _, _, _, _ = contact_ratio_full(d01, d02, r.da1, r.da2, mn,
                                                   beta_deg, r.b, r.a + backlash)

    # verim — GEOMETRİYE bağlı (Ohlendorf H_v), yağlama μ üzerinden etkir
    r.mu_used = mat["mu_greased"] if lubricated else mat["mu"]
    if eta_gear is None:
        eta_gear = mesh_efficiency(z1, z2, beta_deg, r.eps_a, e1, e2, r.mu_used)
    r.eta = eta_gear
    r.P_out = P_in*eta_gear
    r.n_out = n_in/r.i_real
    r.T2 = Mb*r.i_real*eta_gear

    if r.eps_a < 1.0:
        r.warnings.append(f"εα={r.eps_a:.2f} < 1,0 -> SÜREKLİ KAVRAMA YOK, dişli çalışmaz!")
    elif r.eps_a < 1.1:
        r.warnings.append(f"εα={r.eps_a:.2f} < 1,1 -> kavrama sınırda, gürültü/darbe riski.")
    if r.eps_a_built < 1.1 <= r.eps_a:
        r.warnings.append(f"Boşluk j={backlash:.2f} mm eklenince εα {r.eps_a:.2f}→"
                          f"{r.eps_a_built:.2f} düşüyor (sınır altı). Boşluğu azalt.")

    # ÖZELLİK 3 — diş ucu sivrilme
    r.sa1 = tip_thickness(mn, z1, x1, r.da1, beta_deg)
    r.sa2 = tip_thickness(mn, z2, x2, r.da2, beta_deg)
    r.sa_lim = tip_thickness_limit(mn, mat["plastic"])
    if r.sa1 < r.sa_lim:
        r.warnings.append(f"Pinyon diş ucu sivri: sa1={r.sa1:.2f} < {r.sa_lim:.2f} mm "
                          f"-> x1'i azalt veya da1'i kısalt (baş kısaltma).")
    if r.sa2 < r.sa_lim:
        r.warnings.append(f"Çark diş ucu sivri: sa2={r.sa2:.2f} < {r.sa_lim:.2f} mm.")

    # alttan kesilme
    zmin = zmin_no_undercut(beta_deg)
    if z1 < zmin and x1 <= 0:
        r.warnings.append(f"z1={z1} < z_min={zmin:.0f} -> alttan kesilme. "
                          f"x1 ≥ +{x_min_profile(z1, beta_deg):.2f} öner.")

    _common_post(r, mat, S, Lh)
    if mat["plastic"]:
        _plastic_checks(r, mat)
    return r


# ---------------- ÖZELLİK 5: KONİK DİŞLİ ---------------- #

def calc_bevel_stage(idx, material, P_in, n_in, i_stage, delta_axis=90.0,
                     phi_m=10.0, K0=1.25, Kv=1.15, z1_override=None,
                     Kf_override=None, eta_gear=None, lubricated=False,
                     backlash=0.15, S=1.5, Lh=10000.0,
                     m_pref=None, b_pref=None) -> StageResult:
    """
    DÜZ KONİK DİŞLİ — hocanın slaytı (MAKEL2_KONİK_DISLI_2) BİREBİR:
      δ = δ01 + δ02
      tan δ01 = sin δ /(i12 + cos δ)              (δ < 90°)
      tan δ01 = sin(180-δ)/(i12 - cos(180-δ))     (δ > 90°)
      d01 = m·z1 , d02 = m·z2        (DIŞ ölçüler, m standart seçilir)
      R = d01/(2·sin δ01)
      d0m = mm·z ,  m = mm + (b/z)·sin δ01        (ORTALAMA ölçüler)
      hb = m (baş) , ht = 1,2·m (taban) , h = 2,2·m
      tan xb = m/R , tan xt = ht/R
      db = d0 + 2·hb·cos δ0   (BAŞ çapı!)  ,  dt = d0 - 2·ht·cos δ0  (TABAN)
      ze1 = z1/cos δ01                            (Tredgold eşdeğer)
      Md = Ft·z·mm/2   ->   Ft = 2·Md/(z1·mm)
      Fa = Ft·tan α·sin δ01   ,   Fr = Ft·tan α·cos δ01
      σ1 = Ft/(b·mm)·K0·KF·Kv ≤ σMÜS/S
      mm ≥ [2·Md·K0·KF·Kv/(σem·z1·φm)]^(1/3)   ,  φm ≤ 10 ,  b ≤ R/3
    DİKKAT: burada φm = b/mm (silindirikteki ψd = b/d01 DEĞİL), Km YOK.
    """
    mat = MATERIALS[material]
    r = StageResult(idx=idx, gtype="konik", material=material, P_in=P_in, n_in=n_in,
                    i_stage=i_stage, lubricated=lubricated, backlash=backlash,
                    delta_axis=delta_axis, phi_m=phi_m)
    Md = _torque_Nmm(P_in, n_in)
    r.T1 = Md

    z1 = int(z1_override) if z1_override else 17
    z2 = max(1, round(z1*i_stage))
    r.z1, r.z2 = z1, z2
    r.i_real = z2/z1
    i12 = r.i_real

    # --- koni açıları (hocanın formülü) ---
    d_ax = math.radians(delta_axis)
    if abs(delta_axis - 90.0) < 1e-9:
        d01_ang = math.atan(1.0/i12)                       # sin90=1, cos90=0
    elif delta_axis < 90.0:
        d01_ang = math.atan(math.sin(d_ax)/(i12 + math.cos(d_ax)))
    else:
        d2 = math.radians(180.0 - delta_axis)
        d01_ang = math.atan(math.sin(d2)/(i12 - math.cos(d2)))
    d02_ang = d_ax - d01_ang
    r.delta01, r.delta02 = math.degrees(d01_ang), math.degrees(d02_ang)

    # --- eşdeğer diş sayısı (Tredgold) ve Kf ---
    r.ze1 = z1/math.cos(d01_ang)
    Kf = Kf_override if Kf_override else form_factor_Kf(r.ze1, 0.0)

    # --- ömür faktörü ---
    r.YN, r.N_cycles = life_factor(n_in, Lh, mat["sn_exp"])
    sigma_em = mat["sigma_em"]*r.YN
    r.sigma_em_eff = sigma_em

    # --- boyutlandırma: ortalama modül mm (hocanın formülü, Km YOK) ---
    mm_min = (2.0*Md*K0*Kf*Kv/(sigma_em*z1*phi_m)) ** (1.0/3.0)
    r.mn_root = mm_min
    r.mn_hertz = 0.0                     # konikte slaytta yüzey formülü verilmemiş

    # --- dış modülü seç (verilmişse onu kullan = KONTROL MODU) ---
    if m_pref:
        m_std = float(m_pref)
        r.notes.append(f"KONTROL MODU: dış modül m={m_std:g} kullanıcı tarafından verildi "
                       f"(boyutlandırma formülü mm≥{mm_min:.3f} sadece kıyas için).")
    else:
        b_try = phi_m*mm_min
        m_calc = mm_min + (b_try/z1)*math.sin(d01_ang)
        m_std = std_module(m_calc, mat["plastic"])
    r.mn = m_std                          # DIŞ modül

    # --- dış geometri ---
    d01 = m_std*z1
    d02 = m_std*z2
    r.d01, r.d02 = d01, d02
    R = d01/(2.0*math.sin(d01_ang))
    r.R_cone = R

    # --- diş genişliği: verilmişse o, yoksa φm·mm ve R/3 sınırlarının küçüğü ---
    if b_pref:
        b = float(b_pref)
        r.notes.append(f"KONTROL MODU: diş genişliği b={b:g} mm verildi.")
    else:
        b = min(phi_m*mm_min, R/3.0)
    r.b = b

    # --- ortalama modül (standart dış modülden geri) ---
    mm = m_std - (b/z1)*math.sin(d01_ang)
    r.mt = mm                             # ORTALAMA modül
    r.d0m1 = mm*z1
    r.d0m2 = mm*z2

    # --- baş/taban ölçüleri (hocanın notasyonu: db=BAŞ, dt=TABAN) ---
    hb, ht = m_std, 1.2*m_std
    r.da1 = d01 + 2.0*hb*math.cos(d01_ang)     # db1 (baş)
    r.da2 = d02 + 2.0*hb*math.cos(d02_ang)     # db2
    r.df1 = d01 - 2.0*ht*math.cos(d01_ang)     # dt1 (taban)
    r.df2 = d02 - 2.0*ht*math.cos(d02_ang)     # dt2
    r.db1 = 0.0                                # konikte temel daire kullanılmıyor

    # --- kuvvetler (hocanın formülü) ---
    r.Ft = 2.0*Md/(z1*mm)                      # = 2·Md/d0m1
    r.Fa = r.Ft*math.tan(ALPHA_N)*math.sin(d01_ang)
    r.Fr = r.Ft*math.tan(ALPHA_N)*math.cos(d01_ang)
    r.v = math.pi*r.d0m1*n_in/60000.0

    # --- diş dibi kontrolü (Km YOK) ---
    r.sigma1 = r.Ft/(b*mm)*K0*Kf*Kv
    r.sigma_allow = sigma_em/S
    r.root_ok = r.sigma1 <= r.sigma_allow
    if not r.root_ok:
        r.warnings.append(f"Diş dibi σ1={r.sigma1:.1f} > σ_em(N)/S={r.sigma_allow:.1f} "
                          f"N/mm² -> modülü veya φm'i artır.")

    # --- kontroller ---
    phi_m_real = b/mm                      # gerçekleşen φm = b/mm
    r.phi_m = phi_m_real
    if phi_m_real > 10.0:
        r.warnings.append(f"φm=b/mm={phi_m_real:.1f} > 10 -> hocanın sınırı aşıldı.")
    if b > R/3.0 + 1e-6:
        r.warnings.append(f"b={b:.1f} > R/3={R/3:.1f} -> genişlik sınırı aşıldı.")
    if r.ze1 < 17:
        r.warnings.append(f"Eşdeğer diş sayısı ze1={r.ze1:.1f} < 17 -> alttan kesilme "
                          f"riski (konikte profil kaydırma ile düzeltilir).")

    # --- kavrama oranı: Tredgold eşdeğer düz dişli üzerinden (verimden ÖNCE!) ---
    ze2 = z2/math.cos(d02_ang)
    de1, de2 = mm*r.ze1, mm*ze2
    dae1, dae2 = de1 + 2.0*mm, de2 + 2.0*mm
    r.eps_a, r.eps_b, r.eps_g, _e1, _e2 = contact_ratio_full(
        de1, de2, dae1, dae2, mm, 0.0, b, (de1+de2)/2.0)
    r.eps_a1, r.eps_a2 = _e1, _e2
    r.eps_a_built = r.eps_a
    if r.eps_a < 1.1:
        r.warnings.append(f"εα={r.eps_a:.2f} < 1,1 (Tredgold eşdeğerinden) -> "
                          f"kavrama sınırda.")

    # --- verim (Tredgold eşdeğeri üzerinden H_v; konik ek kayıp için ×0,99) ---
    r.mu_used = mat["mu_greased"] if lubricated else mat["mu"]
    if eta_gear is None:
        eta_gear = 0.99*mesh_efficiency(max(1, int(round(r.ze1))),
                                        max(1, int(round(ze2))), 0.0,
                                        r.eps_a, _e1, _e2, r.mu_used)
    r.eta = eta_gear
    r.P_out = P_in*eta_gear
    r.n_out = n_in/r.i_real
    r.T2 = Md*r.i_real*eta_gear

    # --- diş ucu sivrilme (eşdeğer düz dişli) ---
    r.sa1 = tip_thickness(mm, max(1, int(round(r.ze1))), 0.0, dae1, 0.0)
    r.sa2 = tip_thickness(mm, max(1, int(round(ze2))), 0.0, dae2, 0.0)
    r.sa_lim = tip_thickness_limit(mm, mat["plastic"])

    r.a = 0.0                # konikte eksenler kesişir — eksenler arası mesafe yok
    r.layout_off = d02/2.0   # sadece şema yerleşimi için
    r.notes.append(f"Konik: eksenler {delta_axis:.0f}° kesişiyor -> eksenler arası "
                   f"mesafe (a) TANIMSIZ. Koni mesafesi R={R:.1f} mm.")
    r.notes.append(f"Ortalama modül mm={mm:.3f} (dış m={m_std:g}); kuvvetler ve "
                   f"mukavemet ORTALAMA modül üzerinden — hocanın konvansiyonu.")
    r.notes.append(f"Tredgold eşdeğer: ze1={r.ze1:.1f} -> Kf bu değerden okundu.")

    _common_post(r, mat, S, Lh)
    if mat["plastic"]:
        _plastic_checks(r, mat)
        r.warnings.append("Konik dişli FDM'de zor: diş yüzeyi eğik, katman merdiveni "
                          "belirgin. Yüksek çözünürlük/reçine düşün.")
    return r


def ze1_safe(z):
    return z


# ---------------- WORM ---------------- #

def calc_worm_stage(idx, material, P_in, n_in, i_stage, z1=2, q=10.0,
                    mn_pref=None, K0=1.25, lubricated=False, backlash=0.15,
                    T_amb=25.0, housing_area_m2=None, S=1.5,
                    Lh=10000.0) -> StageResult:
    """
    SONSUZ VİDA — [DIN 3975/Niemann, hoca slaytında YOK]
      tanγ = z1/q ; d1=q·m ; d2=z2·m ; a=m(q+z2)/2
      ρ' = atan(μ/cos αn) ; η = tanγ/tan(γ+ρ') ; kilit: γ ≤ ρ'
      η' (geri) = tan(γ-ρ')/tanγ
    """
    mat = MATERIALS[material]
    r = StageResult(idx=idx, gtype="worm", material=material, P_in=P_in, n_in=n_in,
                    i_stage=i_stage, lubricated=lubricated, backlash=backlash)
    z2 = max(1, round(i_stage*z1))
    r.z1, r.z2 = z1, z2
    r.i_real = z2/z1
    r.q = q
    Mb = _torque_Nmm(P_in, n_in)
    r.T1 = Mb

    if mn_pref:
        m = std_module(mn_pref, mat["plastic"])
    else:
        m0 = max(MIN_MODULE_FDM, (Mb/2000.0) ** (1/3)/max(1, z2/10))
        m = std_module(m0, mat["plastic"])
    r.mn = r.mt = m

    d1, d2 = q*m, z2*m
    r.d01, r.d02 = d1, d2
    r.da1, r.da2 = d1 + 2.0*m, d2 + 2.0*m
    r.df1, r.df2 = d1 - 2.5*m, d2 - 2.5*m
    r.a = (d1 + d2)/2.0
    r.layout_off = r.a
    r.b = 0.75*d1

    gamma = math.atan(z1/q)
    r.gamma = math.degrees(gamma)
    mu = mat["mu_greased"] if lubricated else mat["mu"]
    r.mu_used = mu
    rho = math.atan(mu/math.cos(ALPHA_N))
    eta = math.tan(gamma)/math.tan(gamma + rho)
    r.eta_mesh = r.eta = eta
    r.self_locking = gamma <= rho
    r.eta_reverse = math.tan(gamma - rho)/math.tan(gamma) if gamma > rho else 0.0

    Ft1 = 2.0*Mb/d1
    r.Ft = Ft1
    M2 = Mb*r.i_real*eta
    r.T2 = M2
    r.Fa = 2.0*M2/d2
    r.Fr = Ft1*math.tan(ALPHA_N)/math.sin(gamma) if math.sin(gamma) > 1e-6 else 0.0
    r.v = math.pi*d1*n_in/60000.0
    r.P_out = P_in*eta
    r.n_out = n_in/r.i_real

    r.YN, r.N_cycles = life_factor(n_in, Lh, mat["sn_exp"])
    r.sigma_em_eff = mat["sigma_em"]*r.YN

    r.P_loss = P_in*(1.0 - eta)*1000.0
    A = housing_area_m2 if housing_area_m2 else 20.0*(r.a/1000.0)**2
    A = max(A, 1e-4)
    r.T_steady = T_amb + r.P_loss/(15.0*A)

    r.notes.append(f"Worm DIN 3975/Niemann tabanlı [DIN/tahmini]. "
                   f"μ={mu:.2f} ({'gresli' if lubricated else 'kuru'})")
    if r.self_locking:
        r.notes.append(f"γ={r.gamma:.1f}° ≤ ρ'={math.degrees(rho):.1f}° -> KENDİNDEN "
                       f"KİLİTLİ (çıkıştan sürülemez). η={eta:.2f}")
    else:
        r.notes.append(f"γ={r.gamma:.1f}° > ρ'={math.degrees(rho):.1f}° -> geri "
                       f"sürülebilir, η'={r.eta_reverse:.2f}")
    if eta < 0.5:
        r.warnings.append(f"Worm verimi düşük (η={eta:.2f})."
                          + ("  Gres yağlama denenmedi." if not lubricated else ""))
    Tg = mat["Tg"]
    if r.T_steady > Tg:
        r.warnings.append(f"ÇALIŞMAZ: T_denge={r.T_steady:.0f}°C > sınır {Tg}°C.")
    elif r.T_steady > 0.8*Tg:
        r.warnings.append(f"T_denge={r.T_steady:.0f}°C, sınıra ({Tg}°C) yakın.")

    _common_post(r, mat, S, Lh)
    if mat["plastic"]:
        _plastic_checks(r, mat)
        r.warnings.append("Plastik worm: aşınma/sıcaklık kritik (VDI 2736-3).")
    return r


def _plastic_checks(r: StageResult, mat: dict):
    p_proxy = r.sigma1 if r.sigma1 > 0 else (r.Ft/max(r.b*r.mn, 1e-6))
    pv = p_proxy*r.v
    if pv > mat["pv_lim"]*40:
        r.warnings.append(f"pV taraması yüksek (~{pv:.1f}) -> aşınma/ısınma riski.")
    if r.v > 5.0:
        r.warnings.append(f"Çevresel hız v={r.v:.1f} m/s plastik için yüksek (>5 m/s).")
    if r.mn < MIN_MODULE_FDM:
        r.warnings.append(f"mn={r.mn} < {MIN_MODULE_FDM} mm -> 0,4 mm nozzle basamaz.")
    r.notes.append(f"{r.material}: üst sıcaklık ~{mat['Tg']}°C; σ_em sıcaklıkla düşer.")
    r.notes.append("BASKI: dişliyi YATAY yatır (eksen dik) -> katmanlar diş yüküne dik.")


# ---------------- ÖZELLİK 4: kama kontrolü (kademe sonrası) ---------------- #

def apply_key_checks(results: List[StageResult], shafts: List[ShaftResult]):
    """Her dişlinin göbeğindeki kama yüzey basıncını kontrol et."""
    for i, r in enumerate(results):
        mat = MATERIALS[r.material]
        p_em = mat["p_key"]
        d_pin = shafts[i].d_sec if i < len(shafts) else 0
        d_gear = shafts[i+1].d_sec if i+1 < len(shafts) else 0
        r.key1 = key_check(r.T1, d_pin, r.b, p_em)
        r.key2 = key_check(r.T2, d_gear, r.b, p_em)
        for tag, k in (("Pinyon", r.key1), ("Çark", r.key2)):
            if k and not k["ok"]:
                r.warnings.append(
                    f"{tag} kaması YETERSİZ: p={k['p']:.1f} > p_em={k['p_em']:.0f} "
                    f"N/mm² -> göbeği uzat (l={k['l']:.0f}→{k['l']*k['p']/k['p_em']:.0f} "
                    f"mm), çift kama kullan veya göbeği metal yap.")


# ---------------- MİL (ÖZELLİK 4 + 6) ---------------- #

def _beam_solve(L, point_loads, couples):
    if L <= 0:
        return 0.0, 0.0, {}
    RB = (sum(F*a for a, F in point_loads) + sum(M0 for _, M0 in couples))/L
    RA = sum(F for _, F in point_loads) - RB
    return RA, RB, dict(loads=point_loads, couples=couples, RA=RA, L=L)


def _beam_moment(data, x, side="left"):
    if not data:
        return 0.0
    eps = 1e-6
    xx = x - eps if side == "left" else x + eps
    M = data["RA"]*xx
    for a, F in data["loads"]:
        if a < xx:
            M -= F*(xx - a)
    for a, M0 in data["couples"]:
        if a < xx:
            M -= M0
    return M


def _beam_deflection(L, loads, E, I, x):
    """
    İki mesnetli kiriş, tekil yük F @ a; süperpozisyon.
      x ≤ a: y = F·b·x·(L² - b² - x²)/(6·E·I·L)
      x ≥ a: y = F·a·(L-x)·(2·L·x - x² - a²)/(6·E·I·L)
    (Tekil momentlerin sehime katkısı ihmal — muhafazakâr değil, NOT düşülür.)
    """
    if E*I <= 0 or L <= 0:
        return 0.0
    y = 0.0
    for a, F in loads:
        b = L - a
        if x <= a:
            y += F*b*x*(L**2 - b**2 - x**2)/(6.0*E*I*L)
        else:
            y += F*a*(L - x)*(2.0*L*x - x**2 - a**2)/(6.0*E*I*L)
    return y


def _beam_slopes(L, loads, E, I):
    """θ_A = Σ F·b·(L²-b²)/(6EIL) ,  θ_B = Σ F·a·(L²-a²)/(6EIL)"""
    if E*I <= 0 or L <= 0:
        return 0.0, 0.0
    tA = tB = 0.0
    for a, F in loads:
        b = L - a
        tA += F*b*(L**2 - b**2)/(6.0*E*I*L)
        tB += F*a*(L**2 - a**2)/(6.0*E*I*L)
    return tA, tB


def calc_shafts(results, sigma_em_mil=60.0, L_factor=3.0, alpha0_c=0.7,
                E_shaft=E_SHAFT_DEFAULT, slope_lim=0.001) -> List[ShaftResult]:
    """
    MODEL (muhafazakâr basitleştirme):
      - Her mil iki yatak arası basit kiriş, L = L_factor·max(b)
      - Ara mil: önceki çark (L/3), sonraki pinyon (2L/3); uç mil: tek dişli (L/2)
      - Düşey: Fr + Fa·d0/2 tekil momenti | Yatay: Ft
      - Tüm dişliler aynı faz düzleminde (kuvvetler üst üste biner)
      - Mv = √(M² + 0,75·(α0c·T)²) ;  d = (32·Mv/(π·σem))^(1/3)
    ÖZELLİK 6: seçilen çapla sehim ve yatak eğimi kontrolü.
    """
    n_st = len(results)
    shafts = []
    for k in range(n_st + 1):
        s = ShaftResult(idx=k, slope_lim=slope_lim)
        gears = []
        if k == 0:
            s.name = "GİRİŞ mili"
            gears.append((results[0], "pinyon"))
            s.n_rpm, s.T = results[0].n_in, results[0].T1
        elif k == n_st:
            s.name = "ÇIKIŞ mili"
            gears.append((results[-1], "cark"))
            s.n_rpm, s.T = results[-1].n_out, results[-1].T2
        else:
            s.name = f"Ara mil {k}"
            gears.append((results[k-1], "cark"))
            gears.append((results[k], "pinyon"))
            s.n_rpm, s.T = results[k-1].n_out, results[k-1].T2

        b_max = max(g[0].b for g in gears)
        s.L = L_factor*b_max
        positions = [s.L/2.0] if len(gears) == 1 else [s.L/3.0, 2.0*s.L/3.0]

        loads_y, loads_z, couples_z = [], [], []
        Fa_sum = 0.0
        for (stage, role), pos in zip(gears, positions):
            if stage.gtype == "konik":
                d0 = stage.d0m1 if role == "pinyon" else stage.d0m2
            else:
                d0 = stage.d01 if role == "pinyon" else stage.d02
            loads_y.append((pos, stage.Ft))
            loads_z.append((pos, stage.Fr))
            if stage.Fa > 0:
                couples_z.append((pos, stage.Fa*d0/2.0))
                Fa_sum += stage.Fa

        RA_y, RB_y, dat_y = _beam_solve(s.L, loads_y, [])
        RA_z, RB_z, dat_z = _beam_solve(s.L, loads_z, couples_z)
        s.RA_y, s.RB_y, s.RA_z, s.RB_z = RA_y, RB_y, RA_z, RB_z
        s.RA, s.RB = math.hypot(RA_y, RA_z), math.hypot(RB_y, RB_z)
        s.Fa_net = Fa_sum

        M_max = 0.0
        for pos in positions:
            for side in ("left", "right"):
                M_max = max(M_max, math.hypot(_beam_moment(dat_y, pos, side),
                                              _beam_moment(dat_z, pos, side)))
        s.M_max = M_max
        s.Mv = math.sqrt(M_max**2 + 0.75*(alpha0_c*s.T)**2)
        s.d_min = (32.0*s.Mv/(math.pi*sigma_em_mil)) ** (1.0/3.0) if s.Mv > 0 else 0.0
        s.d_strength = pick_std_bore(s.d_min)
        s.d_sec = s.d_strength

        # --- ÖZELLİK 6: sehim & eğim -> gerekiyorsa çapı BÜYÜT (rijitlik odaklı) ---
        mn_min = min(g[0].mn for g in gears)
        s.defl_lim = 0.01*mn_min                 # yaygın kural: f ≤ 0,01·mn
        s.governing = "mukavemet"

        def _stiffness(d):
            I = math.pi*d**4/64.0
            dfl = 0.0
            for pos in positions:
                dy = _beam_deflection(s.L, loads_y, E_shaft, I, pos)
                dz = _beam_deflection(s.L, loads_z, E_shaft, I, pos)
                dfl = max(dfl, math.hypot(dy, dz))
            tAy, tBy = _beam_slopes(s.L, loads_y, E_shaft, I)
            tAz, tBz = _beam_slopes(s.L, loads_z, E_shaft, I)
            return dfl, math.hypot(tAy, tAz), math.hypot(tBy, tBz)

        # önce mukavemet çapında rijitliği sına -> belirleyici kriteri sapta
        dfl0, tA0, tB0 = _stiffness(s.d_strength)
        if dfl0 > s.defl_lim:
            s.governing = "sehim"
        elif max(tA0, tB0) > slope_lim:
            s.governing = "eğim"
        else:
            s.governing = "mukavemet"

        for cand in [d for d in STD_BORE if d >= s.d_strength] or [s.d_strength]:
            dfl, tA, tB = _stiffness(cand)
            s.d_sec, s.defl, s.slope_A, s.slope_B = cand, dfl, tA, tB
            s.defl_ok = dfl <= s.defl_lim
            s.slope_ok = max(tA, tB) <= slope_lim
            if s.defl_ok and s.slope_ok:
                break

        if s.d_sec > s.d_strength:
            s.warnings.append(
                f"Çapı RİJİTLİK belirledi: mukavemet {s.d_strength:.0f} mm yeterdi, "
                f"{s.governing} kontrolü {s.d_sec:.0f} mm'ye zorladı.")
        if not s.defl_ok:
            s.warnings.append(f"Sehim f={s.defl*1000:.0f} µm > sınır {s.defl_lim*1000:.0f} µm "
                              f"(0,01·mn) — katalogdaki en büyük çapla bile sağlanmadı. "
                              f"Yatak açıklığını (L={s.L:.0f} mm) kısalt veya diş "
                              f"genişliğini azalt.")
        if not s.slope_ok:
            s.warnings.append(f"Yatak eğimi {max(s.slope_A, s.slope_B)*1000:.2f} mrad > "
                              f"{slope_lim*1000:.1f} mrad -> oynak/eğik yatak düşün.")
        if s.Fa_net > 0.5*max(s.RA, s.RB, 1e-6):
            s.warnings.append(f"Eksenel yük yüksek (Fa={s.Fa_net:.0f} N) -> eksenel "
                              f"sabitleme ve uygun rulman tipi şart.")
        shafts.append(s)
    return shafts


def calc_bearing(shaft: ShaftResult, Lh_target=10000.0) -> BearingResult:
    """P = Fr veya X·Fr+Y·Fa ; L10h = (C/P)³·10⁶/(60·n)  [X-Y katalogdan iyileştirilebilir]"""
    br = BearingResult(shaft_idx=shaft.idx, target=Lh_target)
    Fr, Fa = max(shaft.RA, shaft.RB), shaft.Fa_net
    br.Fr, br.Fa = Fr, Fa
    e, X, Y = 0.3, 0.56, 1.5
    P = Fr if (Fr <= 1e-9 or Fa/Fr <= e) else (X*Fr + Y*Fa)
    br.P = P = max(P, 1e-6)
    cands = [b for b in BEARINGS if b[1] >= shaft.d_sec]
    if not cands:
        br.notes.append(f"Katalogda d ≥ {shaft.d_sec:.0f} mm rulman yok -> "
                        f"daha büyük seri/tip gerekli.")
        return br
    # Tüm adayları sırayla dene (çap küçük->büyük, aynı çapta hafif->ağır seri).
    # Hedefi sağlayan İLK rulman seçilir; hiçbiri sağlamazsa en yüksek C'li tutulur.
    best_fallback = None
    for name, d, D, B, C, C0, tip in cands:
        L10h = (C/P)**3*1e6/(60.0*max(shaft.n_rpm, 1e-6))
        if L10h >= Lh_target:
            br.name, br.d, br.D, br.B, br.C, br.L10h, br.ok = name, d, D, B, C, L10h, True
            break
        if best_fallback is None or C > best_fallback[4]:
            best_fallback = (name, d, D, B, C, L10h)
    else:
        name, d, D, B, C, L10h = best_fallback
        br.name, br.d, br.D, br.B, br.C, br.L10h, br.ok = name, d, D, B, C, L10h, False
        br.notes.append(f"Katalogdaki en güçlü rulman (C={C:.0f} N) bile hedefi "
                        f"sağlamıyor (L10h={L10h:,.0f} < {Lh_target:,.0f} h). "
                        f"Gerekli C ≈ {P*(Lh_target*60*shaft.n_rpm/1e6)**(1/3):,.0f} N -> "
                        f"makaralı rulman, çift sıra veya yükü düşür.")
    if br.d > shaft.d_sec:
        br.notes.append(f"Mil çapı {shaft.d_sec:.0f} mm yeterdi ama ömür için "
                        f"d={br.d:.0f} mm rulmana çıkıldı -> mil o kademede "
                        f"{br.d:.0f} mm'ye büyütülmeli.")
    if Fr > 1e-9 and Fa/Fr > 0.5:
        br.notes.append("Fa/Fr > 0,5 -> eğik bilyalı (7xxx) veya konik makaralı düşün.")
    return br


# ---------------- ÖZELLİK 1: KOAKSİYELLİK ---------------- #

def check_coaxial(results: List[StageResult], tol=0.5) -> dict:
    """
    Giriş ve çıkış milleri eş eksenli mi?
    Ara mil merkezleri düzlemde serbestçe konumlanabildiği için koşul VEKTÖRELDİR:
        Σ a_k (2B vektör) = 0   ->  a_k uzunlukları KAPALI ÇOKGEN oluşturmalı.
      n=1 : imkânsız (a1 ≠ 0 ; ancak planet dişli ile olur)
      n=2 : iki vektör -> zıt yönlü ve eşit  =>  a1 = a2  (KESİN koşul)
      n=3 : üçgen kapanması -> üçgen eşitsizliği: max(a) ≤ Σ(diğerleri)
    Konik kademe varsa eksen döner -> koaksiyel tanımı bozulur.
    """
    bevels = [r.idx for r in results if r.gtype == "konik"]
    if bevels:
        return dict(feasible=False, error=float('inf'), angles=[],
                    msg=f"Kademe {bevels} KONİK -> eksen {results[bevels[0]-1].delta_axis:.0f}° "
                        f"döner, giriş/çıkış eş eksenli olamaz.")
    a = [r.a for r in results]
    n = len(a)
    if n == 1:
        return dict(feasible=False, error=a[0], angles=[],
                    msg=f"Tek kademe koaksiyel olamaz (a={a[0]:.1f} mm ofset). "
                        f"Planet dişli gerekir.")
    if n == 2:
        err = abs(a[0] - a[1])
        return dict(feasible=(err <= tol), error=err, angles=[180.0],
                    msg=(f"a1={a[0]:.2f}, a2={a[1]:.2f} -> fark {err:.2f} mm. "
                         + ("KOAKSİYEL ✓ (2 kademede a1=a2 şart)" if err <= tol
                            else "eş eksenli DEĞİL — a1=a2 olmalı.")))
    # n >= 3: çokgen kapanması
    mx = max(a)
    rest = sum(a) - mx
    err = max(0.0, mx - rest)
    if err > tol:
        return dict(feasible=False, error=err, angles=[],
                    msg=(f"a={[f'{v:.1f}' for v in a]} -> en büyük ({mx:.1f}) diğerlerinin "
                         f"toplamından ({rest:.1f}) büyük. Çokgen kapanmaz, "
                         f"eş eksenli olamaz. Fark {err:.1f} mm."))
    angles = []
    if n == 3:
        # üçgen iç açıları (kosinüs teoremi) -> mil yerleşim açıları
        A, B, C = a
        try:
            angA = math.degrees(math.acos(max(-1, min(1, (B*B + C*C - A*A)/(2*B*C)))))
            angB = math.degrees(math.acos(max(-1, min(1, (A*A + C*C - B*B)/(2*A*C)))))
            angC = 180.0 - angA - angB
            angles = [angA, angB, angC]
        except Exception:
            angles = []
    return dict(feasible=True, error=err, angles=angles,
                msg=(f"a={[f'{v:.1f}' for v in a]} -> çokgen kapanıyor, KOAKSİYEL ✓"
                     + (f"  (mil yerleşim açıları: "
                        f"{', '.join(f'{x:.1f}°' for x in angles)})" if angles else "")))


# ---------------- ANA ZİNCİR ---------------- #

def calc_reducer(cfg: dict, light: bool = False) -> dict:
    """
    light=True -> mil/rulman/kama atlanır (arama motoru için hızlı).
    """
    P, n = cfg['P_in'], cfg['n_in']
    lub = cfg.get('lubricated', False)
    j = cfg.get('backlash', 0.15)
    bed = cfg.get('bed_size', 220.0)
    Lh = cfg.get('Lh_target', 10000.0)
    S = cfg.get('S', 1.5)
    results, spur_count = [], 0

    for i, sc in enumerate(cfg['stages'], start=1):
        gtype, mat = sc['gtype'], sc['material']
        if gtype == "worm":
            res = calc_worm_stage(i, mat, P, n, sc['i_stage'], z1=sc.get('z1', 2),
                                  q=sc.get('q', 10.0), mn_pref=sc.get('mn_pref'),
                                  K0=sc.get('K0', 1.25), lubricated=lub, backlash=j,
                                  T_amb=cfg.get('T_amb', 25.0),
                                  housing_area_m2=cfg.get('housing_area_m2'),
                                  S=S, Lh=Lh)
        elif gtype == "konik":
            res = calc_bevel_stage(i, mat, P, n, sc['i_stage'],
                                   m_pref=sc.get('m_pref'), b_pref=sc.get('b_pref'),
                                   delta_axis=sc.get('delta_axis', 90.0),
                                   phi_m=sc.get('phi_m', 10.0), K0=sc.get('K0', 1.25),
                                   Kv=sc.get('Kv', 1.15), z1_override=sc.get('z1_gear'),
                                   Kf_override=sc.get('Kf'), eta_gear=sc.get('eta'),
                                   lubricated=lub, backlash=j, S=S, Lh=Lh)
        else:
            beta = sc.get('beta', 0.0) if gtype == "helisel" else 0.0
            res = calc_gear_stage(i, gtype, mat, P, n, sc['i_stage'], beta_deg=beta,
                                  psi_d=sc.get('psi_d', 0.8), K0=sc.get('K0', 1.25),
                                  Kv=sc.get('Kv', 1.15), Km=sc.get('Km', 1.2),
                                  x1=sc.get('x1', 0.0), x2=sc.get('x2', 0.0),
                                  z1_override=sc.get('z1_gear'), Kf_override=sc.get('Kf'),
                                  eta_gear=sc.get('eta'), lubricated=lub, backlash=j,
                                  S=S, Lh=Lh)
            if gtype == "duz":
                spur_count += 1

        # ÖZELLİK 10 — baskı yatağı taraması
        biggest = max(res.da1, res.da2, res.b)
        if res.gtype == "worm":
            biggest = max(biggest, 10.0*res.mn)
        if biggest > bed:
            res.warnings.append(
                f"BASKI: en büyük ölçü {biggest:.0f} mm > yatak {bed:.0f} mm -> oranı böl "
                f"(i={res.i_real:.1f} yerine {math.sqrt(res.i_real):.2f}×"
                f"{math.sqrt(res.i_real):.2f}) veya malzemeyi güçlendir.")
        elif biggest > 0.9*bed:
            res.warnings.append(f"BASKI: {biggest:.0f} mm, yatağın %90'ını aşıyor.")
        results.append(res)
        P, n = res.P_out, res.n_out

    eta_total, i_real_total = 1.0, 1.0
    for res in results:
        eta_total *= res.eta
        i_real_total *= res.i_real

    out = dict(results=results, eta_total=eta_total, i_real_total=i_real_total,
               i_target=cfg['i_total'], P_in=cfg['P_in'], n_in=cfg['n_in'],
               lubricated=lub, cfg=cfg)

    if light:
        out.update(shafts=[], bearings=[], coax=None, back_drivable=True,
                   project_warnings=[])
        return out

    shafts = calc_shafts(results, sigma_em_mil=cfg.get('sigma_em_mil', 60.0),
                         L_factor=cfg.get('L_factor', 3.0),
                         E_shaft=cfg.get('E_shaft', E_SHAFT_DEFAULT))
    apply_key_checks(results, shafts)            # ÖZELLİK 4
    bearings = [calc_bearing(s, Lh_target=Lh) for s in shafts]
    coax = check_coaxial(results)                # ÖZELLİK 1
    locked = any(r.self_locking for r in results if r.gtype == "worm")

    pw = []
    if cfg['n_stages'] < 3:
        pw.append("PROJE UYARISI: 3 kademeden az -> -40 puan (Puanlama.pdf).")
    if spur_count > 1:
        pw.append(f"PROJE UYARISI: {spur_count} düz dişli kademe -> 1'den fazla düz "
                  f"dişli -40 puan.")
    pw.append("EŞ EKSENLİLİK: " + coax['msg'])

    out.update(shafts=shafts, bearings=bearings, coax=coax,
               back_drivable=(not locked), project_warnings=pw)
    return out


# ================================================================== #
#  ÖZELLİK 1 + 9 + 10 — TASARIM ARAMA MOTORU
# ================================================================== #

def _ratio_splits(i_total, n_stages, step, lo=1.5, hi=6.3):
    """Kademelere oran dağılımı adayları."""
    if n_stages == 1:
        return [[i_total]] if lo <= i_total <= hi*2 else [[i_total]]
    grid = []
    v = lo
    while v <= hi + 1e-9:
        grid.append(round(v, 3))
        v += step
    out = []
    if n_stages == 2:
        for i1 in grid:
            i2 = i_total/i1
            if lo <= i2 <= hi:
                out.append([i1, i2])
    else:
        for i1 in grid:
            for i2 in grid:
                i3 = i_total/(i1*i2)
                if lo <= i3 <= hi:
                    out.append([i1, i2, i3])
    return out


def _gear_volume(res) -> float:
    """Kaba hacim (kompaktlık göstergesi): Σ π/4·da²·b  [mm³]"""
    V = 0.0
    for r in res['results']:
        V += math.pi/4.0*(r.da1**2)*r.b + math.pi/4.0*(r.da2**2)*r.b
    return V


def search_designs(base_cfg: dict, objective: str = "koaksiyel", n_best: int = 5,
                   z1_list=None, beta_list=None, max_evals: int = 20000,
                   progress=None) -> List[dict]:
    """
    ÖZELLİK 1 / 9 / 10 — tek arama motoru, farklı amaç fonksiyonları.
      objective:
        "koaksiyel"    -> giriş/çıkış eş eksenli olsun (a'lar kapalı çokgen)
        "min_hacim"    -> en kompakt (Σ π/4·da²·b en küçük)
        "max_verim"    -> toplam η en yüksek
        "oran_hassas"  -> gerçekleşen i, hedefe en yakın
    Tarama: oran dağılımı × z1 × β (kademe başına β).
    Kısıt: tüm kademelerde diş dibi TAMAM ve εα ≥ 1,1 olmalı (aksi halde elenir).
    """
    n_st = base_cfg['n_stages']
    types = [s['gtype'] for s in base_cfg['stages']]
    has_helical = any(t == "helisel" for t in types)

    if z1_list is None:
        z1_list = [16, 17, 18, 20] if n_st <= 2 else [17, 20]
    if beta_list is None:
        beta_list = [8, 12, 15, 20, 25] if n_st <= 2 else [12, 15, 20]

    step = 0.25 if n_st <= 2 else 0.5
    splits = _ratio_splits(base_cfg['i_total'], n_st, step)
    if not splits:
        splits = [distribute_ratio(base_cfg['i_total'], n_st)]

    # β kombinasyonları (sadece helisel kademeler için)
    beta_opts = []
    for t in types:
        beta_opts.append(beta_list if t == "helisel" else [0])
    beta_combos = list(itertools.product(*beta_opts))
    if not has_helical:
        beta_combos = [tuple(0 for _ in types)]

    combos = [(sp, z1, bc) for sp in splits for z1 in z1_list for bc in beta_combos]
    if len(combos) > max_evals:
        stride = max(1, len(combos)//max_evals)
        combos = combos[::stride][:max_evals]

    scored = []
    total = len(combos)
    for idx, (sp, z1, bc) in enumerate(combos):
        if progress and idx % 500 == 0:
            progress(idx, total)
        cfg = json.loads(json.dumps({k: v for k, v in base_cfg.items()
                                     if k != 'stages'}))
        cfg['stages'] = []
        for k, s in enumerate(base_cfg['stages']):
            s2 = dict(s)
            s2['i_stage'] = sp[k]
            s2['z1_gear'] = z1
            if s2['gtype'] == "helisel":
                s2['beta'] = bc[k]
            cfg['stages'].append(s2)
        try:
            res = calc_reducer(cfg, light=True)
        except Exception:
            continue

        # kısıtlar
        if any((not r.root_ok) for r in res['results']):
            continue
        if any(r.eps_a < 1.1 for r in res['results'] if r.gtype in ("duz", "helisel")):
            continue

        i_err = abs(res['i_real_total'] - base_cfg['i_total'])/base_cfg['i_total']
        if objective != "oran_hassas" and i_err > 0.05:
            continue                       # %5'ten fazla sapan tasarımları ele

        coax = check_coaxial(res['results'])
        if objective == "koaksiyel":
            score = coax['error'] + 1000.0*i_err
        elif objective == "min_hacim":
            score = _gear_volume(res)/1000.0 + 1e6*i_err
        elif objective == "max_verim":
            score = -res['eta_total'] + 10.0*i_err
        else:  # oran_hassas
            score = i_err
        scored.append(dict(score=score, cfg=cfg, i_real=res['i_real_total'],
                           i_err=i_err*100.0, eta=res['eta_total'],
                           coax_err=coax['error'], coax_ok=coax['feasible'],
                           coax_msg=coax['msg'], volume=_gear_volume(res)/1000.0,
                           a_list=[r.a for r in res['results']],
                           mn_list=[r.mn for r in res['results']],
                           z_list=[(r.z1, r.z2) for r in res['results']],
                           beta_list=[r.beta for r in res['results']],
                           evaluated=total))
    scored.sort(key=lambda d: d['score'])
    return scored[:n_best]


# ================================================================== #
#  ÖZELLİK 16 — DUYARLILIK TARAMASI
# ================================================================== #

SWEEPS = {
    "β (helis açısı) → Fa, mn, εβ": dict(param="beta", lo=0.0, hi=30.0, n=31,
                                          gtypes=("helisel",),
                                          curves=["Fa (N)", "mn×10", "εβ×100"]),
    "x1 (profil kaydırma) → σ1, sa1, εα": dict(param="x1", lo=-0.5, hi=0.8, n=27,
                                               gtypes=("duz", "helisel"),
                                               curves=["σ1 (N/mm²)", "sa1×10 (mm)",
                                                       "εα×100"]),
    "q (çap faktörü) → η, γ": dict(param="q", lo=6.0, hi=18.0, n=25,
                                    gtypes=("worm",),
                                    curves=["η×100", "γ (°)", "Fa/10 (N)"]),
    "φm → mm, b, σ1 (konik)": dict(param="phi_m", lo=4.0, hi=12.0, n=17,
                                    gtypes=("konik",),
                                    curves=["mm×10", "b (mm)", "σ1 (N/mm²)"]),
}


def sweep_stage(base_cfg: dict, stage_idx: int, sweep_name: str):
    """
    Bir kademenin tek parametresini tarayıp 3 eğri döndürür.
    Döner: dict(x=[...], series=[(ad,[değerler]), ...], xlabel=..)
    """
    spec = SWEEPS[sweep_name]
    p = spec["param"]
    xs = [spec["lo"] + (spec["hi"]-spec["lo"])*k/(spec["n"]-1) for k in range(spec["n"])]
    s1, s2, s3 = [], [], []
    for xv in xs:
        cfg = json.loads(json.dumps({k: v for k, v in base_cfg.items() if k != 'stages'}))
        cfg['stages'] = [dict(s) for s in base_cfg['stages']]
        cfg['stages'][stage_idx][p] = xv
        try:
            res = calc_reducer(cfg, light=True)
            r = res['results'][stage_idx]
        except Exception:
            s1.append(float('nan')); s2.append(float('nan')); s3.append(float('nan'))
            continue
        if p == "beta":
            s1.append(r.Fa); s2.append(r.mn*10); s3.append(r.eps_b*100)
        elif p == "x1":
            s1.append(r.sigma1); s2.append(r.sa1*10); s3.append(r.eps_a*100)
        elif p == "q":
            s1.append(r.eta*100); s2.append(r.gamma); s3.append(r.Fa/10)
        else:  # phi_m
            s1.append(r.mt*10); s2.append(r.b); s3.append(r.sigma1)
    names = spec["curves"]
    return dict(x=xs, xlabel=p, series=[(names[0], s1), (names[1], s2), (names[2], s3)])


# ================================================================== #
#  BÖLÜM 4 — RAPOR
# ================================================================== #

def _box(lines: List[str]) -> str:
    w = max(len(l) for l in lines)
    return ("┌" + "─"*(w+2) + "┐\n"
            + "\n".join("│ " + l.ljust(w) + " │" for l in lines)
            + "\n└" + "─"*(w+2) + "┘")


def _ok(flag):
    return "TAMAM ✓" if flag else "YETERSİZ ✗"


TYPE_NAMES = {"duz": "DÜZ DİŞLİ", "helisel": "HELİSEL DİŞLİ",
              "konik": "DÜZ KONİK DİŞLİ", "worm": "SONSUZ VİDA (WORM)"}


def report_stage(r: StageResult) -> str:
    o = []
    o.append("="*72)
    o.append(f"  KADEME {r.idx} — {TYPE_NAMES[r.gtype]}   |   {r.material}"
             f"   |   {'GRESLİ' if r.lubricated else 'KURU'}")
    o.append("="*72)
    o.append(f"Giriş: P={r.P_in:.3f} kW, n={r.n_in:.1f} rpm, hedef i={r.i_stage:.3f}")
    o.append(f"Diş sayıları: z1={r.z1}, z2={r.z2}  ->  gerçek i={r.i_real:.3f}"
             f"   {'(asal ✓)' if r.hunting else '(asal DEĞİL)'}")
    if r.gtype == "helisel":
        o.append(f"Helis açısı β={r.beta:.1f}°   (mt=mn/cosβ={r.mt:.3f} mm)")
    if r.gtype == "konik":
        o.append(f"Eksen açısı δ={r.delta_axis:.0f}°  ->  δ01={r.delta01:.2f}°, "
                 f"δ02={r.delta02:.2f}°")
        o.append(f"Koni mesafesi R={r.R_cone:.2f} mm   |   Tredgold ze1={r.ze1:.2f}")
    if r.gtype == "worm":
        o.append(f"Ağız z1={r.z1}, çap faktörü q={r.q:.1f}, γ={r.gamma:.2f}°, "
                 f"μ={r.mu_used:.2f}")

    # --- ömür faktörü (ÖZELLİK 7) ---
    o.append("")
    o.append("-- ÖMÜR / ÇEVRİM (σ_em ömre bağlı azalır) --  [VDI 2736 / Wöhler]")
    o.append(f"  N = 60·n·Lh = {r.N_cycles:.2e} çevrim  ->  Y_N = {r.YN:.3f}")
    o.append(f"  σ_em: {MATERIALS[r.material]['sigma_em']:.0f} × {r.YN:.3f} = "
             f"{r.sigma_em_eff:.1f} N/mm²")

    o.append("")
    o.append("-- BOYUTLANDIRMA --")
    if r.gtype == "konik":
        o.append(f"  Hocanın formülü: mm ≥ [2·Md·K0·KF·Kv/(σem·z1·φm)]^(1/3) = "
                 f"{r.mn_root:.3f} mm")
        o.append(f"  φm = b/mm = {r.phi_m:.2f}  (sınır ≤ 10)   |   b ≤ R/3 = "
                 f"{r.R_cone/3:.1f} mm")
        o.append(_box([f"DIŞ modül m (standart) = {r.mn:.3f} mm",
                       f"ORTALAMA modül mm = {r.mt:.3f} mm",
                       f"b (diş genişliği) = {r.b:.2f} mm",
                       f"R (koni mesafesi) = {r.R_cone:.2f} mm"]))
    elif r.gtype == "worm":
        o.append("  (worm: modül q ve momentten seçilip std'ye yuvarlandı)")
        o.append(_box([f"m (standart) = {r.mn:.3f} mm",
                       f"b = {r.b:.2f} mm", f"a (eksenler arası) = {r.a:.2f} mm"]))
    else:
        o.append(f"  Diş dibinden:      mn ≥ {r.mn_root:.3f} mm")
        o.append(f"  Yüzey basıncından: mn ≥ {r.mn_hertz:.3f} mm")
        o.append(f"  -> Belirleyici: {'YÜZEY BASINCI' if r.mn_hertz > r.mn_root else 'DİŞ DİBİ'}"
                 f"  ->  DIN 780'e yuvarla:")
        o.append(_box([f"mn (standart) = {r.mn:.3f} mm",
                       f"b (diş genişliği) = {r.b:.2f} mm",
                       f"a (eksenler arası) = {r.a:.2f} mm"]))

    o.append("")
    o.append("-- GEOMETRİ --")
    if r.gtype == "konik":
        o.append(f"  DIŞ taksimat:      d01={r.d01:.2f}   d02={r.d02:.2f} mm")
        o.append(f"  ORTALAMA taksimat: d0m1={r.d0m1:.2f}  d0m2={r.d0m2:.2f} mm")
        o.append(f"  Baş çapı (db):     {r.da1:.2f}   {r.da2:.2f} mm")
        o.append(f"  Taban çapı (dt):   {r.df1:.2f}   {r.df2:.2f} mm")
        o.append("  NOT: hocanın konik notasyonunda db=BAŞ, dt=TABAN "
                 "(helisel'deki temel daire DEĞİL).")
    else:
        o.append(f"  Taksimat: d01={r.d01:.2f}  d02={r.d02:.2f} mm")
        o.append(f"  Diş üstü: da1={r.da1:.2f}  da2={r.da2:.2f} mm")
        o.append(f"  Diş dibi: df1={r.df1:.2f}  df2={r.df2:.2f} mm")
        if r.gtype != "worm":
            o.append(f"  Temel daire: db1={r.db1:.2f} mm")
        if r.x1 or r.x2:
            o.append(f"  Profil kaydırma: x1={r.x1:+.3f}  x2={r.x2:+.3f}")

    # --- kavrama oranı (ÖZELLİK 2) ---
    if r.gtype != "worm":
        o.append("")
        o.append("-- KAVRAMA ORANI --  εα=[√(ra1²-rb1²)+√(ra2²-rb2²)-a_w·sinα_tw]/(π·mt·cosα_t)")
        lines = [f"εα (alın)     = {r.eps_a:.3f}   (≥1,1 olmalı)"]
        if r.eps_b > 0:
            lines.append(f"εβ (örtüşme)  = {r.eps_b:.3f}   = b·sinβ/(π·mn)")
            lines.append(f"εγ (toplam)   = {r.eps_g:.3f}")
        if abs(r.eps_a_built - r.eps_a) > 0.005:
            lines.append(f"εα (j={r.backlash:.2f} eklenmiş) = {r.eps_a_built:.3f}")
        o.append(_box(lines))

    # --- diş ucu sivrilme (ÖZELLİK 3) ---
    if r.gtype != "worm":
        o.append("")
        o.append("-- DİŞ UCU SİVRİLME --  s_a = da·[s_t/d + inv(α_t) - inv(α_at)]")
        o.append(_box([f"sa1 = {r.sa1:.3f} mm   sa2 = {r.sa2:.3f} mm",
                       f"sınır = {r.sa_lim:.3f} mm  -> "
                       f"{_ok(r.sa1 >= r.sa_lim and r.sa2 >= r.sa_lim)}"]))

    o.append("")
    o.append("-- KUVVETLER --")
    o.append(f"  T1 (giriş) = {r.T1:.0f} N·mm   |   T2 (çıkış) = {r.T2:.0f} N·mm")
    if r.gtype == "konik":
        o.append(f"  Ft = 2·Md/(z1·mm) = {r.Ft:.1f} N       [ortalama modül üzerinden]")
        o.append(f"  Fr = Ft·tanα·cos δ01 = {r.Fr:.1f} N")
        o.append(f"  Fa = Ft·tanα·sin δ01 = {r.Fa:.1f} N   <-- EKSENEL")
    else:
        o.append(f"  Ft (teğetsel) = {r.Ft:.1f} N")
        o.append(f"  Fr (radyal)   = {r.Fr:.1f} N")
        tag = "   <-- EKSENEL (yataklar buna göre!)" if r.Fa > 0 else ""
        o.append(f"  Fa (eksenel)  = {r.Fa:.1f} N{tag}")
    o.append(f"  v (çevresel hız) = {r.v:.2f} m/s")

    o.append("")
    if r.gtype == "konik":
        o.append("-- DİŞ DİBİ KONTROLÜ --  σ1 = Ft/(b·mm)·K0·KF·Kv ≤ σMÜS/S   (Km YOK)")
    elif r.gtype != "worm":
        o.append("-- DİŞ DİBİ KONTROLÜ --  σ1 = Ft/(b·mn)·Kf·K0·Kv·Km ≤ σD*/S")
    if r.gtype != "worm":
        o.append(_box([f"σ1 = {r.sigma1:.2f} N/mm²",
                       f"σ_em(N)/S = {r.sigma_allow:.2f} N/mm²  -> {_ok(r.root_ok)}"]))
    else:
        o.append("-- WORM ANALİZİ --  [DIN/tahmini]")
        o.append(_box([f"Kademe verimi η = {r.eta_mesh:.3f}",
                       f"Kendinden kilit: {'EVET (çıkıştan sürülemez)' if r.self_locking else 'hayır'}",
                       f"Geri sürme verimi η' = {r.eta_reverse:.3f}"]))
        o.append("-- SICAKLIK DENGESİ --  T = T_amb + P_kayıp/(k·A), k=15 W/m²K")
        o.append(_box([f"P_kayıp = {r.P_loss:.1f} W",
                       f"T_denge = {r.T_steady:.1f} °C",
                       f"Malzeme sınırı = {MATERIALS[r.material]['Tg']} °C"]))

    # --- kama (ÖZELLİK 4) ---
    if r.key1 or r.key2:
        o.append("")
        o.append("-- GÖBEK KAMASI (DIN 6885) --  p = 2·T/(d·t2·l_taşıyıcı) ≤ p_em")
        for tag, k in (("Pinyon", r.key1), ("Çark  ", r.key2)):
            if not k:
                continue
            o.append(f"  {tag}: kama {k['b']}×{k['h']}, t2={k['t2']}, "
                     f"l={k['l']:.0f} mm (taşıyıcı {k['l_eff']:.0f})")
            o.append(f"          p = {k['p']:.1f} ≤ p_em = {k['p_em']:.0f} N/mm²  -> "
                     f"{_ok(k['ok'])}")

    o.append("")
    o.append("-- VERİM & ÇIKIŞ --  [η: Ohlendorf H_v — geometriye bağlı]")
    o.append(_box([f"η = {r.eta:.4f}   (μ={r.mu_used:.2f})",
                   f"P_out = {r.P_out:.3f} kW",
                   f"n_out = {r.n_out:.1f} rpm"]))

    if r.warnings:
        o.append("")
        o.append("⚠️  UYARILAR:")
        for w in r.warnings:
            o.append(f"   • {w}")
    if r.notes:
        o.append("")
        o.append("📝  NOTLAR:")
        for nn in r.notes:
            o.append(f"   • {nn}")

    o.append("")
    o.append("🗺️  ÇÖZÜM AKIŞI:")
    if r.gtype == "worm":
        o.append("   P,n → z1,q → m(std) → d1,d2,a → γ,ρ' → η → Ft,Fa,Fr → T_denge → çıkış")
    elif r.gtype == "konik":
        o.append("   P,n → Md → δ01=atan(sinδ/(i+cosδ)) → ze1=z1/cosδ01 → Kf")
        o.append("        → mm(boyutlandırma) → m(std) → R, b≤R/3 → mm=m-(b/z1)sinδ01")
        o.append("        → Ft=2Md/(z1·mm) → Fr,Fa → σ1 kontrol → çıkış")
    else:
        o.append("   P,n → T → Y_N → mn(dişdibi & yüzey) → std mn → d,da,df,a,b")
        o.append("        → εα, sa → Ft,Fr,Fa → σ1 kontrol → η(H_v) → çıkış")
    o.append("")
    return "\n".join(o)


def report_shafts(res: dict) -> str:
    o = []
    o.append("="*72)
    o.append("  MİL ÖN BOYUTLANDIRMA  (mukavemet + RİJİTLİK)")
    o.append("="*72)
    o.append("MODEL (muhafazakâr basitleştirme):")
    o.append("  • İki yatak arası basit kiriş, L = 3·b")
    o.append("  • Ara mil: çark L/3, pinyon 2L/3 | uç mil: tek dişli L/2")
    o.append("  • Düşey: Fr + Fa·d0/2 momenti | Yatay: Ft | aynı faz düzlemi kabulü")
    o.append("  • Mv = √(M² + 0,75·(0,7·T)²) ; d = (32·Mv/(π·σem))^(1/3)")
    o.append("  • Sonra sehim (f ≤ 0,01·mn) ve yatak eğimi (≤1 mrad) için çap BÜYÜTÜLÜR")
    o.append("")
    n_st = len(res['results'])
    for s in res['shafts']:
        o.append(f"--- {s.name}  (n={s.n_rpm:.0f} rpm, L={s.L:.1f} mm) ---")
        if s.idx == 0 or s.idx == n_st:
            o.append("      SCD:  A△————————[dişli]————————△B     (L/2)")
        else:
            o.append("      SCD:  A△———[çark]———[pinyon]———△B   (L/3, 2L/3)")
        o.append(f"  Yatak A: Ry={s.RA_y:8.1f}  Rz={s.RA_z:8.1f}  |R|={s.RA:8.1f} N")
        o.append(f"  Yatak B: Ry={s.RB_y:8.1f}  Rz={s.RB_z:8.1f}  |R|={s.RB:8.1f} N")
        o.append(f"  Eksenel net Fa = {s.Fa_net:.1f} N")
        o.append(f"  M_max = {s.M_max:.0f} N·mm   |   T = {s.T:.0f} N·mm")
        o.append(_box([f"Mv = {s.Mv:.0f} N·mm  ->  mukavemetten d = {s.d_strength:.0f} mm",
                       f"Sehim f = {s.defl*1000:.1f} µm  (sınır {s.defl_lim*1000:.0f} µm) "
                       f"{_ok(s.defl_ok)}",
                       f"Yatak eğimi = {max(s.slope_A, s.slope_B)*1000:.2f} mrad "
                       f"(sınır {s.slope_lim*1000:.1f}) {_ok(s.slope_ok)}",
                       f"SEÇİLEN d = {s.d_sec:.0f} mm   [belirleyici: {s.governing.upper()}]"]))
        for w in s.warnings:
            o.append(f"   ⚠️  {w}")
        o.append("")
    return "\n".join(o)


def report_bearings(res: dict) -> str:
    o = []
    o.append("="*72)
    o.append("  RULMAN SEÇİMİ ve ÖMÜR (L10h)")
    o.append("="*72)
    o.append("P = Fr (Fa/Fr ≤ e) ; P = X·Fr+Y·Fa (Fa/Fr > e) ; e=0,30 X=0,56 Y=1,5")
    o.append("L10h = (C/P)³·10⁶/(60·n)          [X-Y: katalogdan iyileştirilebilir]")
    o.append("")
    for b, s in zip(res['bearings'], res['shafts']):
        o.append(f"--- {s.name} ---")
        if b.name == "-":
            o.append("   Uygun rulman bulunamadı.")
        else:
            o.append(f"  {b.name}  (d={b.d:.0f}×D={b.D:.0f}×B={b.B:.0f}), C={b.C:.0f} N")
            o.append(f"  Fr={b.Fr:.1f}  Fa={b.Fa:.1f}  ->  P={b.P:.1f} N")
            o.append(_box([f"L10h = {b.L10h:,.0f} saat",
                           f"Hedef = {b.target:,.0f} saat  -> {_ok(b.ok)}"]))
        for nn in b.notes:
            o.append(f"   • {nn}")
        o.append("")
    return "\n".join(o)


def report_full(res: dict) -> str:
    o = []
    o.append("#"*72)
    o.append("#  REDÜKTÖR HESAP RAPORU")
    o.append("#"*72)
    o.append(f"Giriş: {res['P_in']:.3f} kW @ {res['n_in']:.1f} rpm")
    o.append(f"Hedef oran i={res['i_target']:.2f}  |  Gerçekleşen i={res['i_real_total']:.2f}"
             f"  (sapma %{(res['i_real_total']-res['i_target'])/res['i_target']*100:+.1f})")
    o.append(f"Toplam verim η={res['eta_total']:.4f} (≈%{res['eta_total']*100:.1f})"
             f"   |   Yağlama: {'GRESLİ' if res['lubricated'] else 'KURU'}")
    o.append(f"Geri sürülebilir: {'EVET' if res['back_drivable'] else 'HAYIR (worm kilidi)'}")
    if res.get('coax'):
        o.append(f"Eş eksenlilik: {res['coax']['msg']}")
    o.append("")
    if res['project_warnings']:
        o.append("🎯 PROJE (Puanlama.pdf) KONTROL:")
        for w in res['project_warnings']:
            o.append(f"   • {w}")
        o.append("")
    for r in res['results']:
        o.append(report_stage(r))
    o.append(report_shafts(res))
    o.append(report_bearings(res))
    return "\n".join(o)


def report_search(best: List[dict], objective: str) -> str:
    """ÖZELLİK 1/9/10 — arama sonuçları tablosu."""
    o = []
    o.append("="*78)
    o.append(f"  TASARIM ARAMA — amaç: {objective.upper()}")
    o.append("="*78)
    if not best:
        o.append("Kısıtları sağlayan tasarım bulunamadı.")
        o.append("Öneriler: hedef oranı gevşet, malzemeyi güçlendir, kademe ekle,")
        o.append("veya ψd/φm ile diş genişliğini artır.")
        return "\n".join(o)
    o.append(f"Taranan kombinasyon: {best[0]['evaluated']}  |  "
             f"kısıtları geçen: en iyi {len(best)} gösteriliyor")
    o.append("Kısıt: tüm kademelerde diş dibi TAMAM ve εα ≥ 1,1")
    o.append("")
    hdr = f"{'#':<3}{'i (sapma%)':<14}{'η':<9}{'hacim cm³':<11}{'koax hata':<11}{'a listesi'}"
    o.append(hdr)
    o.append("-"*78)
    for k, b in enumerate(best, 1):
        a_s = ", ".join(f"{v:.1f}" for v in b['a_list'])
        o.append(f"{k:<3}{b['i_real']:.3f} ({b['i_err']:+.2f})  {b['eta']:<9.4f}"
                 f"{b['volume']:<11.0f}{b['coax_err']:<11.2f}[{a_s}]")
        z_s = ", ".join(f"{a}/{c}" for a, c in b['z_list'])
        bt = ", ".join(f"{x:.0f}°" for x in b['beta_list'])
        mn_s = ", ".join(f"{v:g}" for v in b['mn_list'])
        o.append(f"     z: {z_s}   β: {bt}   mn: {mn_s}")
        o.append(f"     {b['coax_msg']}")
        o.append("")
    o.append("NOT: 'En iyiyi uygula' ile 1. sıradaki tasarım forma yüklenir.")
    return "\n".join(o)


def compare_report(resA: dict, resB: dict) -> str:
    def line(lbl, a, b):
        return f"{lbl:<30}{str(a):>17}{str(b):>17}"
    o = []
    o.append("="*64)
    o.append(f"{'KARŞILAŞTIRMA':<30}{'SENARYO A':>17}{'SENARYO B':>17}")
    o.append("="*64)
    o.append(line("Kademe sayısı", len(resA['results']), len(resB['results'])))
    o.append(line("Gerçekleşen i", f"{resA['i_real_total']:.2f}", f"{resB['i_real_total']:.2f}"))
    o.append(line("Toplam verim η", f"{resA['eta_total']:.4f}", f"{resB['eta_total']:.4f}"))
    o.append(line("Yağlama", "gresli" if resA['lubricated'] else "kuru",
                  "gresli" if resB['lubricated'] else "kuru"))
    sa = sum(r.a for r in resA['results']); sb = sum(r.a for r in resB['results'])
    o.append(line("Σ eksenler arası (mm)", f"{sa:.1f}", f"{sb:.1f}"))
    va = sum(math.pi/4*(r.da1**2 + r.da2**2)*r.b for r in resA['results'])/1000
    vb = sum(math.pi/4*(r.da1**2 + r.da2**2)*r.b for r in resB['results'])/1000
    o.append(line("Dişli hacmi (cm³)", f"{va:.0f}", f"{vb:.0f}"))
    o.append(line("En büyük da (mm)",
                  f"{max(max(r.da1, r.da2) for r in resA['results']):.1f}",
                  f"{max(max(r.da1, r.da2) for r in resB['results']):.1f}"))
    o.append(line("Eş eksenli",
                  "evet" if resA.get('coax', {}).get('feasible') else "hayır",
                  "evet" if resB.get('coax', {}).get('feasible') else "hayır"))
    o.append(line("Geri sürülebilir", "evet" if resA['back_drivable'] else "hayır",
                  "evet" if resB['back_drivable'] else "hayır"))
    wa = sum(len(r.warnings) for r in resA['results'])
    wb = sum(len(r.warnings) for r in resB['results'])
    o.append(line("Uyarı sayısı", wa, wb))
    if resA['shafts'] and resB['shafts']:
        o.append(line("En büyük mil çapı (mm)",
                      f"{max(s.d_sec for s in resA['shafts']):.0f}",
                      f"{max(s.d_sec for s in resB['shafts']):.0f}"))
    o.append("-"*64)
    o.append("KADEME DETAYI")
    for k in range(max(len(resA['results']), len(resB['results']))):
        ra = resA['results'][k] if k < len(resA['results']) else None
        rb = resB['results'][k] if k < len(resB['results']) else None
        f = lambda r, s: (s(r) if r else "-")
        o.append(line(f"  K{k+1} tip", f(ra, lambda r: r.gtype), f(rb, lambda r: r.gtype)))
        o.append(line(f"  K{k+1} mn / z1-z2",
                      f(ra, lambda r: f"{r.mn:g} / {r.z1}-{r.z2}"),
                      f(rb, lambda r: f"{r.mn:g} / {r.z1}-{r.z2}")))
        o.append(line(f"  K{k+1} εα",
                      f(ra, lambda r: f"{r.eps_a:.2f}"), f(rb, lambda r: f"{r.eps_a:.2f}")))
        o.append(line(f"  K{k+1} σ1/σ_em",
                      f(ra, lambda r: f"{(r.sigma1/r.sigma_allow*100 if r.sigma_allow else 0):.0f}%"),
                      f(rb, lambda r: f"{(r.sigma1/r.sigma_allow*100 if r.sigma_allow else 0):.0f}%")))
        o.append(line(f"  K{k+1} η", f(ra, lambda r: f"{r.eta:.3f}"),
                      f(rb, lambda r: f"{r.eta:.3f}")))
        o.append(line(f"  K{k+1} Fa (N)", f(ra, lambda r: f"{r.Fa:.0f}"),
                      f(rb, lambda r: f"{r.Fa:.0f}")))
    o.append("-"*64)
    o.append("YORUM:")
    o.append(f"  • Daha verimli: {'A' if resA['eta_total'] > resB['eta_total'] else 'B'} "
             f"(Δη={abs(resA['eta_total']-resB['eta_total']):.4f})")
    o.append(f"  • Daha kompakt (hacim): {'A' if va < vb else 'B'} (Δ={abs(va-vb):.0f} cm³)")
    o.append(f"  • Daha az uyarılı: {'A' if wa < wb else ('B' if wb < wa else 'eşit')}")
    return "\n".join(o)


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

def default_cfg():
    return dict(P_in=0.25, n_in=1500, i_total=9.0, n_stages=2, lubricated=False,
                backlash=0.15, bed_size=220.0, sigma_em_mil=60.0, Lh_target=10000.0,
                T_amb=25.0, E_shaft=E_SHAFT_DEFAULT, S=1.5, bore_type="kama",
                stages=[
                    dict(gtype="helisel", material="PETG", i_stage=3.0, beta=15.0, K0=1.25),
                    dict(gtype="duz", material="PETG", i_stage=3.0, K0=1.25),
                ])


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
    root.title("Redüktör Tasarım Aracı v3 — MAKEL2 (Akkurt/DIN)")
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
