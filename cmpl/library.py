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
                os.replace(path, backup)
            except OSError:
                pass
    draft_save.first = False
    _write_json(path, doc)


draft_save.first = True


def draft_load(base):
    try:
        return _read_json(draft_path(base))
    except Exception:
        return None
