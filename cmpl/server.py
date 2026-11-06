"""Petit serveur local : l'interface s'ouvre dans le navigateur, tout reste sur l'ordinateur."""
import base64
import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageOps

from . import assets, batch, colors, defaults, flat, layout, library, render_pdf, render_pptx, render_png, updater, version, errlog, report

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ID = "cmpl-couvertures"
PORT = 8765
TOKEN = secrets.token_urlsafe(16)

IMAGES = {}        # id -> PIL.Image (images importées)
RAW = {}           # id -> (bytes, extension) pour l'enregistrement des fiches
_state = {"seen": False, "bye_at": None}


# ------------------------------------------------------------------ réglages

def app_dir():
    override = os.environ.get("CMPL_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "CMPL-Couvertures")
    os.makedirs(d, exist_ok=True)
    return d


def settings_path():
    return os.path.join(app_dir(), "reglages.json")


SETTING_KEYS = ("custom_colors", "custom_collections", "out_dir", "update_popup", "theme", "support_email",
                "support_whatsapp")


def load_settings():
    try:
        with open(settings_path(), encoding="utf8") as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    data.setdefault("custom_colors", [])
    data.setdefault("custom_collections", [])
    data.setdefault("update_popup", True)
    data.setdefault("theme", "light")
    data.setdefault("support_email", "")
    data.setdefault("support_whatsapp", "")
    data.setdefault("out_dir", os.path.join(os.path.expanduser("~"), "Documents", "Couvertures CMPL"))
    return data


def save_settings(data):
    keep = {k: data.get(k) for k in SETTING_KEYS}
    with open(settings_path(), "w", encoding="utf8") as fh:
        json.dump(keep, fh, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ images

def register_image(data: bytes, ext="png", image_id=None):
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("CMYK", "I;16", "I", "F"):
        im = im.convert("RGB")
    elif im.mode == "P":
        im = im.convert("RGBA" if "transparency" in im.info else "RGB")
    elif im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    if max(im.size) > 4000:
        k = 4000 / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    iid = image_id or uuid.uuid4().hex[:8]
    IMAGES[iid] = im
    RAW[iid] = (data, ext)
    return iid, im


def load_builtin_images():
    path = os.path.join(assets.ASSETS, "exemple_aigle.png")
    with open(path, "rb") as fh:
        register_image(fh.read(), "png", "ex-aigle")


# ------------------------------------------------------------------ rendu

contrast_ratio = colors.contrast


def warnings_for(p, notes=None):
    """Liste de {level, text} : info (gris), warn (orange), error (rouge)."""
    w = []
    if not (p.get("titre") or "").strip():
        w.append({"level": "warn", "text": "Le titre est vide."})
    if p["type"] == "A":
        status, msg = assets.isbn_status(p.get("isbn"))
        if status == "invalide":
            w.append({"level": "warn", "text": "ISBN : " + msg})
        elif status == "vide":
            w.append({"level": "info", "text": "Pas d'ISBN : la 4e de couverture n'aura pas de code-barres."})
        if contrast_ratio("#FFFFFF", p["color"]) < 3.0:
            w.append({"level": "warn",
                      "text": "Ce fond est clair : le texte blanc sera difficile à lire (la charte demande du blanc)."})
    else:
        if not p.get("illustration") or p.get("illustration") not in IMAGES:
            w.append({"level": "warn", "text": "Pas d'illustration : ajoute une image dans la section « Images »."})
    for level, text in (notes.items if notes else []):
        w.append({"level": level, "text": text})
    order = {"error": 0, "warn": 1, "info": 2}
    w.sort(key=lambda x: order.get(x["level"], 3))
    return w


def build(params):
    p = defaults.normalize(params)
    pages = layout.build_pages(p, IMAGES)
    return p, pages, layout.last_notes()


def _png_b64(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def preview(params, dpi=100, bleed=0.0, only_front=False, only=None):
    p, pages, notes = build(params)
    if only_front:
        only = 0
    faces = []
    for i, pg in enumerate(pages):
        if only is not None and i != only:
            continue
        img = render_png.render_page(pg, dpi=dpi)
        faces.append({"name": pg.name, "w": img.width, "h": img.height, "png": _png_b64(img)})
    hot = notes.hot.get("ill")
    texts = notes.hot.get("texts", [])
    if only is not None:
        return {"faces": faces, "warnings": warnings_for(p, notes), "hot": hot, "texts": texts, "partial": True}
    # couverture à plat (avec repères de coupe et de pli, uniquement dans l'aperçu)
    bleed = max(0.0, min(10.0, float(bleed)))
    fpage, info = flat.compose(pages, bleed=bleed)
    fdpi = max(40, int(dpi * 0.7))
    fimg = render_png.render_page(fpage, dpi=fdpi)
    from PIL import ImageDraw
    d = ImageDraw.Draw(fimg)
    k = fdpi / 25.4
    tx, ty, tw, th = info["trim"]
    d.rectangle([tx * k, ty * k, (tx + tw) * k, (ty + th) * k], outline=(0, 170, 255), width=1)
    for fx in info["folds"]:
        d.line([fx * k, 0, fx * k, fimg.height], fill=(255, 0, 170), width=1)
    faces.append({"name": ("À plat" if not bleed else f"À plat · fonds perdus {bleed:g} mm"), "w": fimg.width, "h": fimg.height,
                  "png": _png_b64(fimg)})
    return {"faces": faces, "warnings": warnings_for(p, notes), "hot": hot, "texts": texts}


def thumb_of(pages, dpi=40):
    return "data:image/png;base64," + _png_b64(render_png.render_page(pages[0], dpi=dpi))


def safe_name(text):
    text = unicodedata.normalize("NFC", text or "").replace("\n", " ").strip()
    text = re.sub(r'[\\/:*?"<>|]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:80] or "Couverture"


def generate(params, out_dir, name, want_png=True, want_pptx=True, dpi=300, want_pdf=False, bleed=0.0,
             marks=False):
    p, pages, _notes = build(params)
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    base = safe_name(name or p.get("titre") or p.get("auteur"))
    files = []
    labels = ["1re de couverture", "4e de couverture", "dos"]
    if want_png:
        for pg, label in zip(pages, labels):
            img = render_png.render_page(pg, dpi=dpi)
            path = os.path.join(out_dir, f"{base} - {label}.png")
            img.save(path, dpi=(dpi, dpi))
            files.append(path)
    if want_pptx:
        path = os.path.join(out_dir, f"{base}.pptx")
        render_pptx.build_pptx(pages, path, title=base)
        files.append(path)
    if want_pdf:
        fdpi = min(int(dpi), 300)
        bleed = max(0.0, min(10.0, float(bleed)))
        fpage, info = flat.compose(pages, bleed=bleed, marks=marks)
        fimg = render_png.render_page(fpage, dpi=fdpi)
        path = os.path.join(out_dir, f"{base} - couverture a plat.pdf")
        sx, sy, sw, sh = info["sheet"]
        render_pdf.write_pdf(fimg, path, fdpi, trim_mm=info["trim"], bleed_mm=(sx, sy, sw, sh), title=base)
        files.append(path)
    return files


# ------------------------------------------------------------------ lot (Excel)

JOBS = {}
_job_lock = threading.Lock()


def _drop_job_images(job):
    for iid in job.get("_imgs", []):
        IMAGES.pop(iid, None)
        RAW.pop(iid, None)
    job["_imgs"] = []


def _image_dirs(base_dir, img_dir):
    dirs = []
    for d in (img_dir, base_dir,
              base_dir and os.path.join(base_dir, "illustrations"),
              base_dir and os.path.join(base_dir, "Illustrations"),
              base_dir and os.path.join(base_dir, "images"),
              base_dir and os.path.join(base_dir, "Images")):
        if d and d not in dirs and os.path.isdir(d):
            dirs.append(d)
    return dirs


def _analyze(job_id, data, filename, base_dir, img_dir):
    """Lit le fichier, vérifie chaque ligne et prépare un aperçu (miniature) par livre."""
    job = JOBS[job_id]
    try:
        rows = batch.read_rows(data, filename)
    except Exception as e:
        job.update(finished=True, error=f"Fichier illisible : {e}")
        return
    if not rows:
        job.update(finished=True, error="Aucun livre trouvé : remplis au moins le titre d'une ligne "
                                        "(à partir de la ligne 3 du modèle).")
        return
    job["total"] = len(rows)
    settings = load_settings()
    dirs = _image_dirs(base_dir, img_dir)

    def loader(ref):
        path = ref if os.path.isabs(ref) else None
        if path is None:
            for d in dirs:
                cand = os.path.join(d, ref)
                if os.path.isfile(cand):
                    path = cand
                    break
        if not path or not os.path.isfile(path):
            where = ("dans le dossier du fichier Excel ou dans le dossier des illustrations choisi" if base_dir
                     else "dans le dossier des illustrations (à choisir)")
            raise ValueError(f"image introuvable : « {ref} » (elle doit être {where})")
        with open(path, "rb") as fh:
            iid, _ = register_image(fh.read(), os.path.splitext(path)[1].lstrip(".") or "png")
        job["_imgs"].append(iid)
        return iid

    for n, (line, d) in enumerate(rows, 1):
        label = (d.get("titre") or d.get("auteurs") or f"ligne {line}").replace("\n", " ")
        job["current"] = label
        entry = {"line": line, "ok": False, "titre": label, "auteurs": (d.get("auteurs") or "").replace("\n", " · ")}
        try:
            p = batch.row_to_params(d, settings.get("custom_colors"), loader)
            p, pages, notes = build(p)
            wl = warnings_for(p, notes)
            kind = p["type"]
            ign = batch.ignored_columns(kind, d)
            if ign:
                wl.append({"level": "info", "text": "Colonnes sans effet pour ce modèle : " + ", ".join(ign) + "."})
            entry.update(ok=True, type=kind, format=p["format"], color=p["color"], spine=p["spine_mm"],
                         name=safe_name(d.get("name") or p.get("titre") or p.get("auteur")),
                         warn=wl, thumb=thumb_of(pages, 30))
            job["_params"][line] = p
        except Exception as e:
            errlog.record(f"lot Excel, analyse ligne {line}", e)
            entry.update(error=str(e), type="", format="", color="", spine=None, name="", warn=[], thumb=None)
        job["rows"].append(entry)
        job["done"] = n
    job["current"] = ""
    job["finished"] = True


def start_analysis(data, filename, base_dir="", img_dir=""):
    with _job_lock:
        for old in JOBS.values():
            _drop_job_images(old)
        JOBS.clear()
        jid = uuid.uuid4().hex[:8]
        JOBS[jid] = {"done": 0, "total": 0, "current": "", "rows": [], "finished": False, "error": None,
                     "file": filename, "base_dir": base_dir, "_params": {}, "_imgs": [],
                     "run_done": 0, "run_total": 0, "run_current": "", "run_results": [], "run_finished": False,
                     "running": False}
    threading.Thread(target=_analyze, args=(jid, data, filename, base_dir, img_dir), daemon=True).start()
    return jid


def plan_folders(job, out_dir, lines=None):
    """Nom du sous-dossier de chaque livre (un dossier par livre, doublons numérotés) + déjà présent ?"""
    out_root = os.path.abspath(os.path.expanduser(out_dir))
    used, plan = {}, {}
    for r in job["rows"]:
        if not r["ok"] or (lines is not None and r["line"] not in lines):
            continue
        base = r["name"]
        used[base] = used.get(base, 0) + 1
        folder = base if used[base] == 1 else f"{base} ({used[base]})"
        full = os.path.join(out_root, folder)
        exists = os.path.isdir(full) and bool(os.listdir(full))
        plan[r["line"]] = {"folder": folder, "path": full, "exists": exists}
    return plan


def public_job(job, since=0, since_run=0):
    out = {k: v for k, v in job.items() if not k.startswith("_") and k not in ("rows", "run_results")}
    out["rows"] = job["rows"][since:]
    out["n_rows"] = len(job["rows"])
    out["run_results"] = job["run_results"][since_run:]
    out["n_run_results"] = len(job["run_results"])
    return out


def _run_batch(job_id, lines, opts):
    job = JOBS[job_id]
    out_root = os.path.abspath(os.path.expanduser(opts["out_dir"]))
    plan = plan_folders(job, out_root, set(lines))
    rows = {r["line"]: r for r in job["rows"]}
    job.update(run_total=len(plan), run_done=0, run_results=[], run_finished=False, running=True)
    for n, (line, info) in enumerate(plan.items(), 1):
        r = rows[line]
        job["run_current"] = r["titre"]
        try:
            files = generate(job["_params"][line], info["path"], r["name"], opts.get("png", True),
                             opts.get("pptx", True), int(opts.get("dpi", 300)), opts.get("pdf", False),
                             opts.get("bleed", 0), opts.get("marks", False))
            job["run_results"].append({"line": line, "name": r["name"], "ok": True, "files": len(files),
                                       "folder": info["folder"], "path": info["path"]})
        except Exception as e:
            errlog.record(f"lot Excel, création ligne {line}", e)
            job["run_results"].append({"line": line, "name": r["titre"], "ok": False, "error": str(e)})
        job["run_done"] = n
    job.update(run_current="", run_finished=True, running=False)


# ------------------------------------------------------------------ fiches

def export_fiche(params):
    p = defaults.normalize(params)
    imgs = {}
    for key in ("illustration", "logo_rond"):
        iid = p.get(key)
        if iid in RAW and iid != "ex-aigle":
            data, ext = RAW[iid]
            imgs[iid] = {"ext": ext, "data": base64.b64encode(data).decode("ascii")}
    return {"cmpl_fiche": 1, "params": p, "images": imgs}


def import_fiche(doc):
    p = dict(doc.get("params", {}))
    remap = {}
    for old, info in (doc.get("images") or {}).items():
        try:
            new, _ = register_image(base64.b64decode(info["data"]), info.get("ext", "png"))
            remap[old] = new
        except Exception:
            pass
    for key in ("illustration", "logo_rond"):
        if p.get(key) in remap:
            p[key] = remap[p[key]]
    return defaults.normalize(p)


# ------------------------------------------------------------------ dossier

def browse_folder(initial):
    initial = initial if initial and os.path.isdir(initial) else os.path.expanduser("~")
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(initialdir=initial, title="Choisir le dossier de sortie", parent=root)
        root.destroy()
        return path or ""
    except Exception:
        pass
    if sys.platform.startswith("win"):
        ps = ("Add-Type -AssemblyName System.Windows.Forms; "
              "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
              "$f.Description = 'Choisir le dossier de sortie'; "
              f"$f.SelectedPath = '{initial}'; "
              "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 creationflags=0x08000000, timeout=300)
            return out.stdout.strip()
        except Exception:
            return ""
    return ""


def open_folder(path):
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def browse_file(initial, title="Choisir un fichier"):
    """Fenêtre « Ouvrir » (Excel/CSV). Retourne le chemin, '' si annulé, None si indisponible."""
    initial = initial if initial and os.path.isdir(initial) else os.path.expanduser("~")
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            initialdir=initial, title=title, parent=root,
            filetypes=[("Tableaux Excel ou CSV", "*.xlsx *.csv"), ("Tous les fichiers", "*.*")])
        root.destroy()
        return path or ""
    except Exception:
        pass
    if sys.platform.startswith("win"):
        ps = ("Add-Type -AssemblyName System.Windows.Forms; "
              "$f = New-Object System.Windows.Forms.OpenFileDialog; "
              f"$f.Title = '{title}'; $f.InitialDirectory = '{initial}'; "
              "$f.Filter = 'Tableaux Excel ou CSV (*.xlsx;*.csv)|*.xlsx;*.csv|Tous les fichiers (*.*)|*.*'; "
              "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 creationflags=0x08000000, timeout=600)
            return out.stdout.strip()
        except Exception:
            return None
    return None


def open_file(path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def save_template(out_dir):
    """Crée le modèle Excel dans « <dossier de sortie>/Lot Excel » (sans jamais écraser un fichier existant)."""
    folder = os.path.join(os.path.abspath(os.path.expanduser(out_dir)), "Lot Excel")
    os.makedirs(folder, exist_ok=True)
    for i in range(1, 100):
        name = "Modele-couvertures-CMPL.xlsx" if i == 1 else f"Modele-couvertures-CMPL ({i}).xlsx"
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            batch.make_template(path)
            return path
    raise RuntimeError("trop de modèles dans le dossier « Lot Excel »")


# ------------------------------------------------------------------ bibliothèque / brouillon

def lib_save(params, item_id=None):
    doc = export_fiche(params)
    _p, pages, _n = build(doc["params"])
    return library.save(app_dir(), doc, thumb_of(pages, 40), item_id)


def draft_meaningful(p):
    base = defaults.EXAMPLE_A if p.get("type") != "B" else defaults.EXAMPLE_B
    if not any((p.get(k) or "").strip() for k in ("titre", "auteurs", "auteur")):
        return False
    return any((p.get(k) or "") != (base.get(k) or "") for k in ("titre", "auteurs", "auteur", "texte_4e"))


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "CMPL/1.0"

    def log_message(self, *a):  # silence
        pass

    # -- utilitaires
    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _token_ok(self):
        if self.headers.get("X-Token") == TOKEN:
            return True
        return ("t=" + TOKEN) in (self.path.split("?", 1)[1] if "?" in self.path else "")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf8")
        elif isinstance(body, str):
            body = body.encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # -- GET
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "host"})
        path = self.path.split("?", 1)[0]
        _state["bye_at"] = None
        if path == "/":
            with open(os.path.join(HERE, "web", "index.html"), encoding="utf8") as fh:
                html = fh.read().replace("__TOKEN__", TOKEN)
            return self._send(200, html, "text/html; charset=utf-8")
        if path in ("/favicon.png", "/favicon.ico"):
            with open(os.path.join(HERE, "web", "favicon.png"), "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/batch/template":
            if not self._token_ok():
                return self._send(403, {"error": "forbidden"})
            try:
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    fp = os.path.join(tmp, "m.xlsx")
                    batch.make_template(fp)
                    with open(fp, "rb") as fh:
                        data = fh.read()
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="Modele-couvertures-CMPL.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/ping":
            _state["seen"] = True
            _state["bye_at"] = None
            return self._send(200, {"app": APP_ID})
        return self._send(404, {"error": "not found"})

    # -- POST
    def do_POST(self):
        if not self._host_ok() or not self._token_ok():
            return self._send(403, {"error": "forbidden"})
        path = self.path.split("?", 1)[0]
        if path != "/api/bye":
            _state["bye_at"] = None
        try:
            if path == "/api/bye":
                _state["bye_at"] = time.time()
                return self._send(200, {})
            if path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
                return
            if path == "/api/update/status":
                return self._send(200, updater.status())
            if path == "/api/update/check":
                if updater.STATE["state"] not in ("downloading", "ready", "checking"):
                    updater.start_check(0.0, silent=False)
                return self._send(200, updater.status())
            if path == "/api/update/start":
                updater.start_download()
                return self._send(200, updater.status())
            if path == "/api/update/cancel":
                updater.cancel()
                return self._send(200, updater.status())
            if path == "/api/update/apply":
                try:
                    updater.apply()
                except Exception as e:
                    updater._set(state="error", error=f"Installation impossible : {e}")
                    return self._send(200, updater.status())
                self._send(200, updater.status())
                threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
                return
            if path == "/api/batch/analyze_upload":
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n)
                from urllib.parse import unquote
                fname = unquote(self.headers.get("X-Filename", "livres.xlsx"))
                img_dir = unquote(self.headers.get("X-Img-Dir", ""))
                return self._send(200, {"job": start_analysis(data, fname, "", img_dir)})
            if path == "/api/upload":
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n)
                ext = os.path.splitext(self.headers.get("X-Filename", "x.png"))[1].lstrip(".").lower() or "png"
                iid, im = register_image(data, ext)
                th = im.copy()
                th.thumbnail((160, 160))
                buf = io.BytesIO()
                th.convert("RGBA" if th.mode == "RGBA" else "RGB").save(buf, "PNG")
                return self._send(200, {"id": iid, "w": im.width, "h": im.height,
                                        "thumb": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()})
            body = self._json()
            if path == "/api/preview":
                return self._send(200, preview(body["params"], int(body.get("dpi", 100)), body.get("bleed", 0),
                                               bool(body.get("only_front")), body.get("only")))
            if path == "/api/generate":
                p0 = defaults.normalize(body["params"])
                base = safe_name(body.get("name") or p0.get("titre") or p0.get("auteur"))
                folder = os.path.join(os.path.abspath(os.path.expanduser(body["out_dir"])), base)   # un dossier par livre
                files = generate(body["params"], folder, base, body.get("png", True),
                                 body.get("pptx", True), int(body.get("dpi", 300)), body.get("pdf", False),
                                 body.get("bleed", 0), body.get("marks", False))
                s = load_settings()
                s["out_dir"] = body["out_dir"]
                save_settings(s)
                return self._send(200, {"files": files, "folder": folder,
                                        "pptx": next((f for f in files if f.endswith(".pptx")), None)})
            if path == "/api/open_file":
                fp = os.path.abspath(body.get("path", ""))
                if os.path.splitext(fp)[1].lower() not in (".pptx", ".pdf", ".png", ".xlsx") or not os.path.isfile(fp):
                    return self._send(400, {"error": "fichier introuvable"})
                return self._send(200, {"opened": open_file(fp)})
            if path == "/api/batch/template_save":
                out_dir = body.get("out_dir") or load_settings()["out_dir"]
                tpl = save_template(out_dir)
                return self._send(200, {"path": tpl, "folder": os.path.dirname(tpl), "opened": open_file(tpl)})
            if path == "/api/batch/pick_file":
                return self._send(200, {"path": browse_file(body.get("initial"), "Choisir le fichier Excel rempli")})
            if path == "/api/batch/analyze_path":
                fp = os.path.abspath(os.path.expanduser(body.get("path", "")))
                if not os.path.isfile(fp):
                    return self._send(400, {"error": f"Fichier introuvable : {fp}"})
                try:
                    with open(fp, "rb") as fh:
                        data = fh.read()
                except PermissionError:
                    return self._send(400, {"error": "Impossible de lire le fichier (est-il bien fermé dans Excel ?)."})
                jid = start_analysis(data, os.path.basename(fp), os.path.dirname(fp), body.get("img_dir", ""))
                return self._send(200, {"job": jid, "file": os.path.basename(fp), "folder": os.path.dirname(fp)})
            if path == "/api/batch/status":
                job = JOBS.get(body.get("job"))
                if not job:
                    return self._send(404, {"error": "tâche inconnue"})
                return self._send(200, public_job(job, int(body.get("since", 0)), int(body.get("since_run", 0))))
            if path == "/api/batch/folders":
                job = JOBS.get(body.get("job"))
                if not job:
                    return self._send(404, {"error": "tâche inconnue"})
                return self._send(200, {"plan": {str(k): v for k, v in plan_folders(job, body["out_dir"]).items()}})
            if path == "/api/batch/row_preview":
                job = JOBS.get(body.get("job"))
                p = job and job["_params"].get(int(body.get("line", 0)))
                if not p:
                    return self._send(404, {"error": "livre inconnu"})
                return self._send(200, preview(p, 100, body.get("bleed", 0)))
            if path == "/api/batch/run":
                job = JOBS.get(body.get("job"))
                if not job or not job["finished"]:
                    return self._send(400, {"error": "L'analyse n'est pas terminée."})
                if job.get("running"):
                    return self._send(400, {"error": "Une création est déjà en cours."})
                opts = body.get("opts", {})
                s = load_settings()
                s["out_dir"] = opts.get("out_dir", s["out_dir"])
                save_settings(s)
                job["running"] = True
                threading.Thread(target=_run_batch, args=(body["job"], [int(x) for x in body.get("lines", [])], opts),
                                 daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/lib/list":
                return self._send(200, {"items": library.listing(app_dir())})
            if path == "/api/lib/save":
                return self._send(200, {"id": lib_save(body["params"], body.get("id"))})
            if path == "/api/lib/load":
                return self._send(200, {"params": import_fiche(library.load(app_dir(), body.get("id")))})
            if path == "/api/lib/export":
                return self._send(200, library.load(app_dir(), body.get("id")))
            if path == "/api/lib/delete":
                library.delete(app_dir(), body.get("id"))
                return self._send(200, {"ok": True})
            if path == "/api/draft/save":
                library.draft_save(app_dir(), export_fiche(body["params"]))
                return self._send(200, {"ok": True})
            if path == "/api/draft/load":
                doc = library.draft_load(app_dir())
                if not doc:
                    return self._send(200, {"params": None})
                p = import_fiche(doc)
                return self._send(200, {"params": p if draft_meaningful(p) else None})
            if path == "/api/settings":
                s = load_settings()
                s.update({k: body[k] for k in SETTING_KEYS if k in body})
                save_settings(s)
                return self._send(200, {"ok": True})
            if path == "/api/browse":
                return self._send(200, {"path": browse_folder(body.get("initial"))})
            if path == "/api/open_folder":
                return self._send(200, {"ok": open_folder(body.get("path", ""))})
            if path == "/api/report/text":
                return self._send(200, {"text": report.error_text(body.get("error", ""), body.get("client"))})
            if path == "/api/report/create":
                out_dir = body.get("out_dir") or load_settings()["out_dir"]
                try:
                    fiche = export_fiche(body["params"]) if body.get("params") else None
                except Exception as e:
                    errlog.record("export de la fiche pour le rapport", e)
                    fiche = None
                return self._send(200, report.build(out_dir, fiche, body.get("description", ""), body.get("error", ""),
                                                    body.get("client")))
            if path == "/api/report/share":
                out_dir = body.get("out_dir") or load_settings()["out_dir"]
                if not report.valid_report_path(body.get("path"), out_dir):
                    return self._send(400, {"error": "rapport introuvable"})
                return self._send(200, report.share(body["path"], body.get("how"), body.get("to", ""),
                                                    body.get("number", ""), body.get("description", ""),
                                                    body.get("error", "")))
            if path == "/api/fiche/export":
                return self._send(200, export_fiche(body["params"]))
            if path == "/api/fiche/import":
                return self._send(200, {"params": import_fiche(body)})
            if path == "/api/thumb":
                im = IMAGES.get(body.get("id"))
                if im is None:
                    return self._send(404, {"error": "image"})
                th = im.copy()
                th.thumbnail((160, 160))
                buf = io.BytesIO()
                th.convert("RGBA" if th.mode == "RGBA" else "RGB").save(buf, "PNG")
                return self._send(200, {"thumb": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()})
        except Exception as e:  # message lisible dans l'interface
            errlog.record(path, e)
            import traceback
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": "not found"})


def bootstrap_payload():
    s = load_settings()
    return {
        "palettes": defaults.PALETTES, "collections": defaults.COLLECTIONS,
        "formats": {k: {"w": v[0], "h": v[1], "label": v[2]} for k, v in layout.FORMATS.items()},
        "settings": s, "version": version.VERSION,
        "examples": {"A": defaults.EXAMPLE_A, "B": defaults.EXAMPLE_B},
        "blanks": {"A": defaults.BLANK_A, "B": defaults.BLANK_B},
    }


_orig_get = Handler.do_GET


def _do_get(self):
    if self.path.split("?", 1)[0] == "/api/bootstrap":
        if not self._host_ok() or not self._token_ok():
            return self._send(403, {"error": "forbidden"})
        return self._send(200, bootstrap_payload())
    return _orig_get(self)


Handler.do_GET = _do_get


def _watchdog(server):
    while True:
        time.sleep(1.0)
        t = _state.get("bye_at")
        if t and time.time() - t > 8:
            os._exit(0)


def already_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=1.5) as r:
            return json.loads(r.read().decode()).get("app") == APP_ID
    except Exception:
        return False


def main(open_browser=True, relance=False):
    import webbrowser
    if relance:                                   # on attend que l'ancienne version ait libéré le port
        for _ in range(60):
            if not already_running():
                break
            time.sleep(0.25)
    if already_running():
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return
    load_builtin_images()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=_watchdog, args=(server,), daemon=True).start()
    errlog.install_thread_hook()
    updater.cleanup_old()
    updater.start_check(delay=2.5)
    url = f"http://127.0.0.1:{port}/"
    if sys.stdout:
        print(f"Générateur de couvertures CMPL : {url}\nFerme l'onglet (ou clique sur « Quitter ») pour arrêter.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
