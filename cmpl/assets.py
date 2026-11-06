"""Images embarquées : logos, pinceau, cadre ; recoloration ; code-barres EAN-13."""
import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from . import fonts

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=None)
def _load(name):
    return Image.open(os.path.join(ASSETS, name))


def _tint_on_white(coverage, rgb):
    """coverage (H,W) 0..1 -> image RGB : blanc + couleur proportionnelle."""
    cov = np.clip(coverage, 0, 1)[..., None]
    base = np.array(rgb, dtype=float)[None, None, :]
    out = 255.0 - cov * (255.0 - base)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype("uint8"), "RGB")


def _coverage_green(img, ref_green):
    g = np.array(img.convert("RGB"))[..., 1].astype(float)
    return (255.0 - g) / max(255.0 - ref_green, 1.0)


# ---------------------------------------------------------------- logos

@lru_cache(maxsize=None)
def logo(variant, color_hex="#294364"):
    """Logo CMPL Éditeur sur fond blanc, carré.

    variant : 'couleur' (rouge/bleu d'origine), 'noir', 'mono' (une seule couleur = color_hex)
    """
    if variant == "couleur":
        return _load("logo_couleur.png").convert("RGB")
    base = _load("logo_noir.png").convert("RGB")
    arr = np.array(base).astype(float)
    lum = arr.mean(axis=2)
    bg, dark = 253.0, 37.0
    cov = (bg - lum) / (bg - dark)
    rgb = (0, 0, 0) if variant == "noir" else hex_to_rgb(color_hex)
    if variant == "noir":
        rgb = (35, 38, 40)
    return _tint_on_white(cov, rgb)


@lru_cache(maxsize=None)
def logo_rond(color_hex):
    img = _load("logo_rond_taka.png").convert("RGB")
    return _tint_on_white(_coverage_green(img, 58.0), hex_to_rgb(color_hex))


@lru_cache(maxsize=None)
def cadre_illustration(color_hex):
    img = _load("cadre_illustration.png").convert("RGB")
    return _tint_on_white(_coverage_green(img, 58.0), hex_to_rgb(color_hex))


@lru_cache(maxsize=None)
def pinceau(color_hex, flip=False, scale=3):
    """Bande « coup de pinceau » recolorée (sans le trait noir d'origine)."""
    img = _load("pinceau_dos.png").convert("RGB")
    cov = _coverage_green(img, 58.0)
    out = _tint_on_white(cov, hex_to_rgb(color_hex))
    out = out.resize((out.width * scale, out.height * scale), Image.LANCZOS)
    if flip:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    return out


def recolor_user_logo(img, color_hex):
    """Recolore un logo rond importé (fond blanc, dessin sombre) avec la couleur du livre."""
    arr = np.array(img.convert("RGB")).astype(float)
    lum = arr.mean(axis=2)
    cov = (255.0 - lum) / 255.0
    cov = np.clip(cov * 1.15, 0, 1)
    return _tint_on_white(cov, hex_to_rgb(color_hex))


# ---------------------------------------------------------------- EAN-13

_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
_G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
_R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def clean_isbn(s):
    return re.sub(r"[^0-9Xx]", "", s or "")


def isbn_status(s):
    """('ok'|'vide'|'invalide', message)"""
    d = clean_isbn(s)
    if not d:
        return "vide", ""
    if len(d) != 13 or not d.isdigit():
        return "invalide", "L'ISBN doit comporter 13 chiffres."
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12]))
    check = (10 - total % 10) % 10
    if check != int(d[12]):
        return "invalide", f"Clé de contrôle ISBN incorrecte (attendu : {check})."
    return "ok", ""


def format_isbn(d):
    """978-2-494268-20-3 (affichage) : on garde la saisie de l'utilisateur si elle contient des tirets."""
    return d


@lru_cache(maxsize=None)
def barcode(isbn_text, dpi_scale=1):
    """Image du code-barres EAN-13 avec ISBN au-dessus et chiffres dessous (fond blanc, ratio ~2:1)."""
    digits = clean_isbn(isbn_text)
    if len(digits) != 13 or not digits.isdigit():
        raise ValueError("ISBN invalide")
    first = int(digits[0])
    pattern = "101"
    for i, ch in enumerate(digits[1:7]):
        pattern += (_L if _PARITY[first][i] == "L" else _G)[int(ch)]
    pattern += "01010"
    for ch in digits[7:]:
        pattern += _R[int(ch)]
    pattern += "101"

    mod = 6 * dpi_scale                    # largeur d'un module en px
    quiet = 11 * mod
    width = quiet * 2 + len(pattern) * mod
    height = int(width * 0.5)
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    top = int(height * 0.17)
    bar_bottom = int(height * 0.80)
    guard_bottom = int(height * 0.86)
    guards = set(range(0, 3)) | set(range(45, 50)) | set(range(92, 95))
    for i, bit in enumerate(pattern):
        if bit == "1":
            x0 = quiet + i * mod
            bottom = guard_bottom if i in guards else bar_bottom
            d.rectangle([x0, top, x0 + mod - 1, bottom], fill="black")
    # textes
    fpath = fonts.resolve("mono", False, False)
    f_small = fonts.pil_font(fpath, max(8, int(height * 0.095)))
    label = "ISBN: " + _hyphen_label(isbn_text, digits)
    d.text((width / 2, int(height * 0.085)), label, font=f_small, fill="black", anchor="mm")
    f_dig = fonts.pil_font(fonts.resolve("arial", False, False), max(10, int(height * 0.15)))
    y_txt = int(height * 0.93)
    d.text((quiet - mod * 1.5, y_txt), digits[0], font=f_dig, fill="black", anchor="rm")
    left_center = quiet + (3 + 21) * mod
    right_center = quiet + (50 + 21) * mod
    d.text((left_center, y_txt), digits[1:7], font=f_dig, fill="black", anchor="mm")
    d.text((right_center, y_txt), digits[7:], font=f_dig, fill="black", anchor="mm")
    return img


def _hyphen_label(raw, digits):
    if "-" in (raw or ""):
        return raw.strip()
    return f"{digits[:3]}-{digits[3]}-{digits[4:10]}-{digits[10:12]}-{digits[12]}"


_TINTED = {}


def tint(img, color_hex):
    """Illustration monochrome : les zones sombres prennent la couleur, les claires deviennent transparentes."""
    key = (id(img), img.size, color_hex)
    hit = _TINTED.get(key)
    if hit is not None and hit[0] is img:
        return hit[1]
    out = _tint(img, color_hex)
    if len(_TINTED) >= 8:
        _TINTED.pop(next(iter(_TINTED)))
    _TINTED[key] = (img, out)
    return out


def _tint(img, color_hex):
    rgba = img.convert("RGBA")
    if max(rgba.size) > 2400:
        rgba.thumbnail((2400, 2400), Image.LANCZOS)
    a = np.asarray(rgba, dtype=np.float32)
    alpha = a[..., 3] / 255.0
    lum = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]) / 255.0
    opaque = alpha > 0.5
    if opaque.any():
        lo, hi = np.percentile(lum[opaque], [1, 99])
    else:
        lo, hi = 0.0, 1.0
    if hi - lo < 0.02:                       # image unie : on garde sa forme
        cov = np.where(lum < 0.98, 1.0, 0.0).astype(np.float32) if hi > 0.9 else np.ones_like(lum)
    else:
        cov = np.clip((hi - lum) / (hi - lo), 0.0, 1.0)
        cov = np.clip((cov - 0.07) / 0.93, 0.0, 1.0)      # écarte le voile gris du fond (JPEG, papier)
    r, g, b = hex_to_rgb(color_hex)
    out = np.zeros(a.shape, dtype=np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = r, g, b
    out[..., 3] = np.round(255 * cov * alpha).astype(np.uint8)
    return Image.fromarray(out, "RGBA")
