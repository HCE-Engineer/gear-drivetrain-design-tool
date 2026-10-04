# -*- coding: utf-8 -*-
"""Kademe hesapları: düz / helisel, düz konik, sonsuz vida."""

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
from .temel import *  # noqa: F401,F403
from .sonuclar import *  # noqa: F401,F403


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
    DÜZ / HELİSEL kademe.  Kaynak: Akkurt, Makina Elemanları Cilt II — alın dişliler (diş dibi + yüzey basıncı)
      mn ≥ [2·Mb/(z1²·ψd·σem)·cos²β·Kf·K0·Kv·Km]^(1/3)
      σ1 = Ft/(b·mn)·Kf·K0·Kv·Km ≤ σ_izin = σ_em·Y_N/S
    Boyutlandırma ve kontrol AYNI izin verilen gerilmeyi (σ_izin) kullanır; böylece
    boyutlandırılan dişli, standart modüle yuvarlanmadan önce bile kontrolü geçer.
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
    sigma_izin = sigma_em / S                     # emniyetli izin verilen gerilme

    # boyutlandırma — diş dibi
    inside = (2.0*Mb)/(z1**2 * psi_d * sigma_izin) * (math.cos(beta)**2) * Kf*K0*Kv*Km
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
        # baş kısaltma: k·mn = a_ref + (x1+x2)·mn − a ; dip boşluğu korunur
        k = (x1 + x2) - (r.a - a_ref)/mn
        if k > 1e-6:
            r.k_short = k
            r.da1 -= 2.0*k*mn
            r.da2 -= 2.0*k*mn
            r.notes.append(f"Baş kısaltma k={k:.4f} -> da1={r.da1:.2f}, da2={r.da2:.2f} mm "
                           f"(dip boşluğu 0,25·m korunur)")
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
    r.sigma_allow = sigma_izin
    pin_ok = r.sigma1 <= r.sigma_allow
    if not pin_ok:
        r.warnings.append(f"Pinyon diş dibi σ1={r.sigma1:.1f} > σ_em(N)/S={r.sigma_allow:.1f} "
                          f"N/mm² -> modülü/ψd'yi artır veya malzeme değiştir.")
    # çark diş dibi: kendi form faktörü (z2) ve kendi çevrim sayısı (n2 = n1/i)
    z_eq2 = z2 / (math.cos(beta) ** 3) if beta_deg > 0 else z2
    Kf2 = form_factor_Kf(z_eq2, x2)
    r.YN2, _ = life_factor(n_in / r.i_real, Lh, mat["sn_exp"])
    r.sigma2 = r.Ft/(r.b*mn)*Kf2*K0*Kv*Km
    r.sigma_allow2 = mat["sigma_em"]*r.YN2/S
    whl_ok = r.sigma2 <= r.sigma_allow2
    if not whl_ok:
        r.warnings.append(f"Çark diş dibi σ2={r.sigma2:.1f} > σ_em(N2)/S={r.sigma_allow2:.1f} "
                          f"N/mm² -> modülü/ψd'yi artır.")
    r.root_ok = pin_ok and whl_ok

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
        r.warnings.append(f"z1={z1} < z_min={zmin:.1f} -> alttan kesilme. "
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
    DÜZ KONİK DİŞLİ.  Kaynak: Akkurt, Makina Elemanları Cilt II — konik dişliler:
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
      σ1 = Ft/(b·mm)·K0·KF·Kv ≤ σ_izin = σ_em·Y_N/S   (boyutlandırmada da σ_izin)
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

    # --- koni açıları ---
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
    sigma_izin = sigma_em / S

    # --- boyutlandırma: ortalama modül mm (konikte Km katsayısı kullanılmaz) ---
    mm_min = (2.0*Md*K0*Kf*Kv/(sigma_izin*z1*phi_m)) ** (1.0/3.0)
    r.mn_root = mm_min
    r.mn_hertz = 0.0                     # konikte yüzey basıncı kontrolü bu sürümde yok

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

    # --- baş/taban ölçüleri (bu modülde db = baş, dt = taban çapı) ---
    hb, ht = m_std, 1.2*m_std
    r.da1 = d01 + 2.0*hb*math.cos(d01_ang)     # db1 (baş)
    r.da2 = d02 + 2.0*hb*math.cos(d02_ang)     # db2
    r.df1 = d01 - 2.0*ht*math.cos(d01_ang)     # dt1 (taban)
    r.df2 = d02 - 2.0*ht*math.cos(d02_ang)     # dt2
    r.db1 = 0.0                                # konikte temel daire kullanılmıyor

    # --- kuvvetler ---
    r.Ft = 2.0*Md/(z1*mm)                      # = 2·Md/d0m1
    r.Fa = r.Ft*math.tan(ALPHA_N)*math.sin(d01_ang)
    r.Fr = r.Ft*math.tan(ALPHA_N)*math.cos(d01_ang)
    r.v = math.pi*r.d0m1*n_in/60000.0

    # --- diş dibi kontrolü (Km YOK) ---
    r.sigma1 = r.Ft/(b*mm)*K0*Kf*Kv
    r.sigma_allow = sigma_izin
    r.root_ok = r.sigma1 <= r.sigma_allow
    if not r.root_ok:
        r.warnings.append(f"Diş dibi σ1={r.sigma1:.1f} > σ_em(N)/S={r.sigma_allow:.1f} "
                          f"N/mm² -> modülü veya φm'i artır.")

    # --- kontroller ---
    phi_m_real = b/mm                      # gerçekleşen φm = b/mm
    r.phi_m = phi_m_real
    if phi_m_real > 10.0:
        r.warnings.append(f"φm=b/mm={phi_m_real:.1f} > 10 -> önerilen sınır (φm ≤ 10) aşıldı.")
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
                   f"mukavemet ORTALAMA modül üzerinden hesaplanır.")
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
    SONSUZ VİDA — Kaynak: DIN 3975, Niemann (Maschinenelemente Bd. III)
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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
