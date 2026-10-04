# -*- coding: utf-8 -*-
"""Tasarım arama motoru ve duyarlılık taraması."""

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
from .reduktor import *  # noqa: F401,F403


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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
