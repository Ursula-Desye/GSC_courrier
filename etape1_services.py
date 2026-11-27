r"""
GSC - ETAPE 1 : creer tous les services du fichier SUIVI_COURRIER.xlsx

A placer dans D:\Downloads\GSC puis :  python etape1_services.py [fichier.xlsx]
Lit l'onglet "Parametres" (colonne SERVICES) et cree chaque structure.
Ne supprime ni ne modifie rien d'existant. Peut etre relance sans risque.
"""
from pathlib import Path
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

DIRECTIONS = {"DG", "DGA_CM", "DGA_SP", "DF"}   # les autres : Departement

fichier = sys.argv[1] if len(sys.argv) > 1 else "SUIVI_COURRIER.xlsx"
if not Path(fichier).exists():
    raise SystemExit(f"Fichier introuvable : {fichier}")

import django
django.setup()
import openpyxl
from courrier.models import Service

classeur = openpyxl.load_workbook(fichier, read_only=True, data_only=True)
feuille = next((classeur[n] for n in classeur.sheetnames if n.lower().startswith("param")), None)
if feuille is None:
    raise SystemExit("Onglet 'Parametres' introuvable dans le fichier.")

noms = []
for ligne in feuille.iter_rows(min_row=1, max_row=60, min_col=2, max_col=14, values_only=True):
    if ligne[1] and str(ligne[1]).strip().upper() != "SERVICES":
        noms.append(" ".join(str(ligne[1]).split()))

print(f"{len(noms)} services trouves dans le fichier\n")
crees = 0
for nom in noms:
    type_structure = "DIRECTION" if nom in DIRECTIONS else "DEPARTEMENT"
    service, cree = Service.objects.get_or_create(
        nom=nom,
        defaults={
            "type_structure": type_structure,
            "description": "Cree depuis le fichier SUIVI_COURRIER.xlsx",
            "actif": True,
        },
    )
    crees += cree
    print(f"  [{'CREE' if cree else 'EXISTE DEJA'}] {nom} ({service.get_type_structure_display()})")

print(f"\nTermine : {crees} service(s) cree(s), {len(noms) - crees} deja present(s).")
print("Etape suivante : verifier PERSONNEL_A_VERIFIER.xlsx puis lancer ETAPE2_PERSONNEL.bat")
