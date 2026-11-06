"""Bibliothèque de couvertures enregistrées + brouillon automatique (dans le dossier de réglages)."""
import json
import os
import re
import time
import uuid


def data_dir(base):
    d = os.path.join(base, "bibliotheque")
    os.makedirs(d, exist_ok=True)
    return d


def _valid_id(item_id):
    return bool(item_id) and re.fullmatch(r"[0-9a-f]{8,32}", item_id) is not None


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path):
    with open(path, encoding="utf8") as fh:
        return json.load(fh)


def label_of(p):
    titre = " ".join((p.get("titre") or "").split())
    auteur = " – ".join(l.strip() for l in ((p.get("auteurs") or p.get("auteur") or "").split("\n")) if l.strip())
    return titre or auteur or "Sans titre", auteur


def save(base, doc, thumb, item_id=None):
    """doc = fiche exportée ({'params':…, 'images':…}). Retourne l'id."""
    d = data_dir(base)
    if not _valid_id(item_id):
        item_id = uuid.uuid4().hex[:12]
    p = doc["params"]
    titre, auteur = label_of(p)
    meta = {"id": item_id, "titre": titre, "auteur": auteur, "type": p.get("type"), "format": p.get("format"),
            "color": p.get("color"), "updated": time.time(), "thumb": thumb}
    _write_json(os.path.join(d, item_id + ".json"), doc)
    _write_json(os.path.join(d, item_id + ".meta.json"), meta)
    return item_id


def listing(base):
    d = data_dir(base)
    items = []
    for fn in os.listdir(d):
        if fn.endswith(".meta.json"):
            try:
                items.append(_read_json(os.path.join(d, fn)))
            except Exception:
                continue
    items.sort(key=lambda m: m.get("updated", 0), reverse=True)
    return items


def load(base, item_id):
    if not _valid_id(item_id):
        raise ValueError("identifiant inconnu")
    return _read_json(os.path.join(data_dir(base), item_id + ".json"))


def delete(base, item_id):
    if not _valid_id(item_id):
        return
    d = data_dir(base)
    for suffix in (".json", ".meta.json"):
        try:
            os.remove(os.path.join(d, item_id + suffix))
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- brouillon

def draft_path(base):
    return os.path.join(base, "brouillon.json")


def draft_save(base, doc):
    path = draft_path(base)
    if os.path.exists(path):
        # première sauvegarde de la session : on garde l'ancien brouillon en secours
        backup = os.path.join(base, "brouillon-precedent.json")
        if draft_save.first:
            try:
                snapshot(base, _read_json(path), force=True)
            except Exception:
                pass
            try:
                os.replace(path, backup)
            except OSError:
                pass
    draft_save.first = False
    _write_json(path, doc)
    try:
        snapshot(base, doc)
    except Exception:
        pass


draft_save.first = True


def draft_load(base):
    try:
        return _read_json(draft_path(base))
    except Exception:
        return None


# ---------------------------------------------------------------- sauvegardes automatiques datées
KEEP_BACKUPS = 10
BACKUP_GAP = 600          # secondes entre deux copies automatiques


def backups_dir(base):
    d = os.path.join(base, "sauvegardes")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot(base, doc, force=False):
    """Copie datée du brouillon : au plus une toutes les 10 minutes (sauf force), jamais deux fois la même, les 10 dernières."""
    p = doc.get("params", {})
    if not any(str(p.get(k) or "").strip() for k in ("titre", "auteurs", "auteur")):
        return None
    d = backups_dir(base)
    files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    if files:
        last = os.path.join(d, files[-1])
        if not force and time.time() - os.path.getmtime(last) < BACKUP_GAP:
            return None
        try:
            if _read_json(last).get("doc", {}).get("params") == p:
                return None
        except Exception:
            pass
    name = time.strftime("%Y-%m-%d_%Hh%Mm%S") + ".json"
    _write_json(os.path.join(d, name), {"t": time.time(), "titre": str(p.get("titre") or "").strip()[:80],
                                        "auteur": str(p.get("auteur") or p.get("auteurs") or "").strip()[:60], "doc": doc})
    for old in sorted(f for f in os.listdir(d) if f.endswith(".json"))[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    return name


def backup_list(base):
    out = []
    d = backups_dir(base)
    for f in sorted((f for f in os.listdir(d) if f.endswith(".json")), reverse=True):
        try:
            j = _read_json(os.path.join(d, f))
            out.append({"name": f, "t": j.get("t", 0), "titre": j.get("titre", ""), "auteur": j.get("auteur", "")})
        except Exception:
            continue
    return out


def backup_load(base, name):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}h[0-9]{2}m[0-9]{2}\.json", name or ""):
        raise ValueError("sauvegarde introuvable")
    p = os.path.join(backups_dir(base), name)
    if not os.path.isfile(p):
        raise ValueError("sauvegarde introuvable")
    return _read_json(p)["doc"]
