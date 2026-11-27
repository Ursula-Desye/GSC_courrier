r"""
GSC - Correction du "retour au Secretariat" (403 apres confirmation)
et autorisation de l'Accueil pour enregistrer un courrier retourne.

A placer dans D:\Downloads\GSC puis lancer :  python corriger_retour.py
Une copie de securite courrier\views.py.bak est creee.
"""
from pathlib import Path
import shutil
import sys

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
vues = base / "courrier" / "views.py"

if not vues.exists():
    raise SystemExit(f"Fichier introuvable : {vues}")

brut = vues.read_bytes().decode("utf-8")
crlf = "\r\n" in brut
texte = brut.replace("\r\n", "\n")

CORRECTIONS = [
    (
        # 1. Apres un retour, le courrier quitte le perimetre du responsable :
        #    on ne doit pas le rediriger vers la fiche (403) mais vers la liste.
        '''            messages.success(
                request,
                "Le courrier a été retourné au Secrétariat.",
            )
            return redirect("detail_courrier", pk=obj.pk)''',
        '''            messages.success(
                request,
                "Le courrier a été retourné à l'Accueil / au Secrétariat.",
            )
            return redirect("liste_courriers")''',
    ),
    (
        # 2. L'Accueil peut aussi enregistrer un courrier retourne.
        '''                if obtenir_profil(request.user) != "SECRETARIAT":
                    raise PermissionDenied(
                        "Seul le Secrétariat peut enregistrer "
                        "un courrier retourné."
                    )''',
        '''                if obtenir_profil(request.user) not in [
                    "ACCUEIL",
                    "SECRETARIAT",
                ]:
                    raise PermissionDenied(
                        "Seuls l'Accueil et le Secrétariat peuvent "
                        "enregistrer un courrier retourné."
                    )''',
    ),
]

for ancien, nouveau in CORRECTIONS:
    n = texte.count(ancien)
    if n == 0 and nouveau in texte:
        print("[DEJA FAIT] une correction etait deja appliquee")
        continue
    if n != 1:
        raise SystemExit(
            f"[ARRET] Texte attendu trouve {n} fois (1 attendu). "
            "Aucun fichier modifie. Envoyez-moi views.py."
        )

if any(texte.count(a) == 1 for a, _ in CORRECTIONS):
    shutil.copy2(vues, vues.with_name("views.py.bak"))
    for ancien, nouveau in CORRECTIONS:
        texte = texte.replace(ancien, nouveau)
    if crlf:
        texte = texte.replace("\n", "\r\n")
    vues.write_bytes(texte.encode("utf-8"))
    print("[OK] courrier/views.py corrige (sauvegarde : views.py.bak)")
else:
    print("[OK] Rien a faire")
