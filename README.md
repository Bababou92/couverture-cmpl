# Générateur de couvertures CMPL

Programme (interface dans le navigateur, tout reste sur l'ordinateur) qui fabrique les couvertures de livres
CMPL Éditeur : 1re, 4e de couverture et dos, en images PNG, PowerPoint modifiable et PDF à plat pour l'imprimeur.

- **Utilisateur** : télécharger `Couvertures-CMPL.exe` dans [Releases](../../releases/latest) et double-cliquer.
  Le programme propose ensuite lui-même les mises à jour.
- Mode d'emploi détaillé : [LIRE-MOI.txt](LIRE-MOI.txt)

## Publier une nouvelle version

1. Modifier `NOTES.txt` (une ou deux lignes sur les nouveautés).
2. `git tag v1.1.0 && git push origin v1.1.0`
3. GitHub Actions construit l'exe sur Windows, le teste, puis le publie dans *Releases* avec `latest.json`.
   Les PC qui ont le programme verront « Nouvelle version disponible » au prochain lancement.

## Développement

```
pip install -r requirements.txt
python run.py            # ouvre http://127.0.0.1:8765/
python run.py --selftest resultat.txt   # génère les exemples et écrit OK
```
