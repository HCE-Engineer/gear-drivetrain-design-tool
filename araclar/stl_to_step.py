#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STL (ucgen mesh) -> STEP (facetli BREP, ISO-10303-21 AP214) donusturucu.

Harici kutuphane GEREKMEZ (sadece standart kutuphane). STL'de zaten sadece
duz ucgenler var (involut/silindirik egri yuzey bilgisi yok), bu yuzden STEP
ciktisinda da her ucgen ayri bir duz (PLANE) yuzey olarak yer alir. Sekil
BIREBIR aynidir, sadece "puruzsuz" degil facetlidir (yakindan bakinca ucgen
kenarlari gorunur). Komsu ucgenler ortak kose/kenarlari PAYLASIR (kaynaksiz/
"welded" topoloji) -> gecerli bir kabuk (shell)/kati (solid) olusur.

Kullanim:
    python stl_to_step.py girdi.stl [cikti.step]
"""

import sys
import os
import struct
import math
import time
import datetime


def read_binary_stl(path):
    with open(path, "rb") as f:
        header = f.read(80)
        (ntri,) = struct.unpack("<I", f.read(4))
        tris = []
        for _ in range(ntri):
            data = f.read(50)
            if len(data) < 50:
                break
            vals = struct.unpack("<12fH", data)
            v1 = vals[3:6]
            v2 = vals[6:9]
            v3 = vals[9:12]
            tris.append((v1, v2, v3))
    return header, tris


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def norm(a):
    return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])


def normalize(a):
    n = norm(a)
    if n < 1e-15:
        return (0.0, 0.0, 1.0), 0.0
    return (a[0]/n, a[1]/n, a[2]/n), n


class StepWriter:
    def __init__(self, f):
        self.f = f
        self.next_id = 1
        self._point_cache = {}   # vertex_index -> cartesian_point step-id
        self._vertex_cache = {}  # vertex_index -> vertex_point step-id

    def _new_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    def emit(self, entity_text):
        i = self._new_id()
        self.f.write(f"#{i}={entity_text};\n")
        return i

    def cartesian_point(self, xyz):
        x, y, z = xyz
        return self.emit(f"CARTESIAN_POINT('',({x:.6f},{y:.6f},{z:.6f}))")

    def direction(self, xyz):
        x, y, z = xyz
        return self.emit(f"DIRECTION('',({x:.9f},{y:.9f},{z:.9f}))")

    def vector(self, dir_id, magnitude):
        return self.emit(f"VECTOR('',#{dir_id},{magnitude:.6f})")

    def line(self, point_id, vector_id):
        return self.emit(f"LINE('',#{point_id},#{vector_id})")

    def vertex_point(self, point_id):
        return self.emit(f"VERTEX_POINT('',#{point_id})")

    def edge_curve(self, v_start_id, v_end_id, curve_id, same_sense=True):
        s = ".T." if same_sense else ".F."
        return self.emit(f"EDGE_CURVE('',#{v_start_id},#{v_end_id},#{curve_id},{s})")

    def oriented_edge(self, edge_curve_id, same_sense):
        s = ".T." if same_sense else ".F."
        return self.emit(f"ORIENTED_EDGE('',*,*,#{edge_curve_id},{s})")

    def edge_loop(self, oriented_edge_ids):
        refs = ",".join(f"#{i}" for i in oriented_edge_ids)
        return self.emit(f"EDGE_LOOP('',({refs}))")

    def face_outer_bound(self, loop_id):
        return self.emit(f"FACE_OUTER_BOUND('',#{loop_id},.T.)")

    def axis2_placement_3d(self, origin_id, axis_dir_id, ref_dir_id):
        return self.emit(f"AXIS2_PLACEMENT_3D('',#{origin_id},#{axis_dir_id},#{ref_dir_id})")

    def plane(self, placement_id):
        return self.emit(f"PLANE('',#{placement_id})")

    def advanced_face(self, bound_ids, surface_id, same_sense=True):
        refs = ",".join(f"#{i}" for i in bound_ids)
        s = ".T." if same_sense else ".F."
        return self.emit(f"ADVANCED_FACE('',({refs}),#{surface_id},{s})")

    def closed_shell(self, face_ids):
        refs = ",".join(f"#{i}" for i in face_ids)
        return self.emit(f"CLOSED_SHELL('',({refs}))")

    def open_shell(self, face_ids):
        refs = ",".join(f"#{i}" for i in face_ids)
        return self.emit(f"OPEN_SHELL('',({refs}))")

    def manifold_solid_brep(self, shell_id):
        return self.emit(f"MANIFOLD_SOLID_BREP('',#{shell_id})")

    def shell_based_surface_model(self, shell_id):
        return self.emit(f"SHELL_BASED_SURFACE_MODEL('',(#{shell_id}))")


def weld_vertices(tris, decimals=6):
    """Aynı koordinattaki köşeleri tek indekste birleştirir (topoloji için şart)."""
    index = {}
    verts = []
    itris = []
    bbox_min = [math.inf, math.inf, math.inf]
    bbox_max = [-math.inf, -math.inf, -math.inf]

    def vid(p):
        key = (round(p[0], decimals), round(p[1], decimals), round(p[2], decimals))
        i = index.get(key)
        if i is None:
            i = len(verts)
            index[key] = i
            verts.append(p)
            for k in range(3):
                bbox_min[k] = min(bbox_min[k], p[k])
                bbox_max[k] = max(bbox_max[k], p[k])
        return i

    n_degenerate = 0
    for v1, v2, v3 in tris:
        e1 = sub(v2, v1)
        e2 = sub(v3, v1)
        cr = cross(e1, e2)
        if norm(cr) < 1e-9:
            n_degenerate += 1
            continue
        i1, i2, i3 = vid(v1), vid(v2), vid(v3)
        if i1 == i2 or i2 == i3 or i1 == i3:
            n_degenerate += 1
            continue
        itris.append((i1, i2, i3))

    diag = norm(sub(tuple(bbox_max), tuple(bbox_min))) if verts else 0.0
    return verts, itris, n_degenerate, diag


def build_step(verts, itris, out_path, source_name):
    t0 = time.time()
    n_faces_total = len(itris)

    with open(out_path, "w", encoding="ascii", newline="\n") as f:
        w = StepWriter(f)

        # --- kose noktalari + vertex_point onceden uret ---
        point_ids = [None] * len(verts)
        vertex_ids = [None] * len(verts)
        for i, p in enumerate(verts):
            pid = w.cartesian_point(p)
            point_ids[i] = pid
            vertex_ids[i] = w.vertex_point(pid)
            if (i + 1) % 20000 == 0:
                print(f"  koseler: {i + 1}/{len(verts)}")

        edge_cache = {}   # (min,max) -> (edge_curve_id, canonical_(a,b))
        multi_edge_warn = 0

        face_ids = []
        for fi, (i1, i2, i3) in enumerate(itris):
            p1, p2, p3 = verts[i1], verts[i2], verts[i3]
            e1 = sub(p2, p1)
            e2 = sub(p3, p1)
            normal_raw = cross(e1, e2)
            normal_dir, _ = normalize(normal_raw)
            ref_dir, _ = normalize(e1)

            oriented_edges = []
            for a, b in ((i1, i2), (i2, i3), (i3, i1)):
                key = (a, b) if a < b else (b, a)
                cached = edge_cache.get(key)
                if cached is None:
                    pa, pb = verts[a], verts[b]
                    d = sub(pb, pa)
                    dnorm, mag = normalize(d)
                    dir_id = w.direction(dnorm)
                    vec_id = w.vector(dir_id, mag)
                    line_id = w.line(point_ids[a], vec_id)
                    ec_id = w.edge_curve(vertex_ids[a], vertex_ids[b], line_id, True)
                    edge_cache[key] = [ec_id, (a, b), 1]
                    same_sense = True
                else:
                    cached[2] += 1
                    if cached[2] > 2:
                        multi_edge_warn += 1
                    ec_id = cached[0]
                    same_sense = (a, b) == cached[1]
                oe_id = w.oriented_edge(ec_id, same_sense)
                oriented_edges.append(oe_id)

            loop_id = w.edge_loop(oriented_edges)
            bound_id = w.face_outer_bound(loop_id)
            axis_id = w.direction(normal_dir)
            ref_id = w.direction(ref_dir)
            placement_id = w.axis2_placement_3d(point_ids[i1], axis_id, ref_id)
            plane_id = w.plane(placement_id)
            af_id = w.advanced_face([bound_id], plane_id, True)
            face_ids.append(af_id)

            if (fi + 1) % 5000 == 0:
                print(f"  yuzler: {fi + 1}/{n_faces_total}  ({time.time() - t0:.1f} s)")

        # --- kapali mi kontrol et (her kenar tam 2 kez kullanilmis mi) ---
        boundary_edges = sum(1 for v in edge_cache.values() if v[2] == 1)
        non_manifold_edges = sum(1 for v in edge_cache.values() if v[2] > 2)
        is_closed = (boundary_edges == 0 and non_manifold_edges == 0)

        if is_closed:
            shell_id = w.closed_shell(face_ids)
            solid_id = w.manifold_solid_brep(shell_id)
            shape_item_id = solid_id
            rep_kind = "MANIFOLD_SOLID_BREP (kapali kati)"
        else:
            shell_id = w.open_shell(face_ids)
            solid_id = w.shell_based_surface_model(shell_id)
            shape_item_id = solid_id
            rep_kind = f"SHELL_BASED_SURFACE_MODEL (acik kabuk -> {boundary_edges} sinir kenari, {non_manifold_edges} non-manifold kenar)"

        # --- STEP AP214 sarmalama (context/units/product boilerplate) ---
        len_unit_id = w.emit("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
        ang_unit_id = w.emit("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
        solid_ang_unit_id = w.emit("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
        unc_val_id = w.emit(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-06),#{len_unit_id},'DISTANCE_ACCURACY_VALUE','Confusion accuracy')")
        geom_ctx_id = w.emit(
            f"(GEOMETRIC_REPRESENTATION_CONTEXT(3) "
            f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{unc_val_id})) "
            f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{len_unit_id},#{ang_unit_id},#{solid_ang_unit_id})) "
            f"REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY'))"
        )

        app_ctx_id = w.emit("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
        app_proto_id = w.emit(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#{app_ctx_id})")
        prod_ctx_id = w.emit(f"PRODUCT_CONTEXT('',#{app_ctx_id},'mechanical')")
        prod_name = source_name.replace("'", "")
        product_id = w.emit(f"PRODUCT('{prod_name}','{prod_name}','',(#{prod_ctx_id}))")
        pd_ctx_id = w.emit(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{app_ctx_id},'design')")
        pdf_id = w.emit(f"PRODUCT_DEFINITION_FORMATION('','',#{product_id})")
        pd_id = w.emit(f"PRODUCT_DEFINITION('design','',#{pdf_id},#{pd_ctx_id})")
        pds_id = w.emit(f"PRODUCT_DEFINITION_SHAPE('','',#{pd_id})")

        shape_rep_id = w.emit(f"SHAPE_REPRESENTATION('',(#{shape_item_id}),#{geom_ctx_id})")
        w.emit(f"SHAPE_DEFINITION_REPRESENTATION(#{pds_id},#{shape_rep_id})")

    return dict(
        n_verts=len(verts),
        n_faces=n_faces_total,
        n_edges=len(edge_cache),
        boundary_edges=boundary_edges,
        non_manifold_edges=non_manifold_edges,
        is_closed=is_closed,
        rep_kind=rep_kind,
        n_entities=w.next_id - 1,
        elapsed=time.time() - t0,
    )


def write_with_header(final_path, body_path, source_name):
    """Once govde uretilir (entity id sayisini bilmek icin), sonra HEADER + DATA
    birlestirilip son dosyaya yazilir (STEP dosyasinda HEADER govdeden once gelmeli
    ama govde uretilirken toplam id sayisi onceden bilinmiyor -> iki asamali yaziyoruz)."""
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    header = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        f"FILE_DESCRIPTION((''),'2;1');\n"
        f"FILE_NAME('{source_name}','{now}',('reduktor-proje'),(''),"
        f"'stl_to_step.py (pure python)','',''); \n"
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\n"
        "ENDSEC;\n"
        "DATA;\n"
    )
    footer = "ENDSEC;\nEND-ISO-10303-21;\n"
    with open(final_path, "w", encoding="ascii", newline="\n") as out:
        out.write(header)
        with open(body_path, "r", encoding="ascii") as body:
            for line in body:
                out.write(line)
        out.write(footer)


def main():
    if len(sys.argv) < 2:
        print("Kullanim: python stl_to_step.py girdi.stl [cikti.step]")
        sys.exit(1)
    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(in_path)[0] + ".step"
    tmp_path = out_path + ".body.tmp"

    print(f"Okunuyor: {in_path}")
    header, tris = read_binary_stl(in_path)
    print(f"Baslik: {header[:60]!r}")
    print(f"Ucgen sayisi (ham): {len(tris)}")

    verts, itris, n_degenerate, diag = weld_vertices(tris)
    print(f"Kaynastirma (weld) sonrasi: {len(verts)} benzersiz kose, "
          f"{len(itris)} gecerli ucgen, {n_degenerate} dejenere/atlandi.")

    stats = build_step(verts, itris, tmp_path, os.path.basename(in_path))
    write_with_header(out_path, tmp_path, os.path.basename(in_path))
    os.remove(tmp_path)

    size = os.path.getsize(out_path)
    print("-" * 60)
    print(f"Sonuc turu     : {stats['rep_kind']}")
    print(f"Kose / Kenar / Yuz : {stats['n_verts']} / {stats['n_edges']} / {stats['n_faces']}")
    print(f"Toplam STEP entity : {stats['n_entities']}")
    print(f"Sure           : {stats['elapsed']:.1f} s")
    print(f"Cikti          : {out_path}  ({size/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
