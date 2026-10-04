# -*- coding: utf-8 -*-
"""Hesap sonuç yapıları (kademe, mil, rulman)."""

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
    # çark diş dibi (kendi form faktörü + kendi çevrim sayısı)
    sigma2: float = 0.0
    sigma_allow2: float = 0.0
    YN2: float = 1.0
    k_short: float = 0.0       # baş kısaltma katsayısı k (dₐ = d₀ + 2m(1 + x − k))
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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
