# -*- coding: utf-8 -*-
"""Mil hesabı: kama kontrolü, kiriş çözümü, mukavemet + rijitlik (sehim/eğim)."""

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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
