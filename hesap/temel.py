# -*- coding: utf-8 -*-
"""Yardımcı fonksiyonlar: evolvent, modül seçimi, kavrama oranı, verim, diş ucu kalınlığı, kama ve asal diş kontrolleri."""

import sys
import math
import os
import json
import struct
import datetime
import itertools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .veriler import *  # noqa: F401,F403


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
    """Alttan kesilmeyi önleyen en küçük profil kaydırma (α = 20°, z_g = 17).
    Helisel dişlide eşdeğer diş sayısı z_n = z / cos³β kullanılır."""
    z_n = z / (math.cos(math.radians(beta_deg)) ** 3)
    return max(0.0, (17.0 - z_n) / 17.0)


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
    [VDI 2736 / Wöhler eğrisi mantığı — tahmini]
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
    [Niemann / ISO-TR 14179 mantığı — tahmini]
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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
