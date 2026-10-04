# -*- coding: utf-8 -*-
"""
Çark Oluşturucu — geometri motoru.

py_gearworks (build123d) ile 3B dişli katıları üretir; redüktör modunda
hesap/ paketindeki mukavemet hesabını (Akkurt / DIN yöntemi) kullanır ve
hesaplanan kademeleri mil + göbek delikleriyle birlikte montaj olarak kurar.
"""

import os
import sys
import math
import io
import zipfile
import tempfile
import copy
from dataclasses import dataclass, field
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# proje kökü (hesap/ paketi) + py_gearworks: önce depodaki kopya (vendor/)
for _p in (ROOT,
           os.path.join(ROOT, "py_gearworks-main", "py_gearworks-main", "src"),
           os.path.join(ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import build123d as bd
import py_gearworks as pgw
import hesap as rd

DEG = math.pi / 180.0
PALETTE = ["#f59e0b", "#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#fb7185",
           "#facc15", "#60a5fa"]
SHAFT_COLOR = "#9ca3af"


class GirdiHatasi(ValueError):
    """Kullanıcıya gösterilecek parametre hatası."""


# ------------------------------------------------------------------ #
#  Parça kaydı
# ------------------------------------------------------------------ #

@dataclass
class Parca:
    name: str
    shape: object
    color: str
    anim: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)
    dxf_wire: object = None          # 2B profil (XY düzleminde)
    dxf_circles: list = field(default_factory=list)


@dataclass
class Sonuc:
    parts: List[Parca]
    summary: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    report: str = ""
    anim_mode: str = "rot"           # "rot" | "osc" (kremayer: ileri-geri)


# ------------------------------------------------------------------ #
#  Yardımcılar
# ------------------------------------------------------------------ #

def _f(p, key, default, lo=None, hi=None):
    try:
        v = float(p.get(key, default))
    except (TypeError, ValueError):
        raise GirdiHatasi(f"'{key}' sayı olmalı")
    if not math.isfinite(v):
        raise GirdiHatasi(f"'{key}' geçersiz")
    if lo is not None and v < lo:
        raise GirdiHatasi(f"'{key}' en az {lo} olmalı")
    if hi is not None and v > hi:
        raise GirdiHatasi(f"'{key}' en fazla {hi} olabilir")
    return v


def _i(p, key, default, lo=None, hi=None):
    return int(round(_f(p, key, default, lo, hi)))


def _b(p, key, default=False):
    v = p.get(key, default)
    if isinstance(v, str):
        return v.lower() in ("1", "true", "evet", "on")
    return bool(v)


def _t(v):
    return (float(v.X), float(v.Y), float(v.Z))


def _axis(g):
    pl = bd.Plane(g.center_location_bottom)
    return np.array(_t(pl.z_dir))


def _pitch_point(g_drive, g_driven):
    """İki dişlinin taksimat temas noktası (yaklaşık, genel eksen konumu)."""
    O1, O2 = np.array(g_drive.center, float), np.array(g_driven.center, float)
    a2 = _axis(g_driven)
    d = O1 - O2
    d_perp = d - np.dot(d, a2) * a2
    n = np.linalg.norm(d_perp)
    if n < 1e-9:
        return None
    return O2 + g_driven.pitch_radius * d_perp / n


def speed_ratio(g_drive, w_drive, g_driven):
    """Taksimat noktasında çevresel hız eşitliğinden tahrik edilen açısal hız.
    Paralel, iç dişli ve konik çiftlerde doğru işaret + büyüklük verir."""
    P = _pitch_point(g_drive, g_driven)
    a1, a2 = _axis(g_drive), _axis(g_driven)
    z1, z2 = g_drive.number_of_teeth, g_driven.number_of_teeth
    if P is None:
        return -w_drive * z1 / z2
    O1, O2 = np.array(g_drive.center, float), np.array(g_driven.center, float)
    u1 = np.cross(a1, P - O1) * w_drive
    u2 = np.cross(a2, P - O2)
    den = float(np.dot(u2, u2))
    val = float(np.dot(u1, u2)) / den if den > 1e-12 else 0.0
    mag = abs(w_drive) * z1 / z2
    if abs(val) < 0.2 * mag:          # çapraz eksen (sonsuz vida): yalnız büyüklük
        return mag
    return math.copysign(mag, val)


def _rot_anim(g, ratio, loc=None):
    L = g.center_location_bottom
    if loc is not None:
        L = loc * L
    pl = bd.Plane(L)
    return dict(type="rot", origin=list(_t(pl.origin)),
                axis=list(_t(pl.z_dir)), ratio=ratio)


def gear_dims(g, extra=None):
    d = dict(z=int(g.number_of_teeth), m=round(float(g.module), 6),
             d0=round(2 * float(g.pitch_radius), 3))
    try:
        d["da"] = round(2 * float(g.addendum_radius), 3)
        d["df"] = round(2 * float(g.dedendum_radius), 3)
    except Exception:
        pass
    try:
        d["db"] = round(2 * float(g.r_base), 3)
    except Exception:
        pass
    if extra:
        d.update(extra)
    return d


def _loc_mid(g):
    return g.center_location_middle


def _bore_tool(bore_d, bore_type, length):
    """Merkez delik kesici katısı (yerel eksen Z, merkez orijinde)."""
    r = bore_d / 2.0
    if bore_type == "altigen":
        prof = bd.RegularPolygon(r, 6, major_radius=False)
        return bd.extrude(prof, amount=length / 2, both=True)
    tool = bd.Cylinder(r, length)
    if bore_type == "dflat":
        # D-kesit: dairenin r'den 0,15·d kadar içeriden düz kesilmiş hali
        flat = r - 0.15 * bore_d
        keep = bd.Pos(0, -r + (flat + r) / 2.0, 0) * bd.Box(2 * r + 1, flat + r, length + 1)
        tool = tool & keep
    elif bore_type == "kama":
        km = rd.din6885(bore_d)
        if km:
            b_k, _h, t2 = km
            key = bd.Box(b_k, r + t2, length, align=(bd.Align.CENTER, bd.Align.MIN,
                                                     bd.Align.CENTER))
            tool = tool + key
    return tool


def finish_gear(part, g, opt, warns, label):
    """Göbek (hub) ekle + merkez deliği aç. opt: bore_d, bore_type, hub_d, hub_len."""
    bore_d = float(opt.get("bore_d", 0) or 0)
    bore_type = opt.get("bore_type", "daire")
    hub_d = float(opt.get("hub_d", 0) or 0)
    hub_len = float(opt.get("hub_len", 0) or 0)
    height = float(opt.get("height", 10))
    circles = []
    try:
        if hub_d > 0 and hub_len > 0:
            hub = g.face_location_top * bd.Cylinder(
                hub_d / 2.0, hub_len,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            part = part.fuse(hub)
        if bore_d > 0 and bore_type != "yok":
            df = 2 * float(g.dedendum_radius)
            if bore_d >= 0.85 * df:
                warns.append(f"{label}: delik Ø{bore_d:g} diş dibine (Ø{df:.1f}) çok yakın "
                             f"-> delik açılmadı (mil ile yekpare yapın).")
            else:
                L = 4 * (height + hub_len) + 20
                tool = _loc_mid(g) * _bore_tool(bore_d, bore_type, L)
                part = part.cut(tool)
                circles.append(bore_d / 2.0)
    except Exception as e:  # geometri işlemi başarısızsa dişliyi yine de ver
        warns.append(f"{label}: göbek/delik işlemi başarısız ({e}).")
    if isinstance(part, bd.ShapeList):
        part = bd.Compound(part)
    return part, circles


def _dxf_wire(g):
    """2B diş profili, XY düzlemine (z = 0) indirilmiş halde."""
    try:
        g2 = g.copy()
        g2.reset_location()
        w = g2.build_boundary_wire()
        return w.moved(bd.Location((0, 0, -w.bounding_box().center().Z)))
    except Exception:
        return None


def _gear_opts(p, prefix, height):
    return dict(bore_d=_f(p, prefix + "bore_d", 0, 0, 500),
                bore_type=p.get(prefix + "bore_type", "daire"),
                hub_d=_f(p, prefix + "hub_d", 0, 0, 1000),
                hub_len=_f(p, prefix + "hub_len", 0, 0, 500),
                height=height)


def _common(p):
    """Tüm involüt tiplerde ortak diş parametreleri."""
    return dict(
        module=_f(p, "m", 2, 0.1, 50),
        pressure_angle=_f(p, "pa", 20, 10, 35) * DEG,
        root_fillet=_f(p, "root_fillet", 0, 0, 0.5),
        tip_fillet=_f(p, "tip_fillet", 0, 0, 0.5),
        crowning=_f(p, "crowning", 0, 0, 500),
    )


def tip_shortening(z1, z2, x1, x2, alpha_n, beta=0.0):
    """Baş kısaltma katsayısı k (x1+x2 ≠ 0 iken dip boşluğunu korumak için).
    inv α_tw = inv α_t + 2·tan α_n·(x1+x2)/(z1+z2) ;  k = (x1+x2) − (a_w − a)/m_n"""
    if abs(x1 + x2) < 1e-9:
        return 0.0
    at = math.atan(math.tan(alpha_n) / math.cos(beta))
    atw = rd.inv_involute(rd.involute(at) + 2 * math.tan(alpha_n) * (x1 + x2) / (z1 + z2), at)
    a_ref_m = (z1 + z2) / (2 * math.cos(beta))          # a / m_n
    aw_m = a_ref_m * math.cos(at) / math.cos(atw)
    return max(0.0, (x1 + x2) - (aw_m - a_ref_m))


def _backlash_coef(p, m):
    return _f(p, "backlash", 0.1, 0, 5) / m      # mm -> modül katsayısı


def _add_gear(parts, warns, g, name, color, opt, ratio, info, loc=None, pair=True):
    part = g.build_part()
    part, circles = finish_gear(part, g, opt, warns, name)
    anim = _rot_anim(g, ratio)
    if loc is not None:
        part = part.moved(loc)
        anim = _rot_anim(g, ratio, loc)
    parts.append(Parca(name=name, shape=part, color=color, anim=anim, info=info,
                       dxf_wire=_dxf_wire(g), dxf_circles=circles))


def _pair_summary(g1, g2, r12, extra=None):
    a = float(np.linalg.norm(np.array(g2.center, float) - np.array(g1.center, float)))
    s = dict(a=round(a, 3), i=round(g2.number_of_teeth / g1.number_of_teeth, 4))
    try:
        s["eps_a"] = round(float(pgw.get_contact_ratio(g1, g2)), 3)
    except Exception:
        pass
    if extra:
        s.update(extra)
    return s


# ------------------------------------------------------------------ #
#  Dişli tipleri
# ------------------------------------------------------------------ #

def build_duz(p, helical=False):
    c = _common(p)
    m = c["module"]
    h = _f(p, "width", 10, 0.5, 1000)
    z1 = _i(p, "z1", 14, 3, 400)
    z2 = _i(p, "z2", 28, 3, 400)
    pair = _b(p, "pair", True)
    x1 = _f(p, "x1", 0, -1, 1.5)
    x2 = _f(p, "x2", 0, -1, 1.5)
    bl = _backlash_coef(p, m)
    if helical:
        beta = _f(p, "beta", 20, -60, 60) * DEG
        if p.get("m_kind", "normal") == "alin":
            # girilen değer alın modülü mt -> py_gearworks normal modül ister
            c["module"] = m * math.cos(beta)
    k_sh = tip_shortening(z1, z2, x1, x2, c["pressure_angle"],
                          beta if helical else 0.0) if pair else 0.0
    kw = dict(height=h, enable_undercut=_b(p, "undercut", True), z_anchor=0.5,
              addendum_coefficient=1.0 - k_sh, **c)
    if helical:
        herr = _b(p, "herringbone", False)
        g1 = pgw.HelicalGear(number_of_teeth=z1, helix_angle=beta, herringbone=herr,
                             profile_shift=x1, backlash=bl / 2, **kw)
        g2 = pgw.HelicalGear(number_of_teeth=z2, helix_angle=-beta, herringbone=herr,
                             profile_shift=x2, backlash=bl / 2, **kw)
        mn = c["module"]
        extra = {"β": round(beta / DEG, 2), "m": round(mn, 6),
                 "m_t": round(mn / math.cos(beta), 6)}
    else:
        g1 = pgw.SpurGear(number_of_teeth=z1, profile_shift=x1, backlash=bl / 2, **kw)
        g2 = pgw.SpurGear(number_of_teeth=z2, profile_shift=x2, backlash=bl / 2, **kw)
        extra = {}
    parts, warns = [], []
    if pair:
        g2.mesh_to(g1, target_dir=pgw.RIGHT, backlash=bl, angle_bias=0)
    _add_gear(parts, warns, g1, "Dişli A", PALETTE[0], _gear_opts(p, "a_", h), 1.0,
              gear_dims(g1, dict(x=x1, b=h, **extra)))
    summary = {}
    if pair:
        r = speed_ratio(g1, 1.0, g2)
        _add_gear(parts, warns, g2, "Dişli B", PALETTE[1], _gear_opts(p, "b_", h), r,
                  gear_dims(g2, dict(x=x2, b=h, **{k: (-v if k == "β" else v)
                                                   for k, v in extra.items()})))
        summary = _pair_summary(g1, g2, r, {"k": round(k_sh, 4)} if k_sh > 0 else None)
        if math.gcd(z1, z2) != 1:
            warns.append(f"Asal diş değil: ebob({z1},{z2})={math.gcd(z1, z2)} "
                         f"-> z2={z2 + 1} veya {z2 - 1} önerilir (aşınma dağılımı).")
    zmin = rd.zmin_no_undercut(0.0 if not helical else abs(_f(p, "beta", 20)))
    if z1 < zmin and x1 < rd.x_min_profile(z1, 0 if not helical else abs(_f(p, "beta", 20))):
        warns.append(f"z1={z1} < z_min≈{zmin:.1f}: alttan kesilme var. "
                     f"x1 ≥ {rd.x_min_profile(z1):.2f} önerilir.")
    return Sonuc(parts, summary, warns)


def build_ic(p):
    c = _common(p)
    m = c["module"]
    h = _f(p, "width", 10, 0.5, 1000)
    zr = _i(p, "z_ring", 48, 12, 400)
    zp = _i(p, "z1", 16, 3, 400)
    if zr - zp < 6:
        raise GirdiHatasi("Halka diş sayısı pinyondan en az 6 fazla olmalı")
    rim = _f(p, "rim", 2.5, 1.2, 20)
    bl = _backlash_coef(p, m)
    ring = pgw.SpurRingGear(number_of_teeth=zr, height=h, outside_ring_coefficient=rim,
                            backlash=bl / 2, z_anchor=0.5, **c)
    pin = pgw.SpurGear(number_of_teeth=zp, height=h, backlash=bl / 2,
                       profile_shift=_f(p, "x1", 0, -1, 1.5), z_anchor=0.5, **c)
    pin.mesh_to(ring, target_dir=pgw.RIGHT, backlash=bl)
    parts, warns = [], []
    _add_gear(parts, warns, pin, "Pinyon", PALETTE[0], _gear_opts(p, "a_", h), 1.0,
              gear_dims(pin, dict(b=h)))
    r = speed_ratio(pin, 1.0, ring)
    ring_part = ring.build_part()
    parts.append(Parca("İç dişli (halka)", ring_part, PALETTE[1], _rot_anim(ring, r),
                       gear_dims(ring, dict(b=h, D_dış=round(2 * ring.pitch_radius
                                                            + 2 * rim * m, 2))),
                       dxf_wire=_dxf_wire(ring)))
    return Sonuc(parts, _pair_summary(pin, ring, r), warns)


def build_konik(p):
    c = _common(p)
    m = c["module"]
    h = _f(p, "width", 10, 0.5, 1000)
    z1 = _i(p, "z1", 14, 5, 200)
    z2 = _i(p, "z2", 28, 5, 200)
    sigma = _f(p, "shaft_angle", 90, 20, 160) * DEG
    spiral = _f(p, "spiral", 0, -45, 45) * DEG
    d1 = math.atan2(math.sin(sigma), z2 / z1 + math.cos(sigma))
    d2 = sigma - d1
    kw = dict(height=h, **c)
    g1 = pgw.BevelGear(number_of_teeth=z1, cone_angle=2 * d1, helix_angle=spiral,
                       profile_shift=_f(p, "x1", 0, -0.8, 0.8), **kw)
    g2 = pgw.BevelGear(number_of_teeth=z2, cone_angle=2 * d2, helix_angle=-spiral,
                       profile_shift=-_f(p, "x1", 0, -0.8, 0.8), **kw)
    g1.mesh_to(g2, target_dir=pgw.LEFT)
    parts, warns = [], []
    _add_gear(parts, warns, g1, "Pinyon", PALETTE[0], _gear_opts(p, "a_", h), 1.0,
              gear_dims(g1, {"δ": round(d1 / DEG, 2)}))
    r = speed_ratio(g1, 1.0, g2)
    _add_gear(parts, warns, g2, "Çark", PALETTE[1], _gear_opts(p, "b_", h), r,
              gear_dims(g2, {"δ": round(d2 / DEG, 2)}))
    R = m * z1 / (2 * math.sin(d1))
    if h > R / 3:
        warns.append(f"Diş genişliği b={h:g} > R/3={R / 3:.1f} (konik dişlide önerilmez).")
    return Sonuc(parts, dict(i=round(z2 / z1, 4), Σ=round(sigma / DEG, 1),
                             δ1=round(d1 / DEG, 2), δ2=round(d2 / DEG, 2),
                             R=round(R, 2)), warns)


def build_kremayer(p):
    c = _common(p)
    m = c["module"]
    h = _f(p, "width", 10, 0.5, 1000)
    z1 = _i(p, "z1", 16, 5, 300)
    zr = _i(p, "z_rack", 20, 3, 400)
    beta = _f(p, "beta", 0, -45, 45) * DEG
    bl = _backlash_coef(p, m)
    if abs(beta) > 1e-6:
        g = pgw.HelicalGear(number_of_teeth=z1, helix_angle=beta, height=h, z_anchor=0.5,
                            backlash=bl / 2, **c)
        rack = pgw.HelicalRack(number_of_teeth=zr, helix_angle=beta, height=h,
                               module=m, pressure_angle=c["pressure_angle"],
                               backlash=bl / 2)
    else:
        g = pgw.SpurGear(number_of_teeth=z1, height=h, z_anchor=0.5, backlash=bl / 2, **c)
        rack = pgw.InvoluteRack(number_of_teeth=zr, height=h, module=m,
                                pressure_angle=c["pressure_angle"], backlash=bl / 2)
    rack.mesh_to(g, target_dir=pgw.RIGHT, backlash=bl, axial_offset=-h / 2)
    rack_part = rack.build_part()
    # py_gearworks'ün kremayer mesh_to'su pinyon dişini kremayer dişinin içine
    # yerleştirebiliyor (faz hatası). Pinyonu bir adım içinde döndürüp çakışma
    # hacmini en küçük yapan açıyı bul.
    gear_raw = g.build_part()
    ax = bd.Axis(tuple(np.array(g.center, float)), tuple(_axis(g)))
    pitch_deg = 360.0 / z1

    def overlap(k):
        try:
            return (gear_raw.rotate(ax, k * pitch_deg) & rack_part).volume
        except Exception:
            return float("inf")

    cands = {k / 8: overlap(k / 8) for k in range(8)}
    best = min(cands, key=cands.get)
    for k in (best - 1 / 16, best + 1 / 16, best - 1 / 32, best + 1 / 32):
        cands[k] = overlap(k)
    best = min(cands, key=cands.get)
    parts, warns = [], []
    if cands[best] > 1e-3 * h * m * m:
        warns.append(f"Kremayer hizası tam değil (çakışma {cands[best]:.2f} mm³).")
    g.angle = g.angle + best * 2 * math.pi / z1 * (1 if _axis(g)[2] > 0 else -1)
    gear_part = gear_raw.rotate(ax, best * pitch_deg)
    part, circles = finish_gear(gear_part, g, _gear_opts(p, "a_", h), warns, "Pinyon")
    parts.append(Parca("Pinyon", part, PALETTE[0], _rot_anim(g, 1.0),
                       gear_dims(g, dict(b=h)), dxf_wire=_dxf_wire(g), dxf_circles=circles))
    # kremayer hızı: taksimat noktasındaki çevresel hız
    O = np.array(g.center, float)
    a = _axis(g)
    d = np.array(rack.position, float) - O
    d -= np.dot(d, a) * a
    P = O + g.pitch_radius * d / np.linalg.norm(d)
    v = np.cross(a, P - O)
    L = zr * math.pi * m
    parts.append(Parca("Kremayer", rack.build_part(), PALETTE[1],
                       dict(type="lin", vel=list(v), ratio=1.0),
                       dict(z=zr, m=m, L=round(L, 2), b=h)))
    amp = max(0.2, 0.3 * L / g.pitch_radius)
    return Sonuc(parts, dict(v_per_rad=round(g.pitch_radius, 3), L=round(L, 2),
                             osc_amp=amp), warns, anim_mode="osc")


def build_sikloid(p):
    m = _f(p, "m", 2, 0.1, 50)
    h = _f(p, "width", 10, 0.5, 1000)
    z1 = _i(p, "z1", 12, 4, 300)
    z2 = _i(p, "z2", 24, 4, 300)
    kc = _f(p, "cyc", 0.5, 0.1, 1.0)
    bl = _backlash_coef(p, m)
    g1 = pgw.CycloidGear(number_of_teeth=z1, module=m, height=h, z_anchor=0.5,
                         inside_cycloid_coefficient=kc, backlash=bl / 2)
    g2 = pgw.CycloidGear(number_of_teeth=z2, module=m, height=h, z_anchor=0.5,
                         inside_cycloid_coefficient=kc, backlash=bl / 2)
    g1.adapt_cycloid_radii(g2)
    g2.mesh_to(g1, target_dir=pgw.RIGHT)
    parts, warns = [], []
    _add_gear(parts, warns, g1, "Dişli A", PALETTE[0], _gear_opts(p, "a_", h), 1.0,
              gear_dims(g1, dict(b=h)))
    r = speed_ratio(g1, 1.0, g2)
    _add_gear(parts, warns, g2, "Dişli B", PALETTE[1], _gear_opts(p, "b_", h), r,
              gear_dims(g2, dict(b=h)))
    a = float(np.linalg.norm(np.array(g2.center) - np.array(g1.center)))
    return Sonuc(parts, dict(a=round(a, 3), i=round(z2 / z1, 4)), warns)


def build_planet(p):
    c = _common(p)
    m = c["module"]
    h = _f(p, "width", 10, 0.5, 1000)
    zs = _i(p, "z_sun", 15, 5, 200)
    zr = _i(p, "z_ring", 51, 20, 400)
    npl = _i(p, "n_planet", 3, 1, 12)
    beta = _f(p, "beta", 0, -45, 45) * DEG
    if (zr - zs) % 2:
        raise GirdiHatasi("Halka − güneş diş farkı çift olmalı (gezegen = (zr−zs)/2)")
    zp = (zr - zs) // 2
    if zp < 5:
        raise GirdiHatasi("Gezegen diş sayısı çok küçük; halkayı büyütün")
    gs = pgw.PlanetaryGearset(zs, zr, zp, npl)
    nmax = gs.max_num_planets(addendum_ratio=1.1)
    warns = []
    if npl > nmax:
        warns.append(f"En fazla {nmax} gezegen sığar -> {nmax} kullanıldı.")
        npl = nmax
        gs.num_planets = npl
    angles = gs.get_planet_angles_distributed()
    if (zs + zr) % npl:
        warns.append(f"(zs+zr)={zs + zr} gezegen sayısına ({npl}) bölünmüyor -> "
                     f"gezegenler tam eşit aralıklı değil.")
    bl = _backlash_coef(p, m)
    corr = math.pi / zr * ((zp + 1) % 2)
    kw = dict(height=h, z_anchor=0.5, backlash=bl / 2, **c)
    if abs(beta) > 1e-6:
        ring = pgw.HelicalRingGear(number_of_teeth=zr, helix_angle=beta, angle=corr, **kw)
        sun = pgw.HelicalGear(number_of_teeth=zs, helix_angle=-beta, **kw)
        mk_planet = lambda: pgw.HelicalGear(number_of_teeth=zp, helix_angle=beta, **kw)
    else:
        ring = pgw.SpurRingGear(number_of_teeth=zr, angle=corr, **kw)
        sun = pgw.SpurGear(number_of_teeth=zs, **kw)
        mk_planet = lambda: pgw.SpurGear(number_of_teeth=zp, **kw)
    parts = []
    wc = zs / (zs + zr)                      # halka sabit, güneş=1
    w_rel = -(1 - wc) * zs / zp              # taşıyıcıya göre gezegen dönüşü
    _add_gear(parts, warns, sun, "Güneş", PALETTE[0], _gear_opts(p, "a_", h), 1.0,
              gear_dims(sun, dict(b=h)))
    for k in range(npl):
        pl = mk_planet()
        pl.mesh_to(sun, target_dir=pgw.rotate_vector(pgw.RIGHT, angles[k]))
        part = pl.build_part()
        part, circ = finish_gear(part, pl, _gear_opts(p, "b_", h), warns, f"Gezegen {k + 1}")
        an = _rot_anim(pl, w_rel)
        an["carrier"] = wc
        parts.append(Parca(f"Gezegen {k + 1}", part, PALETTE[2], an,
                           gear_dims(pl, dict(b=h)) if k == 0 else {},
                           dxf_wire=_dxf_wire(pl) if k == 0 else None,
                           dxf_circles=circ))
    parts.append(Parca("Halka", ring.build_part(), PALETTE[1],
                       dict(type="rot", origin=[0, 0, 0], axis=[0, 0, 1], ratio=0.0),
                       gear_dims(ring, dict(b=h)), dxf_wire=_dxf_wire(ring)))
    i_ring_fixed = 1 + zr / zs
    return Sonuc(parts, dict(z_gezegen=zp, n_gezegen=npl,
                             i_güneş_taşıyıcı=round(i_ring_fixed, 4),
                             a=round(m * (zs + zp) / 2, 3)), warns)


def build_sonsuz(p):
    mx = _f(p, "m", 2, 0.2, 20)
    z1 = _i(p, "z1", 2, 1, 6)
    z2 = _i(p, "z2", 30, 10, 150)
    q = _f(p, "q", 10, 5, 20)
    h2 = _f(p, "width", 12, 1, 500)
    gam = math.atan(z1 / q)
    mn = mx * math.cos(gam)
    L = _f(p, "worm_len", 0, 0, 1000) or round((4.5 + 0.02 * z2) * mx * 2, 1)
    w = pgw.HelicalGear(number_of_teeth=z1, module=mn, helix_angle=math.pi / 2 - gam,
                        height=L, z_anchor=0.5, pressure_angle=20 * DEG)
    wh = pgw.HelicalGear(number_of_teeth=z2, module=mn, helix_angle=gam,
                         height=h2, z_anchor=0.5, pressure_angle=20 * DEG)
    w.mesh_to(wh, target_dir=pgw.RIGHT)
    parts, warns = [], []
    warns.append("Sonsuz vida, py_gearworks'te çapraz helisel dişli ile YAKLAŞIK "
                 "modellenir (globoid değil, nokta temas).")
    _add_gear(parts, warns, w, "Sonsuz vida", PALETTE[0], _gear_opts(p, "a_", L), 1.0,
              gear_dims(w, {"γ": round(gam / DEG, 2), "L": L, "m": mx,
                            "d0": round(q * mx, 3)}))
    _add_gear(parts, warns, wh, "Karşı çark", PALETTE[1], _gear_opts(p, "b_", h2),
              -z1 / z2, gear_dims(wh, dict(b=h2)))
    a = mx * (q + z2) / 2
    mu = 0.05
    eta = math.tan(gam) / math.tan(gam + math.atan(mu / math.cos(20 * DEG)))
    return Sonuc(parts, dict(i=round(z2 / z1, 3), a=round(a, 3),
                             γ=round(gam / DEG, 2), η_tahmini=round(eta, 3),
                             kendiliğinden_kilit="EVET" if gam < math.atan(mu) * 1.0 + 0.001
                             else "HAYIR"), warns)


def build_diferansiyel(p):
    """Konik dişli diferansiyel: ayna + tahrik pinyonu, 2 aks (yan) dişlisi,
    n uydu dişlisi ve istavroz mili. 'turn' (%) virajda iki tekerlek arasındaki
    hız farkını verir: sol = ω_kutu·(1+Δ), sağ = ω_kutu·(1−Δ)."""
    m = _f(p, "m", 2, 0.3, 20)
    h = _f(p, "width", 8, 1, 200)
    zs = _i(p, "z_side", 16, 8, 60)
    zp = _i(p, "z_pin", 10, 6, 40)
    npin = _i(p, "n_pin", 2, 2, 4)
    turn = _f(p, "turn", 30, -100, 100) / 100.0
    pa = _f(p, "pa", 20, 14.5, 30) * DEG
    ds = math.atan2(zs, zp)
    dp = math.pi / 2 - ds
    warns = []
    if (2 * zs) % npin:
        warns.append(f"2·z_aks={2 * zs} uydu sayısına ({npin}) bölünmüyor -> uydular "
                     f"eşit aralıkla takılamaz.")
    kw = dict(module=m, height=h, pressure_angle=pa)
    A = pgw.BevelGear(number_of_teeth=zs, cone_angle=2 * ds, **kw)
    pins = []
    for k in range(npin):
        P = pgw.BevelGear(number_of_teeth=zp, cone_angle=2 * dp, **kw)
        P.mesh_to(A, target_dir=pgw.rotate_vector(pgw.RIGHT, 2 * math.pi * k / npin))
        pins.append(P)
    B = pgw.BevelGear(number_of_teeth=zs, cone_angle=2 * ds, **kw)
    B.mesh_to(pins[0], target_dir=pgw.RIGHT)
    apex_z = float(np.array(B.center)[2]) / 2.0          # ortak koni tepesi

    parts = []
    pin_d = round(max(3.0, min(0.5 * m * zp * 0.5, 0.45 * 2 * float(pins[0].dedendum_radius))), 1)
    axle_d = round(max(4.0, 0.35 * m * zs), 1)
    z_axis = dict(origin=[0, 0, 0], axis=[0, 0, 1])
    for g, nm, w, col in ((A, "Sol aks dişlisi", 1 + turn, PALETTE[1]),
                          (B, "Sağ aks dişlisi", 1 - turn, PALETTE[3])):
        part, circ = finish_gear(g.build_part(), g, dict(bore_d=axle_d, bore_type="kama",
                                                          height=h), warns, nm)
        parts.append(Parca(nm, part, col, dict(type="rot", ratio=w, **z_axis),
                           gear_dims(g, {"δ": round(ds / DEG, 2)}),
                           dxf_wire=None, dxf_circles=circ))
    for k, P in enumerate(pins):
        part, circ = finish_gear(P.build_part(), P, dict(bore_d=pin_d, bore_type="daire",
                                                          height=h), warns, f"Uydu {k + 1}")
        an = _rot_anim(P, speed_ratio(A, turn, P))   # kutuya göre kendi dönüşü
        an["carrier"] = 1.0
        parts.append(Parca(f"Uydu dişlisi {k + 1}", part, PALETTE[2], an,
                           gear_dims(P, {"δ": round(dp / DEG, 2)}) if k == 0 else {}))
    # istavroz (uydu) mili: kutu ile döner; 4 uyduda çapraz tek parça
    reach = float(np.linalg.norm(np.array(pins[0].center)[:2])) + h
    cross = None
    for k in range(1 if npin < 4 else 2):
        ang = math.pi / 2 * k
        d = (math.cos(ang), math.sin(ang), 0.0)
        cyl = bd.Location(bd.Plane(origin=(0, 0, apex_z), z_dir=d)) * bd.Cylinder(
            pin_d / 2, 2 * reach)
        cross = cyl if cross is None else cross.fuse(cyl)
    if npin == 3:
        warns.append("3 uyduda istavroz mili gösterimi basitleştirildi (tek mil).")
    parts.append(Parca("İstavroz mili", cross, SHAFT_COLOR,
                       dict(type="rot", ratio=0.0, carrier=1.0, **z_axis),
                       dict(d=pin_d, L=round(2 * reach, 1))))

    # ayna + tahrik pinyonu
    zr = _i(p, "z_ring", 41, 20, 120)
    zd = _i(p, "z_drive", 11, 6, 40)
    mr = _f(p, "m_ring", 2.5, 0.3, 20)
    hr = _f(p, "width_ring", 12, 1, 200)
    dr = math.atan2(zr, zd)
    ring = pgw.BevelGear(number_of_teeth=zr, module=mr, height=hr, cone_angle=2 * dr,
                         pressure_angle=pa)
    drive = pgw.BevelGear(number_of_teeth=zd, module=mr, height=hr,
                          cone_angle=2 * (math.pi / 2 - dr), pressure_angle=pa)
    drive.mesh_to(ring, target_dir=pgw.rotate_vector(pgw.RIGHT, math.pi / npin))
    w_drive = speed_ratio(ring, 1.0, drive)
    ring_part = ring.build_part()
    a_min_z = min(pp.shape.bounding_box().min.Z for pp in parts[:2])
    dz = a_min_z - 3.0 - ring_part.bounding_box().max.Z
    if 2 * float(ring.dedendum_radius) * 0.85 <= 2 * reach:
        warns.append("Ayna çok küçük: diferansiyel kutusunu çevreleyemiyor -> z_ayna veya "
                     "ayna modülünü büyütün.")
    L = bd.Location((0, 0, dz))
    ring_bore = min(2 * float(ring.dedendum_radius) * 0.8, max(axle_d + 6, 1.2 * axle_d))
    rp_, circ = finish_gear(ring_part, ring, dict(bore_d=ring_bore, height=hr), warns, "Ayna")
    parts.append(Parca("Ayna dişlisi", rp_.moved(L), PALETTE[0], _rot_anim(ring, 1.0, L),
                       gear_dims(ring, {"δ": round(dr / DEG, 2)})))
    dpart, circ = finish_gear(drive.build_part(), drive, dict(bore_d=0, height=hr), warns,
                              "Tahrik pinyonu")
    parts.append(Parca("Tahrik pinyonu", dpart.moved(L), PALETTE[5],
                       _rot_anim(drive, w_drive, L),
                       gear_dims(drive, {"δ": round((math.pi / 2 - dr) / DEG, 2)})))
    # akslar
    for nm, w, z0, z1_ in (("Sol aks", 1 + turn, dz - hr - 25, a_min_z + h * 0.3),
                           ("Sağ aks", 1 - turn,
                            max(pp.shape.bounding_box().max.Z for pp in parts[:2]) - h * 0.3,
                            2 * apex_z + h + 25)):
        cyl = bd.Pos(0, 0, (z0 + z1_) / 2) * bd.Cylinder(axle_d / 2 * 0.98, z1_ - z0)
        parts.append(Parca(nm, cyl, SHAFT_COLOR, dict(type="rot", ratio=w, **z_axis),
                           dict(d=axle_d, L=round(z1_ - z0, 1))))
    i_final = zr / zd
    return Sonuc(parts, dict(i_ayna=round(i_final, 4),
                             sol_tekerlek=f"{(1 + turn) * 100:.0f} %",
                             sağ_tekerlek=f"{(1 - turn) * 100:.0f} %",
                             δ_aks=round(ds / DEG, 2), δ_uydu=round(dp / DEG, 2)), warns)


# ----- Kamalı (evolvent) mil — mil_spline.py'nin parametrik hali ----- #

def spline_profile(m, z, alpha_deg, d_tip, d_root, offset=0.0, n_flank=30, internal=False):
    a = alpha_deg * DEG
    rp = m * z / 2.0
    rb = rp * math.cos(a)
    inv = lambda x: math.tan(x) - x
    inv_p = inv(a)
    s_nom = math.pi * m / 2.0
    psi_p = s_nom / (2.0 * rp)
    pitch = 2 * math.pi / z
    delta = offset / rb

    def beta(r):
        ar = math.acos(max(-1.0, min(1.0, rb / r)))
        return psi_p + inv_p - inv(ar) + delta

    r_lo = max(d_root / 2.0, rb + 1e-4)
    r_hi = d_tip / 2.0
    radii = [r_lo + (r_hi - r_lo) * i / n_flank for i in range(n_flank + 1)]
    tooth = [(r, -beta(r)) for r in radii]
    bt = beta(r_hi)
    for i in range(1, 6):
        tooth.append((r_hi, -bt + 2 * bt * i / 6))
    tooth += [(r, beta(r)) for r in reversed(radii)]
    pts = []
    br = beta(r_lo)
    for k in range(z):
        off = k * pitch
        pts += [(r * math.cos(t + off), r * math.sin(t + off)) for (r, t) in tooth]
        a0, a1 = off + br, off + pitch - br
        for i in range(1, 5):
            t = a0 + (a1 - a0) * i / 5
            pts.append((r_lo * math.cos(t), r_lo * math.sin(t)))
    return pts


def build_mil(p):
    m = _f(p, "m", 1, 0.25, 10)
    z = _i(p, "z1", 16, 6, 60)
    alpha = _f(p, "pa", 30, 20, 45)
    d_tip = _f(p, "d_tip", 0, 0, 1000) or m * (z + 1) - 0.2
    d_root = _f(p, "d_root", 0, 0, 1000) or m * (z - 1.5) + 0.1
    off = _f(p, "offset", 0, -1, 1)
    L = _f(p, "width", 30, 1, 2000)
    if d_root >= d_tip:
        raise GirdiHatasi("Diş dibi çapı, diş üstü çapından küçük olmalı")
    pts = spline_profile(m, z, alpha, d_tip, d_root, off)
    wire = bd.Polyline(*pts, close=True)
    face = bd.make_face(wire)
    shaft = bd.extrude(face, amount=L)
    parts = [Parca("Kamalı mil", shaft, PALETTE[3],
                   dict(type="rot", origin=[0, 0, 0], axis=[0, 0, 1], ratio=1.0),
                   dict(z=z, m=m, α=alpha, D_uç=round(d_tip, 3), D_taksimat=m * z,
                        D_dip=round(d_root, 3), ofset=off, L=L),
                   dxf_wire=wire)]
    warns = []
    if _b(p, "with_hub", True):
        clr = _f(p, "hub_clear", 0.15, 0, 1)
        hub_od = _f(p, "hub_d", 0, 0, 1000) or d_tip * 1.8
        # göbek deliği: uç ve dip çaplarında 0,1 mm radyal pay + yanaklarda 'clr' boşluk
        hpts = spline_profile(m, z, alpha, d_tip + 0.2 + 2 * clr, d_root + 0.2 + 2 * clr,
                              off + clr)
        # iç profil: yiv boşluğu = milin diş profili + boşluk; mil profilini büyüterek kes
        hole = bd.extrude(bd.make_face(bd.Polyline(*hpts, close=True)), amount=L)
        hub_len = min(L * 0.6, max(8.0, d_tip))
        body = bd.Pos(0, 0, L - hub_len) * bd.Cylinder(
            hub_od / 2, hub_len, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        hub = body - hole
        parts.append(Parca("Kamalı göbek", hub, PALETTE[4],
                           dict(type="rot", origin=[0, 0, 0], axis=[0, 0, 1], ratio=1.0),
                           dict(D_dış=round(hub_od, 2), boşluk=clr, L=round(hub_len, 1))))
    rb = m * z / 2 * math.cos(alpha * DEG)
    return Sonuc(parts, dict(D_temel=round(2 * rb, 3), z=z, m=m), warns)


# ------------------------------------------------------------------ #
#  Redüktör (hesap/ paketi + py_gearworks montaj)
# ------------------------------------------------------------------ #

def reducer_cfg_from(p):
    cfg = rd.default_cfg()
    cfg.update(P_in=_f(p, "P_in", 0.25, 0.001, 5000),
               n_in=_f(p, "n_in", 1500, 1, 30000),
               i_total=_f(p, "i_total", 9, 1.01, 5000),
               lubricated=_b(p, "lubricated", False),
               backlash=_f(p, "backlash", 0.15, 0, 2),
               Lh_target=_f(p, "Lh", 10000, 100, 200000),
               S=_f(p, "S", 1.5, 1, 5),
               bed_size=_f(p, "bed", 220, 50, 5000),
               bore_type=p.get("bore_type", "kama"))
    stages = p.get("stages") or []
    if not 1 <= len(stages) <= 3:
        raise GirdiHatasi("Kademe sayısı 1–3 olmalı")
    cfg["n_stages"] = len(stages)
    out = []
    for k, s in enumerate(stages, 1):
        gt = s.get("gtype", "duz")
        if gt not in ("duz", "helisel", "konik", "worm"):
            raise GirdiHatasi(f"Kademe {k}: tip geçersiz")
        mat = s.get("material", "PETG")
        if mat not in rd.MATERIALS:
            raise GirdiHatasi(f"Kademe {k}: malzeme geçersiz")
        d = dict(gtype=gt, material=mat, i_stage=_f(s, "i_stage", 3, 1.0, 100),
                 K0=_f(s, "K0", 1.25, 1, 2))
        if gt == "helisel":
            d["beta"] = _f(s, "beta", 15, 0, 45)
        if gt == "worm":
            d["z1"] = _i(s, "z1", 2, 1, 6)
            d["q"] = _f(s, "q", 10, 5, 20)
        if s.get("z1_gear") not in (None, "", 0, "0") and gt != "worm":
            d["z1_gear"] = _i(s, "z1_gear", 17, 6, 100)
        out.append(d)
    cfg["stages"] = out
    return cfg


def _stage_gears(r, j):
    """StageResult -> (pinyon, çark) py_gearworks nesneleri, yerel çerçevede."""
    bl = j / max(r.mn, 1e-6)
    if r.gtype in ("duz", "helisel"):
        beta = r.beta * DEG
        kw = dict(module=r.mn, height=r.b, z_anchor=0.5, backlash=bl / 2,
                  addendum_coefficient=1.0 - r.k_short)
        if r.gtype == "helisel" and abs(beta) > 1e-6:
            g1 = pgw.HelicalGear(number_of_teeth=r.z1, helix_angle=beta,
                                 profile_shift=r.x1, **kw)
            g2 = pgw.HelicalGear(number_of_teeth=r.z2, helix_angle=-beta,
                                 profile_shift=r.x2, **kw)
        else:
            g1 = pgw.SpurGear(number_of_teeth=r.z1, profile_shift=r.x1, **kw)
            g2 = pgw.SpurGear(number_of_teeth=r.z2, profile_shift=r.x2, **kw)
        g2.mesh_to(g1, target_dir=pgw.RIGHT, backlash=bl)
        return g1, g2, r.b, r.b
    if r.gtype == "konik":
        d1, d2 = r.delta01 * DEG, r.delta02 * DEG
        g1 = pgw.BevelGear(number_of_teeth=r.z1, module=r.mn, height=r.b,
                           cone_angle=2 * d1)
        g2 = pgw.BevelGear(number_of_teeth=r.z2, module=r.mn, height=r.b,
                           cone_angle=2 * d2)
        g2.mesh_to(g1, target_dir=pgw.RIGHT)
        return g1, g2, r.b * 1.5, r.b * 1.5
    # worm
    gam = math.atan(r.z1 / r.q) if r.q else r.gamma * DEG
    mn = r.mn * math.cos(gam)
    Lw = round((4.5 + 0.02 * r.z2) * r.mn * 2, 1)
    b2 = r.b if r.b > 0 else 0.75 * r.q * r.mn
    g1 = pgw.HelicalGear(number_of_teeth=r.z1, module=mn, helix_angle=math.pi / 2 - gam,
                         height=Lw, z_anchor=0.5)
    g2 = pgw.HelicalGear(number_of_teeth=r.z2, module=mn, helix_angle=gam, height=b2,
                         z_anchor=0.5)
    g2.mesh_to(g1, target_dir=pgw.RIGHT)
    return g1, g2, Lw, b2


def _r_out(g):
    try:
        return float(g.max_outside_radius)
    except Exception:
        return float(g.addendum_radius)


def _xf(L, c, a):
    """Yerel (merkez, eksen) çiftini Location ile dönüştür."""
    pl = bd.Plane(L * bd.Location(bd.Plane(origin=tuple(c), z_dir=tuple(a))))
    return np.array(_t(pl.origin)), np.array(_t(pl.z_dir))


def _local_axis(g):
    pl = bd.Plane(g.center_location_middle)
    return np.array(_t(pl.origin)), np.array(_t(pl.z_dir)), _r_out(g)


_UNIT = None


def _unit_samples():
    """Birim silindir içinde sabit örnek noktalar (r≤1, |z|≤1)."""
    global _UNIT
    if _UNIT is None:
        rng = np.random.default_rng(7)
        n = 400
        r = np.sqrt(rng.random(n))
        t = rng.random(n) * 2 * np.pi
        _UNIT = np.stack([r * np.cos(t), r * np.sin(t), rng.random(n) * 2 - 1], 1)
    return _UNIT


def _cyl_points(c, a, R, H):
    u = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(a, u); e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    s = _unit_samples()
    return c + (s[:, :1] * R) * e1 + (s[:, 1:2] * R) * e2 + (s[:, 2:3] * H) * a


def _overlap(new, old):
    """Yeni vekillerin eskilerle kesişim hacmi (Monte-Carlo tahmini, mm³).
    Her çiftte küçük hacimli silindirden örneklenir; ince mil uçları kaçmasın."""
    tot = 0.0
    for sa, pa in new:
        for sb, pb in old:
            if sa == sb:
                continue
            (c, a, R, H), (c2, a2, R2, H2) = pa, pb
            if np.linalg.norm(c - c2) > math.hypot(R, H) + math.hypot(R2, H2):
                continue
            if R * R * H > R2 * R2 * H2:
                (c, a, R, H), (c2, a2, R2, H2) = pb, pa
            pts = _cyl_points(c, a, R, H)
            d = pts - c2
            ax = d @ a2
            rad = np.linalg.norm(d - np.outer(ax, a2), axis=1)
            frac = np.mean((np.abs(ax) <= H2) & (rad <= R2))
            tot += frac * math.pi * R * R * 2 * H
    return tot


def _extent(prox):
    pts = []
    for _, (c, a, R, H) in prox:
        pts += [c + a * H, c - a * H]
    pts = np.array(pts)
    rmax = max(R for _, (c, a, R, H) in prox)
    return float(np.linalg.norm(pts.max(0) - pts.min(0))) + rmax


def _layout_stages(stages, shafts, gap=4.0):
    """Her kademeyi bir önceki çarkın ekseni üzerine yerleştirir; mil etrafındaki açı,
    eksen yönü (±) ve eksenel mesafe çakışmasız ve en kompakt olacak şekilde seçilir."""
    locs, placed, prev_wheel_c = [], [], None
    loc_ax = [(_local_axis(g1), _local_axis(g2)) for g1, g2, _, _ in stages]
    for k, (g1, g2, w1, w2) in enumerate(stages):
        d_in = shafts[k].d_sec if k < len(shafts) else 10
        d_out = shafts[k + 1].d_sec if k + 1 < len(shafts) else 10
        (c1, a1, R1), (c2, a2, R2) = loc_ax[k]
        mid1_inv = g1.center_location_middle.inverse()
        if k == 0:
            cands = [mid1_inv]
        else:
            pg1, pg2, pw1, pw2 = stages[k - 1]
            base = locs[-1] * pg2.center_location_middle
            dz0 = pw2 / 2 + gap + w1 / 2
            dzs = [dz0, dz0 + R2 * 0.6, dz0 + R2 + loc_ax[k - 1][1][2] * 0.2]
            cands = [base * bd.Pos(0, 0, sg * dz) * bd.Rot(0, 0, phi) * mid1_inv
                     for dz in dzs for sg in (1, -1) for phi in range(0, 360, 30)]
        best = None
        for L in cands:
            gc1, ga1 = _xf(L, c1, a1)
            gc2, ga2 = _xf(L, c2, a2)
            new = [(k, (gc1, ga1, R1, w1 / 2)), (k, (gc1, ga1, max(d_in / 2, 1), w1 / 2 + 15)),
                   (k + 1, (gc2, ga2, R2, w2 / 2)),
                   (k + 1, (gc2, ga2, max(d_out / 2, 1), w2 / 2 + 15))]
            if prev_wheel_c is not None:   # önceki çark ile bu pinyon arasındaki mil
                seg_len = float(np.linalg.norm(gc1 - prev_wheel_c))
                if seg_len > 1e-6:
                    new.append((k, ((prev_wheel_c + gc1) / 2, (gc1 - prev_wheel_c) / seg_len,
                                    max(d_in / 2, 1), seg_len / 2)))
            ov = _overlap(new, placed) if placed else 0.0
            key = (ov > 0.5, round(ov / 50.0), round(_extent(placed + new), 0))
            if best is None or key < best[0]:
                best = (key, L, new, gc2)
        locs.append(best[1])
        placed += best[2]
        prev_wheel_c = best[3]
    return locs


def build_reduktor(p):
    cfg = reducer_cfg_from(p)
    res = rd.calc_reducer(cfg)
    report = rd.report_full(res)
    results, shafts = res["results"], res["shafts"]
    bore_type = cfg.get("bore_type", "kama")
    j = cfg.get("backlash", 0.15)
    parts, warns = [], []
    stages = [_stage_gears(r, j) for r in results]
    locs = _layout_stages(stages, shafts)
    w = 1.0                         # giriş mili açısal hızı
    shaft_gears = [[] for _ in range(len(results) + 1)]   # (loc, gear, genişlik, hız)
    for k, r in enumerate(results):
        g1, g2, w1_len, w2_len = stages[k]
        L = locs[k]
        d_in = shafts[k].d_sec if k < len(shafts) else 0
        d_out = shafts[k + 1].d_sec if k + 1 < len(shafts) else 0
        w2 = speed_ratio(g1, w, g2) if r.gtype != "worm" else -w * r.z1 / r.z2
        if r.gtype == "worm" and (d_in + d_out) / 2 > r.a:
            warns.append(f"K{k + 1}: mil yarıçapları toplamı ({(d_in + d_out) / 2:.1f} mm) "
                         f"eksen mesafesinden (a={r.a:.1f} mm) büyük -> vida mili ile çark "
                         f"mili çakışır; modülü/q'yu büyütün.")
        for g, nm, col, d_b, ww, wl in ((g1, "pinyon", PALETTE[(2 * k) % 8], d_in, w, w1_len),
                                        (g2, "çark", PALETTE[(2 * k + 1) % 8], d_out, w2,
                                         w2_len)):
            label = f"K{k + 1} {nm}"
            part = g.build_part()
            opt = dict(bore_d=d_b, bore_type=bore_type, height=wl)
            part, circ = finish_gear(part, g, opt, warns, label)
            part = part.moved(L)
            info = gear_dims(g, dict(tip=r.gtype, malzeme=r.material,
                                     b=round(r.b, 2), x=round(r.x1 if nm == "pinyon"
                                                              else r.x2, 3)))
            parts.append(Parca(label, part, col, _rot_anim(g, ww, L), info,
                               dxf_wire=_dxf_wire(g), dxf_circles=circ))
            shaft_gears[k if nm == "pinyon" else k + 1].append((L, g, wl, ww))
        w = w2
    # miller
    for s_idx, lst in enumerate(shaft_gears):
        if not lst or s_idx >= len(shafts):
            continue
        d = shafts[s_idx].d_sec
        L0, g0, _, ww = lst[0]
        pl = bd.Plane(L0 * g0.center_location_middle)
        O, a = np.array(_t(pl.origin)), np.array(_t(pl.z_dir))
        ts = []
        for Lg, g, wl, _ in lst:
            c = np.array(_t(bd.Plane(Lg * g.center_location_middle).origin))
            t = float(np.dot(c - O, a))
            ts += [t - wl / 2, t + wl / 2]
        t0, t1 = min(ts) - 15, max(ts) + 15
        mid = O + a * (t0 + t1) / 2
        loc = bd.Location(bd.Plane(origin=tuple(mid), z_dir=tuple(a)))
        cyl = loc * bd.Cylinder(d / 2, t1 - t0)
        name = "Giriş mili" if s_idx == 0 else ("Çıkış mili" if s_idx == len(shafts) - 1
                                                  else f"Ara mil {s_idx}")
        parts.append(Parca(name, cyl, SHAFT_COLOR,
                           dict(type="rot", origin=list(O), axis=list(a), ratio=ww),
                           dict(d=d, L=round(t1 - t0, 1),
                                n_rpm=round(shafts[s_idx].n_rpm, 1))))
    summ = dict(i_hedef=cfg["i_total"], i_gerçek=round(res["i_real_total"], 4),
                η_toplam=round(res["eta_total"], 4),
                n_çıkış=round(cfg["n_in"] / res["i_real_total"], 2))
    for r in results:
        for wmsg in r.warnings:
            warns.append(f"K{r.idx}: {wmsg}")
    for wmsg in res.get("system_warnings", []):
        warns.append(wmsg)
    stage_tbl = [dict(k=r.idx, tip=r.gtype, z1=r.z1, z2=r.z2, m=r.mn, b=round(r.b, 2),
                      a=round(r.a, 2), i=round(r.i_real, 3), σ=round(r.sigma1, 2),
                      σ_em=round(r.sigma_allow, 2), ok=bool(r.root_ok),
                      εα=round(r.eps_a, 3), η=round(r.eta, 4)) for r in results]
    summ["kademeler"] = stage_tbl
    return Sonuc(parts, summ, warns, report=report)


def reducer_search(p):
    cfg = reducer_cfg_from(p)
    obj = p.get("objective", "koaksiyel")
    if obj not in ("koaksiyel", "min_hacim", "max_verim", "oran_hassas"):
        raise GirdiHatasi("Amaç geçersiz")
    best = rd.search_designs(cfg, objective=obj, n_best=5, max_evals=4000)
    return dict(report=rd.report_search(best, obj),
                best=[dict(cfg=b["cfg"], i_real=b["i_real"], eta=b["eta"],
                           volume=b["volume"], coax_err=b["coax_err"],
                           z_list=b["z_list"], mn_list=b["mn_list"]) for b in best])


# ------------------------------------------------------------------ #
#  Duyarlılık analizi (hesap/ paketi ile parametre taraması)
# ------------------------------------------------------------------ #

SWEEP_DEFS = {
    # param: (etiket, birim, alt, üst, adım sayısı, uygun tipler, varsayılan)
    "x1": ("Profil kaydırma x₁", "", -0.5, 0.8, 27, ("duz", "helisel"), 0.0),
    "beta": ("Helis açısı β", "°", 0.0, 35.0, 36, ("helisel",), 15.0),
    "q": ("Çap katsayısı q", "", 6.0, 18.0, 25, ("worm",), 10.0),
    "phi_m": ("Genişlik oranı φm = b/mm", "", 4.0, 12.0, 17, ("konik",), 10.0),
    "i_stage": ("Kademe oranı i", "", 1.5, 6.0, 19, ("duz", "helisel", "konik"), None),
}


def _sweep_metrics(param, r):
    """Taramada izlenen büyüklükler: (ad, birim, değer, sınır, sınır türü, sınır etiketi)."""
    if param == "x1":
        return [("Diş dibi gerilmesi σ₁", "N/mm²", r.sigma1, r.sigma_allow, "max", "σ_em / S"),
                ("Diş ucu kalınlığı sₐ₁", "mm", r.sa1, r.sa_lim, "min", "sivrilme sınırı"),
                ("Kavrama oranı εα", "", r.eps_a, 1.1, "min", "εα ≥ 1,1")]
    if param == "beta":
        return [("Eksenel kuvvet Fa", "N", r.Fa, None, None, None),
                ("Diş dibi gerilmesi σ₁", "N/mm²", r.sigma1, r.sigma_allow, "max", "σ_em / S"),
                ("Örtüşme oranı εβ", "", r.eps_b, 1.0, "min", "εβ ≥ 1 önerilir")]
    if param == "q":
        return [("Verim η", "%", r.eta * 100, None, None, None),
                ("Helis açısı γ", "°", r.gamma, None, None, None),
                ("Eksenel kuvvet Fa", "N", r.Fa, None, None, None)]
    if param == "phi_m":
        return [("Ortalama modül mm", "mm", r.mt, None, None, None),
                ("Diş genişliği b", "mm", r.b, None, None, None),
                ("Diş dibi gerilmesi σ₁", "N/mm²", r.sigma1, r.sigma_allow, "max",
                 "σ_em / S")]
    # i_stage
    return [("Diş dibi gerilmesi σ₁", "N/mm²", r.sigma1, r.sigma_allow, "max", "σ_em / S"),
            ("Eksen mesafesi a", "mm", r.a, None, None, None),
            ("Kademe verimi η", "%", r.eta * 100, None, None, None)]


def sweep_analysis(p, stage_idx, param):
    """Bir kademenin tek parametresini tarar; her büyüklük ayrı panel olarak döner."""
    cfg = reducer_cfg_from(p)
    if not 0 <= stage_idx < len(cfg["stages"]):
        raise GirdiHatasi("Kademe yok")
    if param not in SWEEP_DEFS:
        raise GirdiHatasi("Parametre geçersiz")
    label, unit, lo, hi, n, gtypes, cur = SWEEP_DEFS[param]
    st = cfg["stages"][stage_idx]
    if st["gtype"] not in gtypes:
        raise GirdiHatasi(f"Bu parametre {st['gtype']} kademesi için anlamlı değil")
    current = st.get(param, cur)
    if param == "phi_m" and current is None:
        current = 10.0
    if param == "i_stage":
        current = st["i_stage"]
    xs = [lo + (hi - lo) * k / (n - 1) for k in range(n)]
    panels = None
    for xv in xs:
        c = dict(cfg, stages=[dict(s_) for s_ in cfg["stages"]])
        c["stages"][stage_idx][param] = xv
        try:
            r = rd.calc_reducer(c, light=True)["results"][stage_idx]
            mets = _sweep_metrics(param, r)
        except Exception:
            mets = None
        if panels is None and mets:
            panels = [dict(name=m[0], unit=m[1], y=[], lim=[], kind=m[4], limit_label=m[5])
                      for m in mets]
        if panels is None:
            continue
        for k, pnl in enumerate(panels):
            v = mets[k][2] if mets else None
            lv = mets[k][3] if mets else None
            pnl["y"].append(None if v is None or not math.isfinite(v) else round(float(v), 5))
            pnl["lim"].append(None if lv is None else round(float(lv), 5))
    if panels is None:
        raise GirdiHatasi("Tarama hesaplanamadı")
    # baştaki başarısız noktalar için y dizilerini hizala
    for pnl in panels:
        pad = [None] * (len(xs) - len(pnl["y"]))
        pnl["y"] = pad + pnl["y"]
        pnl["lim"] = pad + pnl["lim"]
        if pnl["kind"] is None:
            pnl.pop("lim")
    return dict(x=[round(x, 4) for x in xs], xlabel=label, xunit=unit, current=current,
                stage=stage_idx + 1, gtype=st["gtype"], material=st["material"],
                panels=panels)


def sweep_options(gtype):
    return [dict(id=k, label=v[0]) for k, v in SWEEP_DEFS.items() if gtype in v[5]]


BUILDERS = {
    "duz": build_duz,
    "helisel": lambda p: build_duz(p, helical=True),
    "ic": build_ic,
    "konik": build_konik,
    "kremayer": build_kremayer,
    "sikloid": build_sikloid,
    "planet": build_planet,
    "sonsuz": build_sonsuz,
    "mil": build_mil,
    "diferansiyel": build_diferansiyel,
    "reduktor": build_reduktor,
}


def build(kind, params):
    if kind not in BUILDERS:
        raise GirdiHatasi("Bilinmeyen dişli tipi")
    return BUILDERS[kind](params)


# ------------------------------------------------------------------ #
#  Ağ (mesh) + dışa aktarma
# ------------------------------------------------------------------ #

def tessellate(shape, tol=0.02, ang=0.2):
    verts, tris = shape.tessellate(tol, ang)
    v = np.array([_t(vv) for vv in verts], dtype=np.float32).reshape(-1)
    t = np.array(tris, dtype=np.uint32).reshape(-1)
    return v, t


def _tol_for(shape):
    bb = shape.bounding_box()
    size = max(bb.size.X, bb.size.Y, bb.size.Z, 1.0)
    return max(0.005, size / 3000.0)


def export_file(sonuc: Sonuc, fmt: str, index: Optional[int]):
    """(dosya_adı, bytes, mime) döndürür. index=None -> hepsi (zip / tek montaj)."""
    sel = sonuc.parts if index is None else [sonuc.parts[index]]
    tmpdir = tempfile.mkdtemp(prefix="cark_")

    def safe(n):
        tr = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosuCGIOSU_")
        return "".join(ch for ch in n.translate(tr) if ch.isalnum() or ch in "_-")

    def one(part, fmt_):
        fn = os.path.join(tmpdir, safe(part.name) + "." + fmt_)
        if fmt_ == "stl":
            bd.export_stl(part.shape, fn, tolerance=_tol_for(part.shape) / 2,
                          angular_tolerance=0.1)
        elif fmt_ == "step":
            bd.export_step(part.shape, fn)
        elif fmt_ == "dxf":
            if part.dxf_wire is None:
                return None
            ex = bd.ExportDXF(unit=bd.Unit.MM)
            ex.add_layer("PROFIL")
            ex.add_layer("DELIK", color=bd.ColorIndex.RED)
            ex.add_shape(part.dxf_wire, layer="PROFIL")
            for rr in part.dxf_circles:
                ex.add_shape(bd.Circle(rr).edges(), layer="DELIK")
            ex.write(fn)
        elif fmt_ == "3mf":
            m = bd.Mesher()
            m.add_shape(part.shape, linear_deflection=_tol_for(part.shape) / 2)
            m.write(fn)
        return fn

    if fmt == "step" and index is None and len(sel) > 1:
        fn = os.path.join(tmpdir, "montaj.step")
        comp = bd.Compound(children=[_labeled(p_) for p_ in sel])
        bd.export_step(comp, fn)
        return "montaj.step", open(fn, "rb").read(), "application/step"

    files = [f for f in (one(p_, fmt) for p_ in sel) if f]
    if not files:
        raise GirdiHatasi("Bu parça için DXF profili yok (konik/kremayer/mil gövdesi 3B'dir)")
    if len(files) == 1:
        name = os.path.basename(files[0])
        return name, open(files[0], "rb").read(), "application/octet-stream"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, os.path.basename(f))
    return f"disliler_{fmt}.zip", buf.getvalue(), "application/zip"


def _labeled(p_):
    s = copy.copy(p_.shape)       # montaja bağlanan kopya; orijinal şekil değişmesin
    try:
        s.label = p_.name
        s.color = bd.Color(p_.color)
    except Exception:
        pass
    return s
