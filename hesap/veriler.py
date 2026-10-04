# -*- coding: utf-8 -*-
"""Standart veriler: modül serisi, malzemeler, rulman kataloğu, DIN 6885."""

import sys
import math
import os
import json
import struct
import datetime
import itertools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ================================================================== #
#  BÖLÜM 0 — STANDART VERİLER
# ================================================================== #

STD_MODULES = [0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0,
               5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 25.0]     # DIN 780

MIN_MODULE_FDM = 1.0
ALPHA_N = math.radians(20.0)
E_SHAFT_DEFAULT = 210000.0     # çelik mil E (N/mm²)

# --- MALZEME VERİTABANI ---
#  sigma_em : diş dibi sürekli mukavemeti (N/mm²)    [10^6 çevrimde referans]
#             izin verilen gerilme = sigma_em · Y_N / S  (boyutlandırma VE kontrolde aynı)
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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
