#!/usr/bin/env python3
"""
MIL (dis / external) evolvent cok kamali profil  -  m=1, z=16, 30 deg
Tek profil, tek dosya. Gobek yok.

Ayarlar:
  OFFSET : yanak basina duzeltme [mm].  0 = nominal
           negatif => dis inceler (baski sismesini telafi etmek icin)
           pozitif => dis kalinlasir
"""
import math

M          = 1.0        # modul
Z          = 16         # dis sayisi
ALPHA      = math.radians(30.0)
S_NOM      = math.pi * M / 2.0   # bolum dairesinde nominal dis kalinligi = 1.5708

D_TIP      = 16.80      # dis ustu capi  (nominal 17.0; tepe temas etmesin diye 0.2 dusuruldu)
D_ROOT     = 14.60      # dis dibi capi  (nominal 14.5; +0.1 kok bosluk)
OFFSET     = 0.00       # yanak basina duzeltme [mm]

N_FLANK    = 30         # yanak nokta sayisi
# -----------------------------------------------------------------------------
RP = M * Z / 2.0
RB = RP * math.cos(ALPHA)
inv = lambda a: math.tan(a) - a
INV_P = inv(ALPHA)
PSI_P = S_NOM / (2.0 * RP)
PITCH = 2.0 * math.pi / Z
DELTA = OFFSET / RB          # normal ofset = taban dairesinde bu kadar dondurme


def beta(r):
    ar = math.acos(max(-1.0, min(1.0, RB / r)))
    return PSI_P + INV_P - inv(ar) + DELTA


def mil_profili():
    r_lo = max(D_ROOT / 2.0, RB + 1e-4)
    r_hi = D_TIP / 2.0
    radii = [r_lo + (r_hi - r_lo) * i / N_FLANK for i in range(N_FLANK + 1)]
    tooth = [(r, -beta(r)) for r in radii]
    bt = beta(r_hi)
    for i in range(1, 6):
        a = -bt + 2 * bt * i / 6
        tooth.append((r_hi, a))
    tooth += [(r, +beta(r)) for r in reversed(radii)]

    pts = []
    br = beta(r_lo)
    for k in range(Z):
        off = k * PITCH
        pts += [(r * math.cos(a + off), r * math.sin(a + off)) for (r, a) in tooth]
        a0, a1 = off + br, off + PITCH - br
        for i in range(1, 5):
            a = a0 + (a1 - a0) * i / 5
            pts.append((r_lo * math.cos(a), r_lo * math.sin(a)))
    return pts


def write_dxf(path):
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    doc.layers.add("MIL_KESITI", color=1)
    doc.layers.add("REFERANS", color=8)
    doc.layers.add("YAZI", color=2)
    msp.add_lwpolyline(mil_profili(), close=True, dxfattribs={"layer": "MIL_KESITI"})
    for d in (D_ROOT, 2 * RB, M * Z, D_TIP):
        msp.add_circle((0, 0), d / 2.0,
                       dxfattribs={"layer": "REFERANS", "linetype": "DASHED"})
    msp.add_text("MIL  m=%.2f  z=%d  alpha=30  Dtip=%.2f  Dp=%.2f  Droot=%.2f  ofset=%+.2f"
                 % (M, Z, D_TIP, M * Z, D_ROOT, OFFSET),
                 height=0.7, dxfattribs={"layer": "YAZI"}).set_placement((-11, -11.5))
    doc.saveas(path)


def write_svg(path):
    p = mil_profili()
    d = "M %.4f %.4f " % (p[0][0], -p[0][1]) + \
        " ".join("L %.4f %.4f" % (x, -y) for (x, y) in p[1:]) + " Z"
    body = ['<path d="%s" fill="#eee" stroke="#000" stroke-width="0.1"/>' % d]
    for dia, col in ((D_ROOT, "#aaa"), (2 * RB, "#c00"), (M * Z, "#07a"), (D_TIP, "#aaa")):
        body.append('<circle cx="0" cy="0" r="%.4f" fill="none" stroke="%s" '
                    'stroke-width="0.06" stroke-dasharray="0.8,0.6"/>' % (dia / 2, col))
    body.append('<text x="0" y="11.5" font-size="1.4" text-anchor="middle">'
                'm=%.2f z=%d 30deg Dtip=%.2f Dp=%.2f Droot=%.2f</text>'
                % (M, Z, D_TIP, M * Z, D_ROOT))
    open(path, "w").write(
        '<svg xmlns="http://www.w3.org/2000/svg" width="26mm" height="26mm" '
        'viewBox="-13 -13 26 26">\n' + "\n".join(body) + "\n</svg>\n")


if __name__ == "__main__":
    write_dxf("mil_spline_m1_z16.dxf")
    write_svg("mil_spline_m1_z16.svg")
    print("Rp=%.4f Rb=%.4f s=%.4f  tepe dis genisligi=%.3f mm"
          % (RP, RB, S_NOM, 2 * beta(D_TIP / 2) * D_TIP / 2))
