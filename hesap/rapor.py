# -*- coding: utf-8 -*-
"""Metin rapor üretimi."""

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
from .arama import *  # noqa: F401,F403


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
             f"{r.sigma_em_eff:.1f} N/mm²   ->  izin verilen σ_em·Y_N/S = "
             f"{r.sigma_allow:.2f} N/mm² (boyutlandırma ve kontrolde aynı)")

    o.append("")
    o.append("-- BOYUTLANDIRMA --")
    if r.gtype == "konik":
        o.append(f"  Diş dibinden: mm ≥ [2·Md·K0·KF·Kv/(σem·z1·φm)]^(1/3) = "
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
        o.append("  NOT: konik dişlide db = BAŞ, dt = TABAN çapıdır "
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
        o.append("-- DİŞ DİBİ KONTROLÜ --  σ = Ft/(b·mn)·Kf·K0·Kv·Km ≤ σ_em·Y_N/S")
    if r.gtype == "konik":
        o.append(_box([f"σ1 = {r.sigma1:.2f} N/mm²",
                       f"σ_em(N)/S = {r.sigma_allow:.2f} N/mm²  -> {_ok(r.root_ok)}"]))
    elif r.gtype != "worm":
        o.append(_box([f"Pinyon: σ1 = {r.sigma1:.2f} ≤ {r.sigma_allow:.2f} N/mm²  "
                       f"-> {_ok(r.sigma1 <= r.sigma_allow)}",
                       f"Çark:   σ2 = {r.sigma2:.2f} ≤ {r.sigma_allow2:.2f} N/mm²  "
                       f"-> {_ok(r.sigma2 <= r.sigma_allow2)}   (Y_N2 = {r.YN2:.3f})"]))
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
    if res['system_warnings']:
        o.append("GENEL KONTROLLER:")
        for w in res['system_warnings']:
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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
