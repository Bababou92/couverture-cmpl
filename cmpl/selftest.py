"""Auto-test du programme empaqueté : `Couvertures CMPL.exe --selftest résultat.txt`.
Génère les deux exemples (aperçus, PNG, PPTX, PDF à plat) dans un dossier temporaire et écrit OK ou l'erreur."""
import os
import tempfile
import traceback


def run(out_path):
    try:
        from . import defaults, server
        server.load_builtin_images()
        with tempfile.TemporaryDirectory() as tmp:
            for kind, ex in (("A", defaults.EXAMPLE_A), ("B", defaults.EXAMPLE_B)):
                r = server.preview(dict(ex), 80, 3)
                assert len(r["faces"]) == 4, f"aperçu {kind} incomplet"
                files = server.generate(dict(ex), os.path.join(tmp, kind), "test" + kind, True, True, 100, True, 3, True)
                for f in files:
                    assert os.path.getsize(f) > 1000, f"fichier vide : {f}"
                assert any(f.endswith(".pptx") for f in files) and any(f.endswith(".pdf") for f in files)
        from . import version
        text = "OK " + version.VERSION
    except Exception:
        text = "ECHEC\n" + traceback.format_exc()
    with open(out_path, "w", encoding="utf8") as fh:
        fh.write(text)
    return text.startswith("OK")
