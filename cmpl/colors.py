"""Contraste et teinte « encre » (version foncée d'une couleur trop claire pour du texte sur fond blanc)."""
import colorsys


def _rgb(hexv):
    h = hexv.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(hexv):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hexv)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ink(hexv, min_ratio=3.0, target=4.5, bg="#FFFFFF"):
    """La couleur elle-même si elle se lit bien sur le fond, sinon la même teinte assombrie."""
    hexv = "#" + hexv.lstrip("#").upper()
    if contrast(hexv, bg) >= min_ratio:
        return hexv
    r, g, b = [c / 255.0 for c in _rgb(hexv)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    while l > 0.05:
        l -= 0.01
        rr, gg, bb = colorsys.hls_to_rgb(h, l, s)
        cand = "#%02X%02X%02X" % (round(rr * 255), round(gg * 255), round(bb * 255))
        if contrast(cand, bg) >= target:
            return cand
    return cand
