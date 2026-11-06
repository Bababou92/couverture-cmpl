"""Couverture à plat : 4e + dos + 1re assemblés, avec fonds perdus et traits de coupe optionnels."""
from dataclasses import replace

from .layout import Page, Pic, Rect, TextBox

BLACK = "#000000"


def _shift(el, dx, dy, bleed):
    el = replace(el, x=el.x + dx, y=el.y + dy)
    flags = getattr(el, "bleed", "")
    if flags:
        if "l" in flags:
            el = replace(el, x=el.x - bleed, w=el.w + bleed)
        if "r" in flags:
            el = replace(el, w=el.w + bleed)
        if "t" in flags:
            el = replace(el, y=el.y - bleed, h=el.h + bleed)
        if "b" in flags:
            el = replace(el, h=el.h + bleed)
    return el


def compose(pages, bleed=3.0, marks=False):
    """pages = [1re, 4e, dos]. Retourne (page à plat, infos en mm).

    infos : sheet (x, y, w, h) = feuille avec fonds perdus, trim (x, y, w, h) = format fini,
    folds = abscisses des deux plis du dos, spine = épaisseur du dos.
    """
    front, back, spine = pages
    W, H = front.w, front.h
    x0, _y0, x1, _y1 = spine.crop
    e = x1 - x0
    slug = 9.0 if marks else 0.0
    sheet_w, sheet_h = 2 * W + e + 2 * bleed, H + 2 * bleed
    page = Page("Couverture à plat", sheet_w + 2 * slug, sheet_h + 2 * slug, bg="#FFFFFF")
    off = slug + bleed
    els = [Rect(slug, slug, sheet_w, sheet_h, fill=front.bg, name="Fond")]
    for el in back.elements:
        els.append(_shift(el, off, off, bleed))
    for el in spine.elements:
        els.append(_shift(el, off + W - x0, off, bleed))
    for el in front.elements:
        els.append(_shift(el, off + W + e, off, bleed))

    trim = (off, off, 2 * W + e, H)
    folds = (off + W, off + W + e)
    if marks:
        t = 0.1       # épaisseur des traits (mm)
        L = 4.0       # longueur
        gap = bleed + 1.0
        tx0, ty0, tx1, ty1 = trim[0], trim[1], trim[0] + trim[2], trim[1] + trim[3]
        for cx, cy in ((tx0, ty0), (tx1, ty0), (tx0, ty1), (tx1, ty1)):
            sx = -1 if cx == tx0 else 1
            sy = -1 if cy == ty0 else 1
            hx = cx + sx * gap if sx > 0 else cx - gap - L
            els.append(Rect(hx, cy - t / 2, L, t, fill=BLACK, name="Trait de coupe"))
            vy = cy + sy * gap if sy > 0 else cy - gap - L
            els.append(Rect(cx - t / 2, vy, t, L, fill=BLACK, name="Trait de coupe"))
        for fx in folds:
            els.append(Rect(fx - t / 2, ty0 - gap - L, t, L, fill=BLACK, name="Trait de pli"))
            els.append(Rect(fx - t / 2, ty1 + gap, t, L, fill=BLACK, name="Trait de pli"))
    page.elements = els
    info = {"sheet": (slug, slug, sheet_w, sheet_h), "trim": trim, "folds": folds, "spine": e, "slug": slug,
            "bleed": bleed}
    return page, info
