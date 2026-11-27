from pathlib import Path
import os
import sys
import traceback

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

print("=" * 72)
print("GSC - AUDIT GLOBAL EN LECTURE SEULE")
print("Projet :", BASE_DIR)
print("=" * 72)

try:
    import django
    django.setup()
except Exception:
    print("\n[ERREUR] Initialisation Django impossible :")
    traceback.print_exc()
    raise SystemExit(1)

from django.conf import settings
from django.core.checks import run_checks
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import get_resolver, reverse, NoReverseMatch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from courrier import models
from courrier.permissions import obtenir_profil

issues = []
warnings = []

def result(label, ok, detail=""):
    status = "OK" if ok else "A VERIFIER"
    print(f"[{status}] {label}" + (f" : {detail}" if detail else ""))
    if not ok:
        issues.append(label)

def section(title):
    print("\n" + "-" * 72)
    print(title)
    print("-" * 72)

# 1. Configuration et contrôles Django
section("1. CONFIGURATION ET CONTROLES DJANGO")
print("Django :", django.get_version())
print("Base configurée :", settings.DATABASES.get("default", {}).get("ENGINE"))
print("Fichier settings :", os.environ.get("DJANGO_SETTINGS_MODULE"))

try:
    errors = run_checks()
    serious = [e for e in errors if e.level >= 30]
    for e in errors:
        print(f" - {e.level_tag}: {e.msg} ({e.id or 'sans identifiant'})")
    result("Vérifications Django", not serious,
           f"{len(errors)} avertissement(s)/erreur(s), {len(serious)} erreur(s) bloquante(s)")
except Exception as exc:
    result("Vérifications Django", False, str(exc))

# 2. Connexion SQL et migrations
section("2. BASE SQL SERVER ET MIGRATIONS")
try:
    connection.ensure_connection()
    print("Connexion SQL : réussie")
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    result("Migrations", not plan,
           "Aucune migration en attente" if not plan else
           "Migrations en attente : " + ", ".join(str(item[0]) for item in plan))
except Exception as exc:
    result("Connexion SQL / migrations", False, repr(exc))

# 3. Présence des modèles et volumes
section("3. MODELES ET DONNEES EN BASE")
model_names = [
    "Service", "ResponsableService", "CategorieCourrier", "Courrier",
    "Affectation", "DelegationTransmission", "RetourCourrier",
    "PieceJointe", "BordereauTransmission", "LigneBordereau",
    "ReceptionBordereau", "Historique", "AutorisationConfidentialite",
    "RegleOrientation", "JournalAccesConfidentiel", "ParametreGSC",
]
for name in model_names:
    cls = getattr(models, name, None)
    if cls is None:
        result(f"Modèle {name}", False, "classe absente de courrier.models")
        continue
    try:
        count = cls.objects.count()
        result(f"Modèle {name}", True, f"{count} enregistrement(s)")
    except Exception as exc:
        result(f"Table {name}", False, str(exc))

# 4. Comptes, profils et groupes
section("4. UTILISATEURS, GROUPES ET PROFILS")
User = get_user_model()
try:
    users = User.objects.filter(is_active=True).order_by("username")
    print("Groupes présents :", ", ".join(Group.objects.values_list("name", flat=True)) or "(aucun)")
    if not users.exists():
        result("Comptes actifs", False, "aucun utilisateur actif")
    else:
        for user in users:
            groups = ", ".join(user.groups.values_list("name", flat=True)) or "(sans groupe)"
            try:
                profile = obtenir_profil(user)
            except Exception as exc:
                profile = f"ERREUR: {exc}"
            print(f" - {user.username} | profil={profile} | groupes={groups} | staff={user.is_staff} | superuser={user.is_superuser}")
        result("Comptes actifs", True, f"{users.count()} compte(s)")
except Exception as exc:
    result("Lecture des utilisateurs", False, str(exc))

# 5. Configuration opérationnelle
section("5. CONFIGURATION DES STRUCTURES ET CATEGORIES")
try:
    services = models.Service.objects.all()
    actifs = services.filter(actif=True)
    print(f"Structures : {services.count()} total / {actifs.count()} actives")
    for service in services.select_related("responsable").order_by("nom"):
        responsables = []
        if hasattr(service, "responsables_configures"):
            responsables = list(service.responsables_configures.filter(actif=True).values_list("utilisateur__username", flat=True))
        legacy = service.responsable.username if service.responsable_id else "-"
        print(f" - {service.nom} | type={getattr(service, 'type_structure', '-')} | parent={service.parent if hasattr(service, 'parent') else '-'} | responsable_ancien={legacy} | responsables={responsables} | actif={service.actif}")
    result("Structures actives", actifs.exists(), f"{actifs.count()} structure(s) active(s)")
except Exception as exc:
    result("Configuration des structures", False, str(exc))

try:
    categories = models.CategorieCourrier.objects.all()
    active_categories = categories.filter(actif=True)
    print(f"Catégories : {categories.count()} total / {active_categories.count()} actives")
    result("Catégories actives", active_categories.exists(), f"{active_categories.count()} catégorie(s) active(s)")
except Exception as exc:
    result("Catégories", False, str(exc))

# 6. Etat métier des courriers
section("6. ETAT DES COURRIERS ET AFFECTATIONS")
try:
    qs = models.Courrier.objects.all()
    print("Courriers total :", qs.count())
    for field, label in [
        ("sens", "Sens"), ("statut", "Statuts"),
        ("confidentialite", "Confidentialité"),
    ]:
        try:
            print(label + " :", list(qs.values(field).order_by(field).annotate(n=__import__("django").db.models.Count("id")).values_list(field, "n")))
        except Exception as exc:
            print(f"{label} : non disponible ({exc})")
    print("Affectations actives :", models.Affectation.objects.filter(active=True).count())
    print("Affectations service non confirmées :", models.Affectation.objects.filter(active=True, agent__isnull=True, date_confirmation_reception__isnull=True).count())
    print("Bordereaux :", models.BordereauTransmission.objects.count())
    print("Retours non traités :", models.RetourCourrier.objects.filter(traite=False).count())
except Exception as exc:
    result("Lecture des données métier", False, str(exc))

# 7. URLs attendues
section("7. ROUTES IMPORTANTES")
routes = [
    "dashboard_interne", "liste_courriers", "nouveau_courrier",
    "detail_courrier", "modifier_courrier", "transmettre_courrier",
    "confirmer_reception", "affecter_agent", "traiter_courrier",
    "retourner_courrier", "cloturer_courrier", "reouvrir_courrier",
    "liste_bordereaux", "creer_bordereau", "detail_bordereau",
    "receptionner_bordereau", "exporter_courriers_excel",
    "exporter_courriers_pdf", "telecharger_document_courrier",
    "telecharger_piece_jointe",
]
for name in routes:
    try:
        # Ne fournir des paramètres que pour les routes qui en exigent.
        avec_pk = {
            "detail_courrier", "modifier_courrier", "transmettre_courrier",
            "confirmer_reception", "affecter_agent", "traiter_courrier",
            "retourner_courrier", "cloturer_courrier", "reouvrir_courrier",
            "gerer_autorisations_confidentielles",
            "telecharger_document_courrier", "ajouter_piece_jointe",
            "retirer_piece_jointe", "liste_bordereaux", "detail_bordereau",
            "receptionner_bordereau",
        }
        kwargs = {"pk": 1} if name in avec_pk else {}
        if name == "telecharger_piece_jointe":
            kwargs = {"pk": 1, "piece_id": 1}
        reverse(name, kwargs=kwargs)
        result(f"Route {name}", True)
    except NoReverseMatch:
        result(f"Route {name}", False, "nom absent ou paramètres incompatibles")
    except Exception as exc:
        result(f"Route {name}", False, str(exc))

# 8. Templates attendus
section("8. TEMPLATES ET FICHIERS DE L'APPLICATION")
templates = [
    "base.html", "registration/login.html",
    "courrier/dashboard.html", "courrier/liste.html",
    "courrier/detail.html", "courrier/formulaire.html",
    "courrier/confirmation_cloture.html",
    "courrier/autorisations_confidentielles.html",
    "courrier/bordereaux/liste.html",
    "courrier/bordereaux/formulaire.html",
    "courrier/bordereaux/detail.html",
]
for name in templates:
    exists = any((Path(folder) / name).is_file() for folder in settings.TEMPLATES[0].get("DIRS", []))
    if not exists:
        exists = (BASE_DIR / "templates" / name).is_file()
    result(f"Template {name}", exists, "présent" if exists else "introuvable dans templates/")

for name in ["courrier/views.py", "courrier/permissions.py", "courrier/forms.py",
             "courrier/urls.py", "courrier/bordereaux.py", "courrier/exports.py",
             "courrier/models.py", "courrier/admin.py"]:
    p = BASE_DIR / name
    result(f"Fichier {name}", p.is_file(), f"{p.stat().st_size} octets" if p.is_file() else "absent")

# 9. Contrôles statiques ciblés sur les règles métier et sécurité
section("9. CONTROLES CIBLES DU CODE")
def source_has(path, snippets):
    p = BASE_DIR / path
    if not p.exists():
        return False, "fichier absent"
    source = p.read_text(encoding="utf-8", errors="replace")
    missing = [s for s in snippets if s not in source]
    return not missing, ("tous les marqueurs trouvés" if not missing else "marqueurs absents : " + ", ".join(missing))

checks = [
    ("Confirmation réception", "courrier/views.py",
     ["def confirmer_reception", "date_confirmation_reception", "confirme_par"]),
    ("Affectation agents", "courrier/views.py",
     ["def affecter_agent", "Veuillez sélectionner au moins un agent"]),
    ("Traitement", "courrier/views.py",
     ["def traiter_courrier", "Historique"]),
    ("Récupération courrier clôturé", "courrier/views.py",
     ["def reouvrir_courrier"]),
    ("Permissions affectation", "courrier/permissions.py",
     ["def utilisateur_peut_affecter_agent"]),
    ("Permissions traitement", "courrier/permissions.py",
     ["def utilisateur_peut_traiter_courrier"]),
    ("Bordereaux et réception", "courrier/bordereaux.py",
     ["def creer_bordereau", "def receptionner_bordereau", "ReceptionBordereau"]),
    ("Exports Excel/PDF", "courrier/exports.py",
     ["def exporter_courriers_excel", "def exporter_courriers_pdf"]),
]
for label, path, snippets in checks:
    ok, detail = source_has(path, snippets)
    result(label, ok, detail)

detail_path = BASE_DIR / "templates/courrier/detail.html"
if detail_path.exists():
    detail = detail_path.read_text(encoding="utf-8", errors="replace")
    safe_main = "{% url 'telecharger_document_courrier' courrier.pk %}" in detail
    safe_piece = "{% url 'telecharger_piece_jointe' courrier.pk piece.pk %}" in detail
    result("Téléchargement sécurisé du document principal", safe_main,
           "URL Django sécurisée" if safe_main else "vérifier le lien document.url")
    result("Téléchargement sécurisé des pièces jointes", safe_piece,
           "URL Django sécurisée" if safe_piece else "vérifier le lien piece.fichier.url")
else:
    result("Sécurité des liens de téléchargement", False, "detail.html absent")

# 10. Résumé et limites
section("10. SYNTHESE")
print("Points à examiner :", len(issues))
for item in issues:
    print(" -", item)
print("\nCet audit ne modifie aucune donnée et ne lance aucune migration.")
print("Il vérifie l'état ACTUEL de ce dossier et de sa base, pas seulement les anciennes sauvegardes.")
print("Certaines règles métier (droits réels, confidentialité, réception avant affectation)")
print("nécessitent encore une revue fonctionnelle et des tests avec comptes de chaque rôle.")
