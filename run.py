"""Lance le générateur de couvertures CMPL (ouvre l'interface dans le navigateur)."""
import os
import sys

# Version « sans console » (exe) : pas de sortie standard, on évite les erreurs d'affichage
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from cmpl.server import main

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from cmpl import selftest
        i = sys.argv.index("--selftest")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else "selftest.txt"
        sys.exit(0 if selftest.run(out) else 1)
    # --relance : démarrage juste après une mise à jour (l'onglet déjà ouvert se recharge tout seul)
    main(open_browser="--no-browser" not in sys.argv and "--relance" not in sys.argv,
         relance="--relance" in sys.argv)
