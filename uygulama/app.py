# -*- coding: utf-8 -*-
"""
Çark Oluşturucu — web arayüzü sunucusu.

    python app.py            -> http://127.0.0.1:5050 (tarayıcıyı açar)
    python app.py --no-browser
"""

import base64
import hashlib
import json
import sys
import threading
import time
import traceback
import webbrowser
from collections import OrderedDict

from flask import Flask, jsonify, request, send_from_directory, Response

import motor

app = Flask(__name__, static_folder="static", static_url_path="/static")

_CACHE: "OrderedDict[str, motor.Sonuc]" = OrderedDict()
_CACHE_MAX = 12
_LOCK = threading.Lock()          # OCC çekirdeği tek iş parçacığıyla çalışsın


def _b64(arr):
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _key(kind, params):
    raw = json.dumps([kind, params], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if hasattr(o, "item"):
        return o.item()
    return o


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/meta")
def meta():
    return jsonify(materials=list(motor.rd.MATERIALS.keys()),
                   k0=motor.rd.K0_TABLE)


@app.post("/api/build")
def build():
    body = request.get_json(force=True, silent=True) or {}
    kind = body.get("kind", "duz")
    params = body.get("params", {})
    key = _key(kind, params)
    t0 = time.time()
    try:
        with _LOCK:
            if key in _CACHE:
                res = _CACHE[key]
                _CACHE.move_to_end(key)
            else:
                res = motor.build(kind, params)
                _CACHE[key] = res
                while len(_CACHE) > _CACHE_MAX:
                    _CACHE.popitem(last=False)
            parts = []
            for p in res.parts:
                tol = motor._tol_for(p.shape)
                v, t = motor.tessellate(p.shape, tol, 0.25)
                parts.append(dict(name=p.name, color=p.color, info=_jsonable(p.info),
                                  anim=_jsonable(p.anim), pos=_b64(v), idx=_b64(t),
                                  dxf=p.dxf_wire is not None))
    except motor.GirdiHatasi as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Geometri oluşturulamadı: {e}"), 500
    return jsonify(id=key, parts=parts, summary=_jsonable(res.summary),
                   warnings=res.warnings, report=res.report, anim_mode=res.anim_mode,
                   ms=int((time.time() - t0) * 1000))


@app.get("/api/export/<key>")
def export(key):
    fmt = request.args.get("fmt", "stl").lower()
    if fmt not in ("stl", "step", "dxf", "3mf"):
        return jsonify(error="format geçersiz"), 400
    part = request.args.get("part", "all")
    res = _CACHE.get(key)
    if res is None:
        return jsonify(error="Model önbellekte yok, yeniden oluşturun"), 404
    try:
        idx = None if part == "all" else int(part)
        if idx is not None and not 0 <= idx < len(res.parts):
            return jsonify(error="parça yok"), 400
        with _LOCK:
            name, data, mime = motor.export_file(res, fmt, idx)
    except motor.GirdiHatasi as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Dışa aktarma hatası: {e}"), 500
    return Response(data, mimetype=mime, headers={
        "Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/report/<key>")
def report(key):
    res = _CACHE.get(key)
    if res is None or not res.report:
        return jsonify(error="rapor yok"), 404
    return Response(res.report.encode("utf-8"), mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="reduktor_rapor.txt"'})


@app.post("/api/search")
def search():
    body = request.get_json(force=True, silent=True) or {}
    try:
        out = motor.reducer_search(body.get("params", {}))
    except motor.GirdiHatasi as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Arama hatası: {e}"), 500
    return jsonify(_jsonable(out))


@app.post("/api/sweep")
def sweep():
    body = request.get_json(force=True, silent=True) or {}
    try:
        with _LOCK:
            out = motor.sweep_analysis(body.get("params", {}), int(body.get("stage", 0)),
                                       body.get("param", "x1"))
    except motor.GirdiHatasi as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Tarama hatası: {e}"), 500
    return jsonify(_jsonable(out))


def main():
    port = 5050
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print(f"Çark Oluşturucu çalışıyor: http://127.0.0.1:{port}  (kapatmak için Ctrl+C)")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
