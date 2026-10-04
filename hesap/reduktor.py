# -*- coding: utf-8 -*-
"""Redüktör zinciri: kademeler -> miller -> rulmanlar -> eş eksenlilik."""

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
from .disli import *  # noqa: F401,F403
from .mil import *  # noqa: F401,F403
from .rulman import *  # noqa: F401,F403


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
    results = []

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
                   system_warnings=[])
        return out

    shafts = calc_shafts(results, sigma_em_mil=cfg.get('sigma_em_mil', 60.0),
                         L_factor=cfg.get('L_factor', 3.0),
                         E_shaft=cfg.get('E_shaft', E_SHAFT_DEFAULT))
    apply_key_checks(results, shafts)            # ÖZELLİK 4
    bearings = [calc_bearing(s, Lh_target=Lh) for s in shafts]
    coax = check_coaxial(results)                # ÖZELLİK 1
    locked = any(r.self_locking for r in results if r.gtype == "worm")

    pw = ["EŞ EKSENLİLİK: " + coax['msg']]

    out.update(shafts=shafts, bearings=bearings, coax=coax,
               back_drivable=(not locked), system_warnings=pw)
    return out



def default_cfg():
    return dict(P_in=0.25, n_in=1500, i_total=9.0, n_stages=2, lubricated=False,
                backlash=0.15, bed_size=220.0, sigma_em_mil=60.0, Lh_target=10000.0,
                T_amb=25.0, E_shaft=E_SHAFT_DEFAULT, S=1.5, bore_type="kama",
                stages=[
                    dict(gtype="helisel", material="PETG", i_stage=3.0, beta=15.0, K0=1.25),
                    dict(gtype="duz", material="PETG", i_stage=3.0, K0=1.25),
                ])


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
