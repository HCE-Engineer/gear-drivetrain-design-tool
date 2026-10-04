# -*- coding: utf-8 -*-
"""Rulman seçimi ve L10h ömür hesabı."""

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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
