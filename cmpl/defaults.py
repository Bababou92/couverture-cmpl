"""Valeurs par défaut, palette CMPL et exemples."""

# Palette de la charte graphique CMPL (hors couleurs principales réservées au logo)
PALETTE = [
    {"group": "Bleus", "colors": [
        {"name": "Bleu 1", "hex": "#425B7C"},
        {"name": "Bleu 2 (référence)", "hex": "#294364"},
        {"name": "Bleu 3", "hex": "#162E4D"},
        {"name": "Bleu 4", "hex": "#081B34"},
        {"name": "Bleu 5", "hex": "#020E1D"},
    ]},
    {"group": "Olives", "colors": [
        {"name": "Olive 1", "hex": "#BDB45C"},
        {"name": "Olive 2", "hex": "#998F36"},
        {"name": "Olive 3", "hex": "#756D1A"},
        {"name": "Olive 4", "hex": "#504805"},
        {"name": "Olive 5", "hex": "#2D2800"},
    ]},
    {"group": "Rouges", "colors": [
        {"name": "Rouge 1", "hex": "#BD5C5C"},
        {"name": "Rouge 2", "hex": "#993636"},
        {"name": "Rouge 3", "hex": "#751A1A"},
        {"name": "Rouge 4", "hex": "#500505"},
        {"name": "Rouge 5", "hex": "#2D0000"},
    ]},

]

# Charte graphique de la littérature malgache
PALETTE_B = [
    {"group": "Littérature malgache", "colors": [
        {"name": "Rouge sombre", "hex": "#8C3A2F"},
        {"name": "Vert olive", "hex": "#7A8456"},
        {"name": "Bleu gris", "hex": "#6F8594"},
        {"name": "Beige doré", "hex": "#D6C29A"},
        {"name": "Rose ambré", "hex": "#C98A7A"},
        {"name": "Gris taupe", "hex": "#8A8178"},
        {"name": "Brun sable", "hex": "#B89A6A"},
        {"name": "Bleu pâle", "hex": "#AFC1CC"},
    ]},
]

PALETTES = {"A": PALETTE, "B": PALETTE_B}
ALL_GROUPS = PALETTE + PALETTE_B

COLLECTIONS = [
    "Enseignement supérieur",
    "Codes et recueils usuels",
    "Droit usuel bilingue",
]

DEFAULT_FORMAT = {"A": "145x210", "B": "114x178"}
DEFAULT_COLOR = {"A": "#294364", "B": "#8C3A2F"}

EXAMPLE_A = {
    "type": "A", "format": "145x210", "color": "#294364", "logo": "couleur", "spine_mm": 22,
    "auteurs": "Rakotonaivo Thomas\nNakany Charly Zafimagnely\nRakotomahanana A. Franklin James\nRajoelisoa I. Adeline",
    "titre": "Code de procédure civile", "sous_titre": "", "tome": "", "details": "", "mention": "",
    "collection": "Codes et recueils usuels",
    "titre_4e": "Code de procédure civile",
    "texte_4e": ("- De la procédure devant les tribunaux, dispositions liminaires\n"
                 "Des principes directeurs du procès, des règles propres à la matière gracieuse\n"
                 "  Des dispositions générales\n  Des juridictions\n  De la procédure devant les tribunaux\n"
                 "  De l’arbitrage\n"
                 "- Des voies d’exécution\n  Des règles générales pour l’exécution\n  Des saisies\n"
                 "- Procédures diverses\n- Autres procédures diverses"),
    "auteurs_4e": "Thomas Rakotonaivo\nCharly Zafimagnely Nakany\nA. Franklin James Rakotomahanana\nIrène Adeline Rajoelisoa",
    "isbn": "978-2-494268-20-3", "slogan": "TOUT ce qu’il faut SAVOIR",
    "dos_titre": "", "dos_auteur": "Collectif",
}

EXAMPLE_B = {
    "type": "B", "format": "114x178", "color": "#8C3A2F", "logo": "mono", "spine_mm": 9,
    "auteur": "Paul Rapatsalahy", "titre": "Ilay vorona\nmena", "maison": "Éditions CMPL",
    "illustration": "ex-aigle",
    "auteur_4e": "Paul Rapatsalahy\nIdealy-Soa",
    "texte_4e": ("Efa hariva mena masoandro tamin’izay. Injany any ambala daholo ny omby aman’ondry, ary efa "
                 "mipariaka eo an-tokotany ny akoho amam-borona, fahanana sy ampisotroin-drano.\n"
                 "Zazakely tokony ho 12 taona no tena voabaiko hanao izany, atrehim-behivavy lehibe miteny-kiho "
                 "sy mitatatata vava amin’ny fibaikoana an’ilaykely. Raha tombanana ilay zaza dia hita mahia, "
                 "rovitra ny akanjony ary feno hatina ny tenany noho ny halotony. Misy parasy ny togony ka "
                 "mitsidrahaka mahonera, ary hafahafa ny fandehany mandroaka ireo vorony hiditra ny tranony.\n"
                 "- Haingana ry Ngivy à, hoy ilay Ramatoa. Mbola miandry an-tena anie na toto vary, na soron’afo, "
                 "na tsako rano. Nefa ny masoandro ity efa hilentika. Izany ilay kamolahy ity vao hahita ny tsy "
                 "fahitana raha tonga eo Rangahy.\n…"),
    "logo_rond": "defaut", "dos_titre": "", "dos_auteur": "Idealy-Soa",
}

BLANK_A = dict(EXAMPLE_A, **{k: "" for k in (
    "auteurs", "titre", "titre_4e", "texte_4e", "auteurs_4e", "isbn", "dos_auteur", "collection")},
    slogan="TOUT ce qu’il faut SAVOIR")
BLANK_B = dict(EXAMPLE_B, **{k: "" for k in (
    "auteur", "titre", "auteur_4e", "texte_4e", "dos_auteur")}, illustration=None)

KEYS = ["type", "format", "color", "logo", "spine_mm", "auteurs", "auteur", "titre", "sous_titre", "tome",
        "details", "mention", "collection", "titre_4e", "texte_4e", "auteurs_4e", "auteur_4e", "isbn", "slogan",
        "dos_titre", "dos_auteur", "illustration", "maison", "logo_rond",
        "ill_zoom", "ill_x", "ill_y", "ill_tint"]

def to_float(v, default=None):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def normalize(p):
    """Complète les paramètres manquants avec les valeurs du type choisi."""
    kind = p.get("type", "A")
    base = dict(EXAMPLE_A if kind == "A" else EXAMPLE_B)
    out = {k: (base.get(k) if k in ("type", "format", "color", "logo", "spine_mm", "logo_rond") else "") for k in KEYS}
    out["illustration"] = None
    out.update({k: v for k, v in p.items() if k in KEYS})
    out["type"] = kind
    if out.get("format") not in ("145x210", "190x240", "114x178"):
        out["format"] = DEFAULT_FORMAT[kind]
    if not out.get("color"):
        out["color"] = DEFAULT_COLOR[kind]
    tint = p.get("ill_tint", True)
    out["ill_tint"] = tint not in (False, 0, "0", "non", "Non", "false", "False")
    out["ill_zoom"] = _clamp(to_float(p.get("ill_zoom"), 1.0), 1.0, 8.0)
    out["ill_x"] = _clamp(to_float(p.get("ill_x"), 0.5), 0.0, 1.0)
    out["ill_y"] = _clamp(to_float(p.get("ill_y"), 0.5), 0.0, 1.0)
    try:
        out["spine_mm"] = max(3.0, min(80.0, float(out.get("spine_mm") or (22 if kind == "A" else 9))))
    except (TypeError, ValueError):
        out["spine_mm"] = 22 if kind == "A" else 9
    return out
