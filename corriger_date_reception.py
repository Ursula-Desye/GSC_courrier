r"""
GSC - Correction de l'erreur a l'enregistrement d'un courrier :
"Impossible d'inserer la valeur NULL dans la colonne 'date_reception_expedition'"

A placer dans D:\Downloads\GSC puis lancer :  python corriger_date_reception.py
Si la date de reception n'est pas saisie, elle prend la date du courrier.
Une copie de securite courrier\forms.py.bak est creee.
"""
from pathlib import Path
import shutil
import sys

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
p = base / "courrier" / "forms.py"
if not p.exists():
    raise SystemExit(f"Fichier introuvable : {p}")

brut = p.read_bytes().decode("utf-8")
crlf = "\r\n" in brut
texte = brut.replace("\r\n", "\n")

ANCIEN = '''        cleaned_data = super().clean()

        sens = cleaned_data.get("sens")
        confidentialite = cleaned_data.get("confidentialite")
'''
NOUVEAU = '''        cleaned_data = super().clean()

        # La date de reception est facultative dans le formulaire mais
        # obligatoire en base : a defaut, on reprend la date du courrier.
        if not cleaned_data.get("date_reception_expedition"):
            cleaned_data["date_reception_expedition"] = (
                cleaned_data.get("date_courrier") or timezone.localdate()
            )

        sens = cleaned_data.get("sens")
        confidentialite = cleaned_data.get("confidentialite")
'''

if "La date de reception est facultative" in texte:
    raise SystemExit("[DEJA FAIT] la correction est deja appliquee")
n = texte.count(ANCIEN)
if n != 1:
    raise SystemExit(f"[ARRET] point d'insertion trouve {n} fois (1 attendu). Rien modifie : envoyez-moi forms.py.")

shutil.copy2(p, p.with_name("forms.py.bak"))
texte = texte.replace(ANCIEN, NOUVEAU)
if crlf:
    texte = texte.replace("\n", "\r\n")
p.write_bytes(texte.encode("utf-8"))
print("[OK] courrier/forms.py corrige (sauvegarde : forms.py.bak)")
