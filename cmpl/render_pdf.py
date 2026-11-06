"""PDF d'une page image : sans perte (Flate), à la taille réelle, avec TrimBox et BleedBox pour l'imprimeur."""
import zlib

PT_PER_MM = 72.0 / 25.4


def write_pdf(img, path, dpi, trim_mm=None, bleed_mm=None, title="Couverture CMPL"):
    """img : image PIL RGB. trim_mm / bleed_mm : (x, y, w, h) en mm depuis le coin haut-gauche de la page."""
    img = img.convert("RGB")
    w_px, h_px = img.size
    w_pt, h_pt = w_px / dpi * 72.0, h_px / dpi * 72.0
    data = zlib.compress(img.tobytes(), 6)

    def box(b):
        x, y, w, h = [v * PT_PER_MM for v in b]
        return f"[{x:.3f} {h_pt - y - h:.3f} {x + w:.3f} {h_pt - y:.3f}]"

    boxes = ""
    if trim_mm:
        boxes += f" /TrimBox {box(trim_mm)}"
    if bleed_mm:
        boxes += f" /BleedBox {box(bleed_mm)}"
    content = f"q {w_pt:.3f} 0 0 {h_pt:.3f} 0 0 cm /Im0 Do Q".encode("ascii")
    safe_title = "".join(c if ord(c) < 128 and c not in "()\\" else "?" for c in title)

    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.3f} {h_pt:.3f}]{boxes} "
         f"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>").encode("ascii"))
    objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    objs.append((f"<< /Type /XObject /Subtype /Image /Width {w_px} /Height {h_px} /ColorSpace /DeviceRGB "
                 f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(data)} >>\nstream\n").encode("ascii")
                + data + b"\nendstream")
    objs.append(f"<< /Title ({safe_title}) /Producer (Couvertures CMPL) >>".encode("ascii"))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as fh:
        fh.write(out)
