r"""
GSC - FINALISATION AUTOMATIQUE

A placer dans D:\Downloads\GSC (a cote de manage.py), puis lancer :
    python finaliser_gsc.py
Les mots de passe appliques sont ceux du fichier IDENTIFIANTS_GSC.txt
(y compris admin_gsc).

Ce script :
 1. corrige le bug de l'export PDF (variable "table" -> "tableau")
 2. remplace la cle secrete placeholder du fichier .env
 3. configure les droits COMPLETS de chaque groupe
 4. cree les categories de courrier si aucune n'existe
 5. reinitialise les mots de passe des comptes de test
 6. ecrit le bloc-notes IDENTIFIANTS_GSC.txt
 7. lance un test de fonctionnement avec chaque profil

Aucune donnee de courrier n'est modifiee ou supprimee.
"""
from pathlib import Path
import os
import re
import secrets
import shutil
import sys
import traceback
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

AVEC_ADMIN = "--avec-admin" in sys.argv


def etape(titre):
    print("\n" + "-" * 72)
    print(titre)
    print("-" * 72)


# ---------------------------------------------------------------
# 1. Correction de l'export PDF
# ---------------------------------------------------------------
etape("1. CORRECTION DE L'EXPORT PDF")
exports = BASE_DIR / "courrier" / "exports.py"
if exports.exists():
    source = exports.read_text(encoding="utf-8")
    if "elements.append(table)" in source:
        shutil.copy2(exports, exports.with_name("exports.py.bak"))
        exports.write_text(
            source.replace("elements.append(table)", "elements.append(tableau)"),
            encoding="utf-8",
        )
        print("[CORRIGE] elements.append(table) -> elements.append(tableau)")
        print("          sauvegarde : courrier/exports.py.bak")
    else:
        print("[OK] Rien a corriger dans exports.py")
else:
    print("[ATTENTION] courrier/exports.py introuvable")

# ---------------------------------------------------------------
# 2. Cle secrete Django
# ---------------------------------------------------------------
etape("2. FICHIER .env")
env = BASE_DIR / ".env"
if env.exists():
    texte = env.read_text(encoding="utf-8")
    if "DJANGO_SECRET_KEY=change-moi" in texte:
        shutil.copy2(env, BASE_DIR / ".env.bak")
        nouvelle = secrets.token_urlsafe(50)
        texte = re.sub(r"^DJANGO_SECRET_KEY=.*$", f"DJANGO_SECRET_KEY={nouvelle}",
                       texte, flags=re.M)
        env.write_text(texte, encoding="utf-8")
        print("[CORRIGE] Nouvelle cle secrete generee (sauvegarde : .env.bak)")
    else:
        print("[OK] Cle secrete deja personnalisee")
else:
    print("[ATTENTION] .env introuvable")

# ---------------------------------------------------------------
# Initialisation Django
# ---------------------------------------------------------------
try:
    import django
    django.setup()
except Exception:
    print("\n[ERREUR] Initialisation Django impossible :")
    traceback.print_exc()
    raise SystemExit(1)

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse

from courrier.models import CategorieCourrier, Courrier

User = get_user_model()

# ---------------------------------------------------------------
# 3. Permissions des groupes
# ---------------------------------------------------------------
etape("3. DROITS DES GROUPES")
DROITS = {
    "Administrateur": [],
    "Accueil": [
        "view_courrier", "add_courrier", "transmettre_courrier",
        "valider_orientation", "view_affectation", "view_historique",
    ],
    "Secrétariat": [
        "view_courrier", "add_courrier", "change_courrier",
        "transmettre_courrier", "valider_orientation",
        "consulter_confidentiel",
        "view_affectation", "add_affectation", "change_affectation",
        "view_historique",
    ],
    "Responsable de service": [
        "view_courrier", "change_courrier", "traiter_courrier",
        "cloturer_courrier", "retourner_courrier", "reouvrir_courrier",
        "consulter_confidentiel",
        "view_affectation", "add_affectation", "change_affectation",
        "view_historique",
    ],
    "Agent": [
        "view_courrier", "traiter_courrier",
        "view_affectation", "view_historique",
    ],
    "Direction": [
        "view_courrier", "consulter_confidentiel",
        "view_affectation", "view_historique",
    ],
}

with transaction.atomic():
    for nom, codes in DROITS.items():
        groupe, _ = Group.objects.get_or_create(name=nom)
        perms = Permission.objects.filter(
            content_type__app_label="courrier", codename__in=codes
        )
        manquants = set(codes) - set(perms.values_list("codename", flat=True))
        groupe.permissions.set(perms)
        ligne = f"{nom} : {groupe.permissions.count()} droit(s)"
        if manquants:
            ligne += f"  [ABSENTS DE LA BASE : {', '.join(sorted(manquants))}]"
        print(ligne)

# ---------------------------------------------------------------
# 4. Categories
# ---------------------------------------------------------------
etape("4. CATEGORIES DE COURRIER")
if CategorieCourrier.objects.count() == 0:
    for nom in [
        "Administration générale", "Sinistres", "Production / Souscription",
        "Finance et comptabilité", "Juridique et contentieux",
        "Ressources humaines", "Réclamations", "Autre",
    ]:
        CategorieCourrier.objects.create(nom=nom, actif=True)
    print(f"{CategorieCourrier.objects.count()} categories creees")
else:
    print(f"{CategorieCourrier.objects.count()} categorie(s) deja presente(s) : aucune creation")

# ---------------------------------------------------------------
# 5. Mots de passe de test
# ---------------------------------------------------------------
etape("5. MOTS DE PASSE DES COMPTES")
ROLES = {
    "test_accueil": "Accueil",
    "test_secretariat": "Secrétariat",
    "test_responsable": "Responsable de service",
    "test_agent": "Agent",
    "test_direction": "Direction",
    "test_admin": "Administrateur (superuser)",
    "admin_gsc": "Administrateur (superuser)",
}
MOTS_DE_PASSE = {
    "admin_gsc": "Pyc98wRYcZAm#7",
    "test_admin": "qWxt77nTQyQE#7",
    "test_accueil": "ysmaUE6nsncp#7",
    "test_secretariat": "EN2bkg2ytry8#7",
    "test_responsable": "sGYvC4B2UtSF#7",
    "test_agent": "Zk2bk7q78fpD#7",
    "test_direction": "ZSRTePDp4nWK#7",
}
identifiants = []
inchanges = []
with transaction.atomic():
    for username, role in ROLES.items():
        user = User.objects.filter(username=username).first()
        if user is None:
            continue
        mdp = MOTS_DE_PASSE[username]
        user.set_password(mdp)
        user.is_active = True
        user.save()
        identifiants.append((username, role, mdp))
        print(f"[OK] {username}")

# ---------------------------------------------------------------
# 6. Bloc-notes
# ---------------------------------------------------------------
etape("6. BLOC-NOTES")
db = settings.DATABASES.get("default", {})
db_user = os.environ.get("DB_USER", "")
lignes = [
    "=" * 64,
    "GSC - GESTION ET SUIVI DU COURRIER : IDENTIFIANTS",
    f"Genere le {datetime.now():%d/%m/%Y a %H:%M}",
    "=" * 64,
    "",
    "CONFIDENTIEL : fichier a usage local, comptes de TEST uniquement.",
    "Ne pas l'envoyer par e-mail, ne pas le copier sur un serveur de production.",
    "",
    "--- ACCES A L'APPLICATION ---",
    "Application      : http://127.0.0.1:8000/",
    "Administration   : http://127.0.0.1:8000/admin/",
    "Lancement        : .venv\\Scripts\\Activate.ps1   puis   python manage.py runserver",
    "",
    "--- COMPTES ---",
]
for username, role, mdp in identifiants:
    lignes += [f"Compte : {username}", f"Profil : {role}", f"Mot de passe : {mdp}", ""]
for username, role in inchanges:
    lignes += [f"Compte : {username}", f"Profil : {role}",
               "Mot de passe : INCHANGE (stocke chiffre, non recuperable)", ""]
lignes += [
    "--- BASE DE DONNEES SQL SERVER ---",
    f"Base             : {db.get('NAME', '')}",
    f"Serveur/instance : {db.get('HOST', '')}",
    f"Authentification : {'compte SQL ' + db_user if db_user else 'Windows (Trusted connection)'}",
    f"Mot de passe SQL : {'voir le fichier .env (DB_PASSWORD)' if db_user else 'sans objet'}",
    "",
    "--- AUTRES ---",
    "Cle secrete Django : dans le fichier .env (DJANGO_SECRET_KEY)",
    "Sauvegardes creees : .env.bak, courrier/exports.py.bak (si modifies)",
    "Controle complet   : python audit_gsc.py",
    "Reinitialiser les mots de passe : python finaliser_gsc.py",
    "",
    "AVANT LA MISE EN PRODUCTION : supprimer les comptes test_*, changer tous",
    "les mots de passe, DJANGO_DEBUG=False, retirer db_owner du compte SQL.",
]
notes = BASE_DIR / "IDENTIFIANTS_GSC.txt"
notes.write_text("\r\n".join(lignes), encoding="utf-8-sig")
print("Fichier cree :", notes)

gitignore = BASE_DIR / ".gitignore"
if gitignore.exists() and "IDENTIFIANTS_GSC.txt" not in gitignore.read_text(encoding="utf-8"):
    with gitignore.open("a", encoding="utf-8") as f:
        f.write("\nIDENTIFIANTS_GSC.txt\n.env\n")

# ---------------------------------------------------------------
# 7. Test de fonctionnement par profil
# ---------------------------------------------------------------
etape("7. TEST DE FONCTIONNEMENT (lecture seule)")
cibles = [
    ("Tableau de bord", reverse("dashboard_interne")),
    ("Liste courriers", reverse("liste_courriers")),
    ("Bordereaux", reverse("liste_bordereaux")),
    ("Export Excel", reverse("exporter_courriers_excel")),
    ("Export PDF", reverse("exporter_courriers_pdf")),
]
courrier = Courrier.objects.order_by("pk").first()
if courrier:
    cibles.append(("Fiche courrier", reverse("detail_courrier", kwargs={"pk": courrier.pk})))

erreurs_500 = []
with override_settings(ALLOWED_HOSTS=["*"]):
    for username, role, _ in identifiants:
        user = User.objects.get(username=username)
        client = Client(raise_request_exception=False)
        client.force_login(user)
        resultats = []
        for libelle, url in cibles:
            try:
                code = client.get(url).status_code
            except Exception as exc:
                code = f"EXC {exc}"
            resultats.append(f"{libelle}={code}")
            if code == 500 or str(code).startswith("EXC"):
                erreurs_500.append(f"{username} / {libelle}")
        print(f"{username:18}", " | ".join(resultats))

print()
if erreurs_500:
    print("[A VERIFIER] Erreurs serveur (500) :")
    for e in erreurs_500:
        print("  -", e)
else:
    print("[OK] Aucune erreur serveur. (403 = acces refuse par les droits : normal selon le profil ;")
    print("     404 sur un export = aucun courrier visible pour ce profil.)")

print("\nTermine. Ouvrez IDENTIFIANTS_GSC.txt puis lancez : python manage.py runserver")
