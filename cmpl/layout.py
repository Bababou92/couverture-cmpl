"""Gabarits des couvertures (type A « droit » et type B « littérature malgache »).

Chaque gabarit produit une liste d'éléments (rectangles, images, zones de texte)
en millimètres. Les mêmes éléments servent à dessiner le PNG et à écrire le PPTX,
donc les deux sorties sont identiques.
"""
import threading
from dataclasses import dataclass, field, replace
from typing import List, Optional

from PIL import Image

from . import assets, colors, textfit
from .textfit import MM_PER_PT, Para, Run

FORMATS = {
    "145x210": (145.0, 210.0, "Droit usuel · 145 × 210 mm"),
    "190x240": (190.0, 240.0, "Grand format · 190 × 240 mm"),
    "114x178": (114.0, 178.0, "Littérature malgache · 114 × 178 mm"),
}

WHITE = "#FFFFFF"
BLACK = "#000000"
SPINE_SCALE = 0.7           # le texte du dos est en petite taille pour tous les livres


# ------------------------------------------------------------------ éléments

@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: Optional[str] = None
    line: Optional[str] = None
    line_pt: float = 0.0
    name: str = "Rectangle"
    bleed: str = ""             # côtés à prolonger dans les fonds perdus (l, r, t, b)


@dataclass
class Pic:
    x: float
    y: float
    w: float
    h: float
    image: Image.Image = None
    name: str = "Image"
    fmt: str = "PNG"            # format d'incorporation dans le PPTX
    bleed: str = ""             # côtés à prolonger dans les fonds perdus (l, r, t, b)


@dataclass
class TextBox:
    x: float
    y: float
    w: float
    h: float
    paras: List[Para] = field(default_factory=list)
    anchor: str = "t"           # t, m, b
    rot: int = 0                # 0 ou 270 (texte vertical, lecture de bas en haut)
    inset: float = 0.0          # mm, identique sur les 4 côtés
    name: str = "Texte"


@dataclass
class Page:
    name: str
    w: float
    h: float
    bg: str = WHITE
    elements: list = field(default_factory=list)
    crop: Optional[tuple] = None   # (x0, y0, x1, y1) mm : zone exportée en PNG (dos)


# ------------------------------------------------------------------ remarques (alertes)

_tl = threading.local()


class Notes:
    """Remarques recueillies pendant la mise en page : (niveau, texte), niveau = info | warn | error."""

    def __init__(self):
        self.items = []
        self.hot = {}
        self.spots = []         # zones de texte modifiables par double-clic dans l'aperçu

    def add(self, level, text):
        if (level, text) not in self.items:
            self.items.append((level, text))


def last_notes():
    n = getattr(_tl, "n", None)
    if n is None:
        n = _tl.n = Notes()
    return n


def note(level, text):
    last_notes().add(level, text)


def F(key, label, value, multiline=False):
    return {"key": key, "label": label, "value": value or "", "multiline": multiline}


def spot(label, fields, x, y, w, h, rot=0, family="arial", size=12.0):
    """Zone cliquable (mm, coordonnées de la page) qui ouvre l'édition des champs donnés."""
    last_notes().spots.append({"face": getattr(_tl, "face", 0), "label": label, "fields": fields,
                               "rect": [x, y, w, h], "rot": rot, "family": family, "size": size})


def _spots_to_fractions(pages):
    out = []
    for sp in last_notes().spots:
        pg = pages[sp["face"]]
        x0, y0, x1, y1 = pg.crop if pg.crop else (0.0, 0.0, pg.w, pg.h)
        x, y, w, h = sp["rect"]
        fx, fy = (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)
        fw, fh = w / (x1 - x0), h / (y1 - y0)
        fx2, fy2 = min(1.0, fx + fw), min(1.0, fy + fh)
        fx, fy = max(0.0, fx), max(0.0, fy)
        out.append({"face": sp["face"], "label": sp["label"], "fields": sp["fields"], "rot": sp["rot"],
                    "family": sp["family"], "size": sp["size"], "wmm": x1 - x0,
                    "rect": [fx, fy, fx2 - fx, fy2 - fy]})
    return out


def _shrink_note(label, k, fits, warn_below=0.8):
    if not fits:
        note("error", f"{label} : le texte est trop long, il dépasse de sa zone. Raccourcis-le.")
    elif k < warn_below:
        note("warn", f"{label} : texte réduit à {round(k * 100)} % de sa taille normale pour tenir.")


def _fit(label, make, w_pt, h_pt, kmin=0.35, warn_below=0.8):
    """textfit.fit_scale + remarque si le texte a dû être réduit (ou déborde malgré tout)."""
    k, paras = textfit.fit_scale(make, w_pt, h_pt, kmin=kmin)
    fits = textfit.longest_word(paras) <= w_pt + 1e-6 and textfit.total_height(paras, w_pt) <= h_pt + 1e-6
    _shrink_note(label, k, fits, warn_below)
    return k, paras


def _small_note(label, size_pt, limit=7.0):
    if size_pt < limit - 1e-6:
        note("warn", f"{label} : caractères de {size_pt:g} pt, petits à l'impression.")


# ------------------------------------------------------------------ outils

def _s(W, H, bw, bh):
    return W / bw, H / bh, min(W / bw, H / bh)


def lines_of(text):
    return [l.strip() for l in (text or "").replace("\r", "").split("\n") if l.strip()]


def explode_lines(paras, width_pt):
    """Un paragraphe par ligne visuelle (les retours à la ligne deviennent explicites)."""
    out = []
    for para in paras:
        for pieces in textfit._wrap(para, width_pt):
            merged = []
            for piece in pieces:
                if merged and merged[-1][1] is piece.run:
                    merged[-1] = (merged[-1][0] + piece.text, piece.run)
                else:
                    merged.append((piece.text, piece.run))
            out.append(replace(para, runs=[replace(r, text=t) for t, r in merged]))
    return out


def _contain(img: Image.Image, bw, bh):
    """Dimensions (w, h) en mm de img inscrite dans (bw, bh), centrée."""
    r = min(bw / img.width, bh / img.height)
    return img.width * r, img.height * r


def _place_in_box(img, bx, by, bw, bh, zoom=1.0, fx=0.5, fy=0.5):
    """Place img dans le cadre (bx, by, bw, bh) mm. zoom 1 = image entière ; au-delà, elle est recadrée.

    (fx, fy) = point de l'image (0..1) ramené au centre du cadre. Retourne (Pic, infos).
    """
    zoom = max(1.0, float(zoom or 1.0))
    r = min(bw / img.width, bh / img.height) * zoom            # mm par pixel
    dw, dh = img.width * r, img.height * r

    def axis(box, size, f):
        if size <= box + 1e-9:
            return (box - size) / 2.0                          # image entière, centrée
        return min(0.0, max(box - size, box / 2.0 - f * size))

    ox, oy = axis(bw, dw, fx), axis(bh, dh, fy)
    vx0, vy0 = max(0.0, ox), max(0.0, oy)
    vx1, vy1 = min(bw, ox + dw), min(bh, oy + dh)
    box_px = (round((vx0 - ox) / r), round((vy0 - oy) / r), round((vx1 - ox) / r), round((vy1 - oy) / r))
    l, t, rr, b = box_px
    rr, b = max(rr, l + 1), max(b, t + 1)
    crop = img if (l, t, rr, b) == (0, 0, img.width, img.height) else img.crop((l, t, min(rr, img.width), min(b, img.height)))
    vw = vx1 - vx0
    cover = max(bw / img.width, bh / img.height) / min(bw / img.width, bh / img.height)
    dpi = crop.width / (vw / 25.4) if vw > 0 else 0.0
    pic = Pic(bx + vx0, by + vy0, vw, vy1 - vy0, crop, name="Illustration", fmt="AUTO")
    return pic, {"disp": [dw, dh], "cover": cover, "zoom": zoom, "dpi": dpi}


def _text_fit_box(box_w_mm, box_h_mm, inset_mm):
    return (box_w_mm - 2 * inset_mm) / MM_PER_PT, (box_h_mm - 2 * inset_mm) / MM_PER_PT


def _single(text, family, size, color, *, bold=False, italic=False, smallcaps=False, caps=False, align="l"):
    return Para([Run(text, family, size, bold, italic, color, smallcaps, caps)], align=align)


# ------------------------------------------------------------------ type A

def a_front(p, W, H, user_imgs):
    sx, sy, s = _s(W, H, 145.0, 210.0)
    C = p["color"]
    els = []

    m_left, m_top, m_bottom = 11.7 * sx, 9.8 * sy, 12.1 * sy
    strip_w = 21.7 * sx
    row_h = strip_w
    gap_v = 9.8 * sy
    frame_x = 42.6 * sx
    frame_w = W - m_left - frame_x
    frame_h = H - m_top - m_bottom - row_h - gap_v
    row_y = m_top + frame_h + gap_v

    # --- bandeau blanc auteurs
    els.append(Rect(m_left, m_top, strip_w, frame_h, fill=WHITE, name="Bandeau auteurs"))
    inset = 1.8 * s
    authors = lines_of(p.get("auteurs"))
    spot("Auteurs", [F("auteurs", "Auteurs (un par ligne)", p.get("auteurs"), True)],
         m_left, m_top, strip_w, frame_h, rot=270, family="arial", size=14 * s)
    if authors:
        L_pt = (frame_h - 2 * inset) / MM_PER_PT
        thick_pt = (strip_w - 2 * inset) / MM_PER_PT

        def make(k):
            size = textfit.round_pt(14 * s * k)
            sep = " – "
            lines, cur = [], ""
            for a in authors:
                cand = a if not cur else cur + sep + a
                if cur and textfit.text_width_pt(cand, "arial", size, True, False, True) > L_pt:
                    lines.append(cur)
                    cur = a
                else:
                    cur = cand
            if cur:
                lines.append(cur)
            return [Para([Run(l, "arial", size, True, False, C, True)], align="r") for l in lines]

        k, paras = _fit("Auteurs (1re de couverture)", make, L_pt, thick_pt)
        els.append(TextBox(m_left, m_top, strip_w, frame_h, paras, anchor="m", rot=270, inset=inset,
                           name="Auteurs"))

    # --- cadre du titre
    els.append(Rect(frame_x, m_top, frame_w, frame_h, fill=C, line=WHITE, line_pt=1.5 * s, name="Cadre"))
    spot("Bloc titre", [F("titre", "Titre", p.get("titre"), True), F("sous_titre", "Sous-titre", p.get("sous_titre")),
                        F("tome", "Tome / volume", p.get("tome")), F("details", "Détails (une ligne chacun)", p.get("details"), True),
                        F("mention", "Mention", p.get("mention"))],
         frame_x, m_top, frame_w, frame_h, family="arial", size=18 * s)
    pad_x = 7.25 * sx
    inner_w = frame_w - 2 * pad_x
    inner_w_pt = inner_w / MM_PER_PT
    has_mention = bool((p.get("mention") or "").strip())
    top = m_top + 6 * sy
    bottom = m_top + frame_h - 6 * sy - (9 * sy if has_mention else 0)
    avail_pt = (bottom - top) / MM_PER_PT

    titre = (p.get("titre") or "").strip()
    sous = (p.get("sous_titre") or "").strip()
    tome = (p.get("tome") or "").strip()
    details = lines_of(p.get("details"))

    def comps(k):
        out = []
        ts = textfit.round_pt(28 * s * k)
        if titre:
            lines = textfit.balanced_lines(
                titre, lambda t: textfit.text_width_pt(t, "arial", ts, True, False, False, True), inner_w_pt)
            out.append(("Titre", [_single(l, "arial", ts, WHITE, bold=True, caps=True, align="c") for l in lines], 0.0))
        if sous:
            ss = textfit.round_pt(12.5 * s * k)
            lines = textfit.balanced_lines(
                sous, lambda t: textfit.text_width_pt(t, "arial", ss, True, False, False, True), inner_w_pt)
            out.append(("Sous-titre", [_single(l, "arial", ss, WHITE, bold=True, caps=True, align="c") for l in lines],
                        9 * s * k / MM_PER_PT * MM_PER_PT))
        if tome:
            ts2 = textfit.round_pt(11 * s * k)
            out.append(("Tome", [_single(tome, "arial", ts2, WHITE, align="c")], 6 * s * k))
        if details:
            ds = textfit.round_pt(9 * s * k)
            out.append(("Détails", [_single(l, "arial", ds, WHITE, align="c") for l in details], 6 * s * k))
        return out

    def block_height(cs):
        total = 0.0
        for i, (_n, paras, gap_mm) in enumerate(cs):
            total += textfit.total_height(paras, inner_w_pt) + (gap_mm / MM_PER_PT if i else 0)
        return total

    k = 1.0
    while True:
        cs = comps(k)
        title_lines = len(cs[0][1]) if cs and cs[0][0] == "Titre" else 0
        ok = all(textfit.longest_word(c[1]) <= inner_w_pt + 1e-6 for c in cs)
        ok = ok and block_height(cs) <= avail_pt + 1e-6 and title_lines <= 4
        if ok or k <= 0.3:
            break
        k = max(0.3, k - 0.02)
    _shrink_note("Titre", k, ok)

    y = top + ((bottom - top) - block_height(cs) * MM_PER_PT) / 2
    for i, (name, paras, gap_mm) in enumerate(cs):
        if i:
            y += gap_mm
        h_mm = textfit.total_height(paras, inner_w_pt) * MM_PER_PT
        els.append(TextBox(frame_x + pad_x, y, inner_w, h_mm, paras, anchor="t", name=name))
        key, lab, multi = {"Titre": ("titre", "Titre", True), "Sous-titre": ("sous_titre", "Sous-titre", False),
                           "Tome": ("tome", "Tome / volume", False), "Détails": ("details", "Détails (une ligne chacun)", True)}[name]
        spot(name, [F(key, lab, p.get(key), multi)], frame_x + pad_x, y, inner_w, h_mm,
             family="arial", size=paras[0].runs[0].size)
        y += h_mm

    if has_mention:
        ms = textfit.round_pt(9 * s)
        txt = p["mention"].strip()
        while textfit.text_width_pt(txt, "arial", ms, False, True) > inner_w_pt and ms > 5:
            ms -= 0.5
        h_mm = textfit.line_height_pt(Run("x", "arial", ms)) * MM_PER_PT
        els.append(TextBox(frame_x + pad_x, m_top + frame_h - 6 * sy - h_mm, inner_w, h_mm,
                           [_single(txt, "arial", ms, WHITE, italic=True, align="c")], anchor="b", name="Mention"))
        spot("Mention", [F("mention", "Mention", p.get("mention"))], frame_x + pad_x, m_top + frame_h - 6 * sy - h_mm,
             inner_w, h_mm, family="arial", size=ms)

    # --- ligne du bas : logo + collection
    els.append(Pic(m_left, row_y, strip_w, row_h, assets.logo(p.get("logo", "couleur"), C), name="Logo CMPL"))
    els.append(Rect(frame_x, row_y, frame_w, row_h, fill=WHITE, name="Case collection"))
    coll = (p.get("collection") or "").strip()
    spot("Collection", [F("collection", "Collection", p.get("collection"))], frame_x, row_y, frame_w, row_h,
         family="arial", size=18 * s)
    if coll:
        ins = 2.5 * s
        w_pt, h_pt = _text_fit_box(frame_w, row_h, ins)

        def make_c(k):
            sz = textfit.round_pt(18 * s * k)
            return [_single(coll, "arial", sz, BLACK, smallcaps=True, align="c")]

        _k, paras = _fit("Collection", make_c, w_pt, h_pt)
        els.append(TextBox(frame_x, row_y, frame_w, row_h, paras, anchor="m", inset=ins, name="Collection"))
    return Page("1re de couverture", W, H, bg=C, elements=els)


def parse_body(text, size, color, s, family="arial", align="j"):
    """Texte de 4e : lignes vides = espace, « - » = puce, retrait (espaces/tabulation) = sous-élément."""
    paras = []
    for raw in (text or "").replace("\r", "").split("\n"):
        if not raw.strip():
            paras.append(Para([Run("", family, size, False, False, color)], align="l"))
            continue
        stripped = raw.lstrip(" \t")
        indent = raw[: len(raw) - len(stripped)]
        if stripped[:2] in ("- ", "• ", "* ") or stripped[:1] in ("•",):
            body = stripped[2:] if stripped[1:2] == " " else stripped[1:]
            paras.append(Para([Run(body.strip(), family, size, False, False, color)], align=align,
                              left_mm=4.5 * s, first_mm=-4.5 * s, bullet="•"))
        elif indent.count("\t") or len(indent) >= 2:
            level = max(indent.count("\t"), len(indent) // 2, 1)
            paras.append(Para([Run(stripped, family, size, False, False, color)], align="l",
                              left_mm=10 * s * min(level, 3)))
        else:
            paras.append(Para([Run(stripped, family, size, False, False, color)], align=align))
    return paras


def a_back(p, W, H, user_imgs):
    sx, sy, s = _s(W, H, 145.0, 210.0)
    C = p["color"]
    els = []
    frame_w = 90.7 * sx
    frame_x = (W - frame_w) / 2
    frame_y = 9.8 * sy
    frame_h = 134.1 * sy
    els.append(Rect(frame_x, frame_y, frame_w, frame_h, fill=C, line=WHITE, line_pt=1.5 * s, name="Cadre"))

    tx, ty = frame_x + 4.5 * sx, frame_y + 6.5 * sy
    tw, th = frame_w - 9 * sx, frame_h - 6.5 * sy - 5 * sy
    w_pt, h_pt = tw / MM_PER_PT, th / MM_PER_PT
    titre = (p.get("titre_4e") or p.get("titre") or "").replace("\n", " ").strip()
    body = p.get("texte_4e") or ""

    def make(k):
        out = []
        ts = textfit.round_pt(12 * s * k)
        bs = textfit.round_pt(11 * s * k)
        if titre:
            out.append(Para([Run(titre, "arial", ts, True, False, WHITE)], align="l"))
            out.append(Para([Run("", "arial", bs, False, False, WHITE)], align="l"))
        out.extend(parse_body(body, bs, WHITE, s * k))
        return out

    spot("Texte de la 4e de couverture",
         [F("titre_4e", "Titre de la 4e (vide = même titre que la 1re)", titre), F("texte_4e", "Texte", body, True)],
         tx, ty, tw, th, family="arial", size=11 * s)
    k4, paras = _fit("Texte de la 4e de couverture", make, w_pt, h_pt, kmin=0.5)
    if body.strip():
        _small_note("Texte de la 4e de couverture", textfit.round_pt(11 * s * k4))
    if paras:
        els.append(TextBox(tx, ty, tw, th, paras, anchor="t", name="Texte 4e"))

    # auteurs (en gras, un par ligne)
    auth = lines_of(p.get("auteurs_4e")) or lines_of(p.get("auteurs"))
    auth_y = frame_y + frame_h + 4 * sy
    auth_h = 20.5 * sy
    spot("Auteurs (4e)", [F("auteurs_4e", "Auteurs de la 4e (un par ligne)", "\n".join(auth), True)],
         frame_x, auth_y, frame_w, auth_h, family="arial", size=10.5 * s)
    if auth:
        aw_pt, ah_pt = frame_w / MM_PER_PT, auth_h / MM_PER_PT

        def make_a(k):
            sz = textfit.round_pt(10.5 * s * k)
            return [_single(a, "arial", sz, WHITE, bold=True) for a in auth]

        _k, apar = _fit("Auteurs (4e de couverture)", make_a, aw_pt, ah_pt, kmin=0.6)
        els.append(TextBox(frame_x, auth_y, frame_w, auth_h, apar, anchor="t", name="Auteurs"))

    # code-barres + éditeur
    bar_w = 36.4 * sx
    bar_y = 175.8 * sy
    st, _msg = assets.isbn_status(p.get("isbn"))
    bar_h = bar_w * 0.5
    if len(assets.clean_isbn(p.get("isbn"))) == 13:
        try:
            img = assets.barcode(p.get("isbn"))
            bar_h = bar_w * img.height / img.width
            els.append(Pic(frame_x, bar_y, bar_w, bar_h, img, name="Code-barres ISBN"))
        except ValueError:
            pass
    spot("ISBN", [F("isbn", "ISBN (13 chiffres, le code-barres se fait tout seul)", p.get("isbn"))],
         frame_x, bar_y, bar_w, bar_h, family="arial", size=12 * s)
    rx = frame_x + bar_w
    rw = frame_x + frame_w - rx
    ed_ins = 1.0 * s
    eds = textfit.round_pt(13 * s)
    ed_h = 8.5 * sy
    els.append(TextBox(rx, bar_y + 0.5 * sy, rw, ed_h,
                       [_single("CMPL Éditeur", "arial", eds, WHITE, smallcaps=True, align="c")],
                       anchor="m", inset=ed_ins, name="Éditeur"))
    slogan = (p.get("slogan") or "").strip()
    spot("Slogan", [F("slogan", "Slogan", p.get("slogan"))], rx, bar_y + 10.5 * sy, rw, 7.1 * sy,
         family="arial", size=10 * s)
    if slogan:
        sw_pt = (rw - 2 * ed_ins) / MM_PER_PT
        ss = 10 * s
        while textfit.text_width_pt(slogan, "arial", ss, False, False, True) > sw_pt and ss > 5:
            ss -= 0.5
        els.append(TextBox(rx, bar_y + 10.5 * sy, rw, 7.1 * sy,
                           [_single(slogan, "arial", textfit.round_pt(ss), WHITE, smallcaps=True, align="c")],
                           anchor="m", inset=ed_ins, name="Slogan"))
    return Page("4e de couverture", W, H, bg=C, elements=els)


def a_spine(p, W, H, user_imgs):
    sx, sy, s = _s(W, H, 145.0, 210.0)
    C = p["color"]
    e = float(p.get("spine_mm") or 22)
    x = (W - e) / 2
    y_logo = 176.7 * sy
    if y_logo + e > H:
        y_logo = H - e - 2
    els = [Rect(x, 0, e, y_logo, fill=C, name="Dos"),
           Pic(x, y_logo, e, e, assets.logo(p.get("logo", "couleur"), C), name="Logo CMPL"),
           Rect(x, y_logo + e, e, H - y_logo - e, fill=C, name="Dos bas")]
    ins = 1.5
    title = " ".join(lines_of(p.get("dos_titre") or p.get("titre")))
    authors = lines_of(p.get("auteurs"))
    author = (p.get("dos_auteur") or "").strip()
    if not author:
        author = "Collectif" if len(authors) > 2 else " – ".join(authors)
    base = max(6.0, SPINE_SCALE * min(28 * s, max(8.0, e * 1.27)))
    ratio = 16.0 / 28.0
    top = 7 * sy
    length_avail = y_logo - top - 6 * sy

    # zone auteur (haut) puis titre centré dans le reste
    asz = textfit.round_pt(base * ratio)
    az_mm = 0.0
    if author:
        max_a = length_avail * 0.45
        while textfit.text_width_pt(author, "arial", asz, False, False, True) * MM_PER_PT + 2 * ins > max_a and asz > 6:
            asz -= 0.5
        az_mm = textfit.text_width_pt(author, "arial", asz, False, False, True) * MM_PER_PT + 2 * ins + 3
        els.append(TextBox(x, top, e, az_mm, [_single(author, "arial", asz, WHITE, smallcaps=True, align="r")], anchor="m", rot=270,
                           inset=ins, name="Auteur (dos)"))
        if textfit.text_width_pt(author, "arial", asz, False, False, True) * MM_PER_PT + 2 * ins > max_a + 0.01:
            note("error", "Auteur du dos : trop long pour la hauteur du dos.")
    spot("Auteur du dos", [F("dos_auteur", "Auteur du dos", author)], x, top, e, az_mm if author else 25.0 * sy,
         rot=270, family="arial", size=asz)
    t_y0 = top + az_mm + (4 * sy if author else 0)
    t_len = y_logo - 5 * sy - t_y0
    spot("Titre du dos", [F("dos_titre", "Titre du dos", title)], x, t_y0, e, t_len, rot=270, family="arial",
         size=textfit.round_pt(base))
    if title:
        tsz = textfit.round_pt(base)
        while textfit.text_width_pt(title, "arial", tsz, False, False, True) * MM_PER_PT + 2 * ins > t_len and tsz > 6:
            tsz -= 0.5
        els.append(TextBox(x, t_y0, e, t_len, [_single(title, "arial", tsz, WHITE, smallcaps=True, align="c")], anchor="m", rot=270,
                           inset=ins, name="Titre (dos)"))
        if textfit.text_width_pt(title, "arial", tsz, False, False, True) * MM_PER_PT + 2 * ins > t_len + 0.01:
            note("error", "Titre du dos : trop long pour la hauteur du dos (raccourcis-le dans « Titre du dos »).")
        elif tsz < 0.75 * textfit.round_pt(base):
            note("warn", f"Titre du dos : réduit à {tsz:g} pt pour tenir (raccourcis-le dans « Titre du dos »).")
    if e < 6:
        note("warn", f"Dos très fin ({e:g} mm) : le texte du dos sera difficile à lire.")
    return Page("Dos", W, H, bg=WHITE, elements=els, crop=(x, 0, x + e, H))


# ------------------------------------------------------------------ type B

def _b_strip(els, p, W, H, sx, sy, s, side):
    accent = p["color"]
    line_w = 0.7 * s
    brush_w = 8.4 * sx
    margin = 5.8 * sx
    h = 170 * sy
    if side == "left":
        lx = margin
        bx = lx + line_w
        flip = False
    else:
        bx = W - margin - line_w - brush_w
        lx = bx + brush_w
        flip = True
    els.append(Pic(bx, 0, brush_w, h, assets.pinceau(accent, flip=flip), name="Pinceau", bleed="t"))
    els.append(Rect(lx, 0, line_w, h, fill=BLACK, name="Trait noir", bleed="t"))
    return bx


def b_front(p, W, H, user_imgs):
    sx, sy, s = _s(W, H, 114.0, 178.0)
    accent = p["color"]
    ink = colors.ink(accent)         # teinte du titre et de l'image : plus foncée si la couleur est claire
    els = []
    _b_strip(els, p, W, H, sx, sy, s, "left")
    R = W - 6 * sx
    box_x = 12 * sx
    box_w = R - box_x
    ins = 2.0 * s
    w_pt = (box_w - 2 * ins) / MM_PER_PT

    # auteur
    auteur = " ".join(lines_of(p.get("auteur")))
    spot("Auteur", [F("auteur", "Auteur", p.get("auteur"))], box_x, 9.8 * sy, box_w, 9.7 * sy, family="bkant", size=18 * s)
    if auteur:
        sz = 18 * s
        while textfit.text_width_pt(auteur, "bkant", sz, False, False) > w_pt and sz > 8:
            sz -= 0.5
        if textfit.text_width_pt(auteur, "bkant", sz, False, False) > w_pt:
            note("error", "Nom de l'auteur : trop long pour la 1re de couverture.")
        elif sz < 0.8 * 18 * s:
            note("warn", f"Nom de l'auteur : réduit à {textfit.round_pt(sz):g} pt pour tenir.")
        els.append(TextBox(box_x, 9.8 * sy, box_w, 9.7 * sy,
                           [_single(auteur, "bkant", textfit.round_pt(sz), BLACK, align="r")],
                           anchor="t", inset=ins, name="Auteur"))

    # titre
    titre = (p.get("titre") or "").strip()
    frame_w = 90.6 * sx
    frame_x = R - frame_w
    frame_y = 63.9 * sy
    t_top = 28.8 * sy
    t_h = frame_y - t_top - 2 * sy
    spot("Titre", [F("titre", "Titre", p.get("titre"), True)], box_x, t_top, box_w, t_h, family="times", size=28 * s)
    if titre:
        def make(k):
            sz = textfit.round_pt(28 * s * k)
            return [Para([Run(l, "times", sz, False, False, ink)], align="r") for l in lines_of(titre)]

        _k, paras = _fit("Titre", make, w_pt, (t_h - 2 * ins) / MM_PER_PT, kmin=0.4)
        paras = explode_lines(paras, w_pt)
        els.append(TextBox(box_x, t_top, box_w, t_h, paras, anchor="t", inset=ins, name="Titre"))

    # cadre + illustration
    frame_h = 66.1 * sy
    els.append(Pic(frame_x, frame_y, frame_w, frame_h, assets.cadre_illustration(accent), name="Cadre illustration"))
    img = user_imgs.get(p.get("illustration"))
    if img is not None:
        if p.get("ill_tint", True):
            img = assets.tint(img, ink)
        bx, by = frame_x + 13.9 * sx, frame_y + 9.4 * sy
        bw, bh = 62.5 * sx, 47.3 * sy
        pic, info = _place_in_box(img, bx, by, bw, bh, p.get("ill_zoom") or 1.0,
                                  p.get("ill_x", 0.5), p.get("ill_y", 0.5))
        els.append(pic)
        info.update(x=bx / W, y=by / H, w=bw / W, h=bh / H, W=W, H=H)
        last_notes().hot["ill"] = info
        if info["dpi"] < 200:
            note("warn" if info["dpi"] >= 120 else "error",
                 f"Illustration : image peu définie ({round(info['dpi'])} dpi à cette taille), "
                 "elle risque d'être floue à l'impression (300 dpi conseillé).")

    maison = (p.get("maison") or "").strip()
    spot("Maison d'édition", [F("maison", "Maison d'édition", p.get("maison"))], 55.1 * sx, 159.7 * sy,
         R - 55.1 * sx, 10.3 * sy, family="bkant", size=18 * s)
    if maison:
        sz = 18 * s
        while textfit.text_width_pt(maison, "bkant", sz, False, False) > w_pt and sz > 8:
            sz -= 0.5
        if textfit.text_width_pt(maison, "bkant", sz, False, False) > w_pt:
            note("error", "Maison d'édition : texte trop long.")
        els.append(TextBox(55.1 * sx, 159.7 * sy, R - 55.1 * sx, 10.3 * sy,
                           [_single(maison, "bkant", textfit.round_pt(sz), BLACK, align="r")],
                           anchor="t", inset=ins, name="Maison d'édition"))
    return Page("1re de couverture", W, H, bg=WHITE, elements=els)


def b_back(p, W, H, user_imgs):
    sx, sy, s = _s(W, H, 114.0, 178.0)
    accent = p["color"]
    els = []
    bx = _b_strip(els, p, W, H, sx, sy, s, "right")
    left = 7 * sx
    width = 87.3 * sx
    ins = 0.0
    w_pt = width / MM_PER_PT

    head = lines_of(p.get("auteur_4e")) or lines_of(p.get("auteur"))
    y = 10 * sy
    head_top = y
    if head:
        sz = 18 * s
        while max(textfit.text_width_pt(l, "bkant", sz, False, False) for l in head) > w_pt and sz > 8:
            sz -= 0.5
        if max(textfit.text_width_pt(l, "bkant", sz, False, False) for l in head) > w_pt:
            note("error", "Auteur / sous-titre de la 4e : ligne trop longue.")
        paras = [_single(l, "bkant", textfit.round_pt(sz), BLACK) for l in head]
        h_mm = textfit.total_height(paras, w_pt) * MM_PER_PT
        els.append(TextBox(left, y, width, h_mm, paras, anchor="t", name="Auteur / titre"))
        y += h_mm + 3 * sy
    else:
        y = 32.9 * sy
    spot("Auteur / sous-titre", [F("auteur_4e", "Lignes du haut de la 4e (auteur, sous-titre…)", "\n".join(head), True)],
         left, head_top, width, max(y - 3 * sy - head_top, 14 * sy), family="bkant", size=18 * s)

    body_bottom = 120 * sy
    body = p.get("texte_4e") or ""
    spot("Texte de la 4e de couverture", [F("texte_4e", "Texte de la 4e", body, True)], left, y, width,
         body_bottom - y, family="times", size=11 * s)
    if body.strip():
        def make(k):
            sz = textfit.round_pt(11 * s * k)
            return [Para([Run(l.strip(), "times", sz, False, False, BLACK)], align="j", first_mm=3.5 * s)
                    for l in body.replace("\r", "").split("\n") if l.strip()]

        k4, paras = _fit("Texte de la 4e de couverture", make, w_pt, (body_bottom - y) / MM_PER_PT, kmin=0.6)
        _small_note("Texte de la 4e de couverture", textfit.round_pt(11 * s * k4))
        els.append(TextBox(left, y, width, body_bottom - y, paras, anchor="t", name="Texte 4e"))

    # logo rond d'angle
    rsize = 53 * s
    mode = p.get("logo_rond", "defaut")
    rimg = None
    if mode == "defaut":
        rimg = assets.logo_rond(accent)
    elif mode in user_imgs:
        rimg = user_imgs[mode]
    if rimg is not None:
        w, h = _contain(rimg, rsize, rsize)
        els.append(Pic(0.1 * sx, H - h, w, h, rimg, name="Logo rond", fmt="AUTO", bleed="lb"))
    # logo CMPL
    lsize = 22 * s
    els.append(Pic(bx - lsize, 151.5 * sy, lsize, lsize, assets.logo(p.get("logo", "mono"), accent), name="Logo CMPL"))
    return Page("4e de couverture", W, H, bg=WHITE, elements=els)


def b_spine(p, W, H, user_imgs):
    sx, sy, s = _s(W, H, 114.0, 178.0)
    accent = p["color"]
    e = float(p.get("spine_mm") or 9)
    x = (W - e) / 2
    h = 168.5 * sy
    els = [Pic(x, 0, e, h, assets.pinceau(accent), name="Pinceau (dos)", bleed="t")]
    title = " ".join(lines_of(p.get("dos_titre") or p.get("titre")))
    author = (p.get("dos_auteur") or "").strip()
    base = max(5.0, SPINE_SCALE * min(16 * s, max(6.0, e * 1.8)))
    ins = 0.5
    top, bottom = 12 * sy, h - 12 * sy
    length = bottom - top - 2 * ins
    spot("Dos", [F("dos_titre", "Titre du dos", title), F("dos_auteur", "Auteur du dos", author)],
         x, top, e, bottom - top, rot=270, family="arial", size=textfit.round_pt(base))

    def make(k):
        sz = textfit.round_pt(base * k)
        runs = [Run("CMPL", "arial", sz, False, False, BLACK, True)]
        if title:
            runs += [Run(" – ", "arial", sz, False, False, BLACK, True),
                     Run(title, "arial", sz, True, False, BLACK, True)]
        if author:
            runs += [Run(" – ", "arial", sz, False, False, BLACK, True),
                     Run(author, "arial", sz, False, False, BLACK, True)]
        return [Para(runs, align="c")]

    k = 1.0
    while True:
        paras = make(k)
        wd = sum(textfit.run_width(r) for r in paras[0].runs) * MM_PER_PT
        if wd <= length or k <= 0.3:
            break
        k -= 0.02
    _shrink_note("Texte du dos", k, wd <= length, 0.75)
    if e < 6:
        note("warn", f"Dos très fin ({e:g} mm) : le texte du dos sera difficile à lire.")
    els.append(TextBox(x, top, e, bottom - top, paras, anchor="m", rot=270, inset=ins, name="Texte du dos"))
    return Page("Dos", W, H, bg=WHITE, elements=els, crop=(x, 0, x + e, H))


BUILDERS = {
    "A": {"1re": a_front, "4e": a_back, "dos": a_spine},
    "B": {"1re": b_front, "4e": b_back, "dos": b_spine},
}


def build_pages(p, user_imgs=None):
    """Retourne la liste des 3 pages (1re, 4e, dos) pour les paramètres p."""
    user_imgs = user_imgs or {}
    _tl.n = Notes()
    W, H, _ = FORMATS[p["format"]]
    kind = p.get("type", "A")
    pages = []
    for i, f in enumerate(("1re", "4e", "dos")):
        _tl.face = i
        pages.append(BUILDERS[kind][f](p, W, H, user_imgs))
    last_notes().hot["texts"] = _spots_to_fractions(pages)
    return pages
