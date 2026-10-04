# -*- coding: utf-8 -*-
"""
README grafiklerini üretir. Veri, uygulamadaki "Grafik" sekmesiyle aynı fonksiyondan
(motor.sweep_analysis -> hesap/ paketi) gelir.

    pip install matplotlib      # yalnızca bu betik için gerekir
    python docs/grafik_uret.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "uygulama"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import motor  # noqa: E402

# Örnek redüktör: 0,25 kW · 1500 d/dk · i = 9, PETG, 2 kademe
ORNEK = dict(P_in=0.25, n_in=1500, i_total=9, stages=[
    dict(gtype="helisel", material="PETG", i_stage=3, beta=15),
    dict(gtype="duz", material="PETG", i_stage=3)])

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES, CRITICAL = "#2a78d6", "#e34948"

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
})


def ciz(stage, param, baslik, dosya):
    d = motor.sweep_analysis(ORNEK, stage, param)
    n = len(d["panels"])
    fig, axes = plt.subplots(1, n, figsize=(4.1 * n, 3.3), facecolor=SURFACE)
    fig.suptitle(baslik, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    x = d["x"]
    for ax, p in zip(axes, d["panels"]):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        y = [float("nan") if v is None else v for v in p["y"]]
        vals = [v for v in y if v == v]
        lim = None
        if p.get("lim"):
            lim = [float("nan") if v is None else v for v in p["lim"]]
            vals += [v for v in lim if v == v]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or abs(hi) or 1.0
        lo, hi = lo - 0.18 * span, hi + 0.18 * span      # etiketler için pay
        if min(vals) >= 0 and lo < 0:
            lo = 0 if p.get("kind") != "min" else lo
        ax.set_ylim(lo, hi)
        if lim:
            edge = hi if p["kind"] == "max" else lo
            ax.fill_between(x, lim, edge, color=CRITICAL, alpha=0.08, lw=0)
            ax.plot(x, lim, color=CRITICAL, lw=1.5, ls=(0, (5, 4)))
            ax.annotate(p["limit_label"], (x[0], lim[0]), xytext=(4, 5 if p["kind"] == "max" else -5),
                        textcoords="offset points", color=CRITICAL, fontsize=9,
                        va="bottom" if p["kind"] == "max" else "top")
        ax.plot(x, y, color=SERIES, lw=2.2, solid_capstyle="round")
        ax.axvline(d["current"], color=INK2, lw=1, ls=(0, (2, 3)))
        ax.annotate("mevcut", (d["current"], 0), xycoords=("data", "axes fraction"),
                    xytext=(4, 4), textcoords="offset points", color=INK2, fontsize=8.5)
        ax.set_title(p["name"] + (f"  ({p['unit']})" if p["unit"] else ""), loc="left",
                     fontsize=10.5, color=INK, pad=8)
        ax.set_xlabel(d["xlabel"] + (f" ({d['xunit']})" if d["xunit"] else ""))
    fig.text(0.01, 0.015, "Kaynak: hesap/ paketi (Akkurt / DIN) — her nokta tam kademe hesabıyla "
             "yeniden hesaplandı. Kırmızı bölge: emniyet sınırı dışında.",
             fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    out = os.path.join(HERE, "images", dosya)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print("yazıldı:", out)


if __name__ == "__main__":
    ciz(0, "x1", "Profil kaydırma x₁ dişliyi nasıl etkiler? (Kademe 1, helisel, PETG)",
        "grafik-profil-kaydirma.png")
    ciz(0, "beta", "Helis açısı β seçimi (Kademe 1, helisel, PETG)",
        "grafik-helis-acisi.png")
