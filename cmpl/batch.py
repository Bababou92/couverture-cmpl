"""Génération en lot depuis un fichier Excel (.xlsx) ou CSV : une ligne = un livre."""
import csv
import io
import os
import re
import unicodedata

from . import defaults

# (en-tête affiché, clé, aide, exemple droit, exemple malgache)
COLUMNS = [
    ("Type", "type", "Droit  ou  Malgache (modèle de couverture)", "Droit", "Malgache"),
    ("Format", "format", "145x210  /  190x240  /  114x178 (vide = format habituel du modèle)", "145x210", "114x178"),
    ("Couleur", "color", "Nom de la palette (liste déroulante, onglet Couleurs) ou code hexadécimal (ex. 294364)", "Bleu 2", "Rouge sombre"),
    ("Titre", "titre", "Titre de la 1re de couverture. Retour à la ligne dans la case : Alt + Entrée", "Code de procédure civile", "Ilay vorona\nmena"),
    ("Auteurs", "auteurs", "Un auteur par ligne (Alt + Entrée) ou séparés par |  — Droit : Nom Prénom", "Rakotonaivo Thomas | Nakany Charly Zafimagnely", "Paul Rapatsalahy"),
    ("Sous-titre", "sous_titre", "Droit seulement, optionnel", "", ""),
    ("Tome", "tome", "Droit seulement, optionnel (ex. Tome 1)", "", ""),
    ("Détails", "details", "Droit seulement, optionnel : une ligne par détail, séparées par |", "", ""),
    ("Mention", "mention", "Droit seulement, optionnel (ex. nouvelle édition 2026)", "", ""),
    ("Collection", "collection", "Droit seulement : texte de la case blanche du bas", "Codes et recueils usuels", ""),
    ("Maison", "maison", "Malgache seulement (vide = Éditions CMPL)", "", "Éditions CMPL"),
    ("Titre 4e", "titre_4e", "Droit seulement (vide = même titre que la 1re)", "", ""),
    ("Texte 4e", "texte_4e", "Texte de la 4e de couverture (Alt + Entrée pour les paragraphes)", "- Des voies d’exécution\n  Des saisies", "Efa hariva mena masoandro tamin’izay…"),
    ("Auteurs 4e", "auteurs_4e", "Vide = comme la 1re. Malgache : lignes affichées en haut de la 4e (ex. Paul Rapatsalahy | Idealy-Soa)", "Thomas Rakotonaivo | Charly Zafimagnely Nakany", "Paul Rapatsalahy | Idealy-Soa"),
    ("ISBN", "isbn", "Droit : le code-barres est généré automatiquement", "978-2-494268-20-3", ""),
    ("Slogan", "slogan", "Droit seulement (vide = TOUT ce qu’il faut SAVOIR)", "", ""),
    ("Illustration", "illustration", "Malgache : chemin de l'image, ou nom du fichier présent dans le dossier des illustrations", "", "aigle.png"),
    ("Logo rond", "logo_rond", "Malgache : defaut / aucun / chemin d'une image", "", "defaut"),
    ("Image colorée", "ill_tint", "Malgache : Oui = l'illustration prend la couleur du livre (habituel), Non = couleurs d'origine", "", "Oui"),
    ("Logo", "logo", "Couleur / Noir / Mono (vide = habituel du modèle)", "", ""),
    ("Épaisseur dos (mm)", "spine_mm", "Facultatif, à laisser vide (22 mm Droit, 9 mm Malgache par défaut)", "", ""),
    ("Auteur dos", "dos_auteur", "Vide = automatique (Collectif si plus de 2 auteurs)", "", "Idealy-Soa"),
    ("Titre dos", "dos_titre", "Vide = même titre que la 1re", "", ""),
    ("Nom de fichier", "name", "Vide = titre du livre", "", ""),
]


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


ALIASES = {}
for _h, _k, *_ in COLUMNS:
    ALIASES[_norm(_h)] = _k
ALIASES.update({
    "modele": "type", "taille": "format", "color": "color", "auteur": "auteurs", "auteur4e": "auteurs_4e",
    "volume": "tome", "tomevolume": "tome", "maisondedition": "maison", "image": "illustration",
    "texte": "texte_4e", "quatriemedecouverture": "texte_4e", "epaisseurdos": "spine_mm",
    "epaisseurdosmm": "spine_mm", "dos": "spine_mm", "auteurdudos": "dos_auteur", "titredudos": "dos_titre",
    "fichier": "name", "epaisseur": "spine_mm", "couleurimage": "ill_tint", "imagecolor": "ill_tint",
})

MULTILINE_PIPE = {"auteurs", "details", "auteurs_4e"}


# ------------------------------------------------------------------ modèle Excel

SCOPE_A = {"sous_titre", "tome", "details", "mention", "collection", "titre_4e", "isbn", "slogan"}
SCOPE_B = {"maison", "illustration", "logo_rond", "ill_tint"}
HEADER_OF = {k: h for h, k, *_ in COLUMNS}


def ignored_columns(kind, d):
    """En-têtes des colonnes remplies mais sans effet pour ce modèle."""
    other = SCOPE_B if kind == "A" else SCOPE_A
    return [HEADER_OF[k] for k in HEADER_OF if k in other and (d.get(k) or "").strip()]


def make_template(path):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Livres"
    keys = [c[1] for c in COLUMNS]
    fills = {"*": "294364", "A": "3E6FA8", "B": "8C3A2F"}
    HEAD_ROW, FIRST = 2, 3

    ncol = len(COLUMNS)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=min(ncol, 12))
    ws["A1"] = ("Une ligne = un livre, à partir de la ligne 3. Pour passer à la ligne dans une case : Alt + Entrée. "
                "Cases vides = valeur habituelle. Survole un titre de colonne pour l'aide. "
                "Couleurs d'en-tête : bleu foncé = tous les livres · bleu clair = modèle Droit seulement · "
                "brun = modèle Malgache seulement.")
    ws["A1"].alignment = Alignment(wrap_text=True, vertical="center")
    ws["A1"].font = Font(italic=True, color="444444")
    ws.row_dimensions[1].height = 48

    def header_cells(sheet, row):
        for ci, (h, k, helptxt, _a, _b) in enumerate(COLUMNS, 1):
            c = sheet.cell(row=row, column=ci, value=h)
            scope = "A" if k in SCOPE_A else ("B" if k in SCOPE_B else "*")
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=fills[scope])
            c.alignment = Alignment(wrap_text=True, vertical="center")
            c.comment = Comment(helptxt, "CMPL")
            c.comment.width, c.comment.height = 320, 90
            sheet.column_dimensions[get_column_letter(ci)].width = (
                30 if h in ("Titre", "Auteurs", "Texte 4e", "Détails", "Auteurs 4e") else 16)
        sheet.row_dimensions[row].height = 32

    header_cells(ws, HEAD_ROW)
    ws.freeze_panes = f"A{FIRST}"
    for r in range(FIRST, FIRST + 200):
        for ci in range(1, ncol + 1):
            ws.cell(row=r, column=ci).alignment = Alignment(wrap_text=True, vertical="top")

    # onglet couleurs (nom + échantillon) : sert aussi de liste déroulante
    wc = wb.create_sheet("Couleurs")
    wc["A1"], wc["B1"], wc["C1"], wc["D1"] = "Nom (à écrire dans la colonne Couleur)", "Code", "Échantillon", "Pour le modèle"
    wc.column_dimensions["D"].width = 16
    for c in ("A1", "B1", "C1", "D1"):
        wc[c].font = Font(bold=True)
    wc.column_dimensions["A"].width = 38
    wc.column_dimensions["B"].width = 12
    wc.column_dimensions["C"].width = 14
    r = 2
    for g in defaults.ALL_GROUPS:
        for col in g["colors"]:
            name = col["name"].replace(" (référence)", "")
            wc.cell(row=r, column=4, value="Malgache" if g in defaults.PALETTE_B else "Droit")
            wc.cell(row=r, column=1, value=name)
            wc.cell(row=r, column=2, value=col["hex"])
            wc.cell(row=r, column=3).fill = PatternFill("solid", fgColor=col["hex"].lstrip("#"))
            r += 1
    last_color = r - 1
    wc.cell(row=r + 1, column=1, value="Tu peux aussi écrire n'importe quel code, par exemple 1F6F43 ou #1F6F43.")

    def add_list(key, formula, strict=False):
        col = get_column_letter(keys.index(key) + 1)
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=strict)
        ws.add_data_validation(dv)
        dv.add(f"{col}{FIRST}:{col}{FIRST + 199}")

    add_list("type", '"Droit,Malgache"', True)
    add_list("format", '"145x210,190x240,114x178"', True)
    add_list("logo", '"Couleur,Noir,Mono"', True)
    add_list("logo_rond", '"defaut,aucun"')
    add_list("color", f"=Couleurs!$A$2:$A${last_color}")

    # exemples
    we = wb.create_sheet("Exemples")
    we.merge_cells("A1:L1")
    we["A1"] = "Deux livres d'exemple (un Droit, un Malgache). Recopie une ligne dans l'onglet « Livres » et modifie-la."
    we["A1"].font = Font(italic=True, color="444444")
    header_cells(we, 2)
    for r, idx in ((3, 3), (4, 4)):
        for ci, col in enumerate(COLUMNS, 1):
            val = col[idx]
            c = we.cell(row=r, column=ci, value=val if val != "" else None)
            c.alignment = Alignment(wrap_text=True, vertical="top")

    # mode d'emploi
    wm = wb.create_sheet("Mode d'emploi")
    wm.column_dimensions["A"].width = 24
    wm.column_dimensions["B"].width = 110
    wm["A1"], wm["B1"] = "Colonne", "À remplir"
    wm["A1"].font = wm["B1"].font = Font(bold=True)
    notes = [
        ("1", "Remplis l'onglet « Livres » : une ligne par livre. Enregistre le fichier (Ctrl + S) et ferme-le."),
        ("2", "Dans le générateur : « Lot Excel » → choisis ce fichier. Tu vois tout ce qui va être créé avant de valider."),
        ("3", "Chaque livre aura son propre dossier, nommé comme le livre, avec ses images, son PowerPoint et son PDF."),
        ("", "Les images (colonne Illustration / Logo rond) : mets-les dans le même dossier que ce fichier Excel "
             "et écris juste le nom du fichier, par exemple aigle.png."),
        ("", "Pour passer à la ligne dans une case : Alt + Entrée (ou le signe | dans Auteurs et Détails)."),
    ]
    r = 2
    for a, b in notes:
        wm.cell(row=r, column=1, value=a)
        wm.cell(row=r, column=2, value=b).alignment = Alignment(wrap_text=True)
        r += 1
    r += 1
    for h, _k, helptxt, _a, _b in COLUMNS:
        wm.cell(row=r, column=1, value=h).font = Font(bold=True)
        wm.cell(row=r, column=2, value=helptxt).alignment = Alignment(wrap_text=True)
        r += 1
    wb.active = 0
    wb.save(path)


# ------------------------------------------------------------------ lecture

def _find_header(table):
    """Index de la ligne d'en-têtes (parmi les 10 premières) : celle qui contient le plus de colonnes connues."""
    best, best_n = 0, 0
    for i, row in enumerate(table[:10]):
        n = sum(1 for h in row if ALIASES.get(_norm(h)))
        if n > best_n:
            best, best_n = i, n
    return best if best_n >= 2 else 0


def read_rows(data: bytes, filename="livres.xlsx"):
    """Retourne la liste de (numéro de ligne Excel, dict clé->valeur texte)."""
    name = filename.lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:2000]
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        table = list(csv.reader(io.StringIO(text), delimiter=delim))
    else:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), data_only=True)
        ws = wb["Livres"] if "Livres" in wb.sheetnames else wb.worksheets[0]
        table = [[("" if c is None else c) for c in row] for row in ws.iter_rows(values_only=True)]
    if not table:
        return []
    hi = _find_header(table)
    keys = [ALIASES.get(_norm(h)) for h in table[hi]]
    if not any(keys):
        raise ValueError("je ne trouve pas les titres de colonnes (Type, Titre, Auteurs…). "
                         "Utilise le modèle Excel proposé par le générateur.")
    rows = []
    for i, row in enumerate(table[hi + 1:], start=hi + 2):
        d = {}
        for k, v in zip(keys, row):
            if not k:
                continue
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            d[k] = str(v).replace("\r", "").strip() if v is not None else ""
        if any(v for v in d.values()):
            rows.append((i, d))
    return rows


# ------------------------------------------------------------------ conversion en paramètres

def _color(value, extra):
    v = (value or "").strip()
    if not v:
        return None
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", v)
    if m:
        return "#" + m.group(1).upper()
    table = {}
    for g in defaults.ALL_GROUPS:
        for c in g["colors"]:
            table[_norm(c["name"])] = c["hex"]
            table[_norm(c["name"].replace(" (référence)", ""))] = c["hex"]
    for c in extra or []:
        table[_norm(c["name"])] = c["hex"]
    hexv = table.get(_norm(v))
    if not hexv:
        raise ValueError(f"couleur inconnue « {v} » (code hexadécimal ou nom de la palette)")
    return hexv


def row_to_params(d, extra_colors=None, img_loader=None):
    t = _norm(d.get("type") or "droit")
    if t in ("a", "droit", "droits", "enseignementsuperieur"):
        kind = "A"
    elif t in ("b", "malgache", "litterature", "litteraturemalgache", "illustre"):
        kind = "B"
    else:
        raise ValueError(f"type inconnu « {d.get('type')} » (Droit ou Malgache)")
    p = {"type": kind}
    fmt = re.findall(r"\d+", d.get("format") or "")
    if len(fmt) >= 2:
        p["format"] = f"{fmt[0]}x{fmt[1]}"
        if p["format"] not in ("145x210", "190x240", "114x178"):
            raise ValueError("format inconnu (145x210, 190x240 ou 114x178)")
    c = _color(d.get("color"), extra_colors)
    if c:
        p["color"] = c
    for key in ("titre", "sous_titre", "tome", "mention", "collection", "maison", "titre_4e", "texte_4e", "isbn",
                "slogan", "dos_auteur", "dos_titre"):
        if d.get(key):
            p[key] = d[key]
    for key in MULTILINE_PIPE:
        if d.get(key):
            p[key] = re.sub(r"\s*\|\s*", "\n", d[key])
    # l'auteur de la 1re change de nom de clé selon le modèle
    if kind == "B":
        p["auteur"] = p.pop("auteurs", "")
        if "auteurs_4e" in p:
            p["auteur_4e"] = p.pop("auteurs_4e")
    logo = _norm(d.get("logo"))
    if logo in ("couleur", "couleurs", "origine"):
        p["logo"] = "couleur"
    elif logo in ("noir", "noiretblanc", "nb"):
        p["logo"] = "noir"
    elif logo in ("mono", "monochrome", "livre"):
        p["logo"] = "mono"
    if kind == "B":
        rond = (d.get("logo_rond") or "defaut").strip()
        if _norm(rond) in ("defaut", "defautaucun") or not rond:
            p["logo_rond"] = "defaut"
        elif _norm(rond) == "aucun":
            p["logo_rond"] = "aucun"
        elif img_loader:
            p["logo_rond"] = img_loader(rond)
        if d.get("illustration") and img_loader:
            p["illustration"] = img_loader(d["illustration"])
        p["ill_tint"] = _norm(d.get("ill_tint") or "oui") not in ("non", "no", "0", "false", "faux")
    # dos
    spine = defaults.to_float(d.get("spine_mm"))
    if spine:
        p["spine_mm"] = spine
    return defaults.normalize(p)
