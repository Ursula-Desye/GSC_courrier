r"""
GSC - Import du fichier SUIVI_COURRIER.xlsx

A placer dans D:\Downloads\GSC. Deux temps :

  1) SIMULATION (n'ecrit rien dans la base) :
       python import_suivi_excel.py SUIVI_COURRIER.xlsx
     -> ecrit RAPPORT_IMPORT.txt (ce qui sera cree, anomalies detectees)

  2) IMPORT REEL :
       python import_suivi_excel.py SUIVI_COURRIER.xlsx --appliquer
     -> cree services, comptes, courriers, affectations, suivi
     -> ecrit COMPTES_IMPORT.txt (mots de passe provisoires)
     Peut etre relance : les lignes deja importees sont ignorees.

Prerequis : python patch_suivi_excel.py, makemigrations, migrate.
"""
from pathlib import Path
import argparse
import collections
import datetime
import difflib
import os
import re
import secrets
import sys
import time
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

parser = argparse.ArgumentParser()
parser.add_argument("fichier")
parser.add_argument("--appliquer", action="store_true")
args = parser.parse_args()

# ---------------------------------------------------------------
# REGLES MODIFIABLES
# ---------------------------------------------------------------
SEUIL_RESPONSABLE = 200      # apparait au moins N fois dans "RESPONSABLE SERVICE"
SEUIL_CATEGORIE = 100        # une nature de courrier frequente devient une categorie
DESTINATAIRE = "GMC ASSURANCES"
TAILLE_LOT = 500
STRUCTURES_DIRECTION = {"DG", "DGA_CM", "DGA_SP", "DF"}
ALIAS_SERVICES = {
    "direction_generale": "DG", "daf": "DF",
    "dga_cm": "DGA_CM", "dga_sp": "DGA_SP",
}

import django
django.setup()

import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from courrier import models as M

if not hasattr(M, "SuiviCourrier"):
    raise SystemExit(
        "SuiviCourrier absent : lancez d'abord patch_suivi_excel.py, "
        "puis python manage.py makemigrations courrier et migrate."
    )

User = get_user_model()
AUJOURDHUI = timezone.localdate()
anomalies = collections.defaultdict(list)
infos = []


def norm(valeur):
    s = unicodedata.normalize("NFD", str(valeur))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.casefold().split())


def cle_service(valeur):
    return re.sub(r"[^a-z0-9]+", "_", norm(valeur)).strip("_")


def texte(valeur):
    if valeur is None or isinstance(valeur, (datetime.datetime, datetime.date)):
        return ""
    return " ".join(str(valeur).split())


def date_de(valeur, ligne, colonne):
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime.datetime):
        d = valeur.date()
    elif isinstance(valeur, datetime.date):
        d = valeur
    else:
        d = None
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                d = datetime.datetime.strptime(str(valeur).strip(), fmt).date()
                break
            except ValueError:
                pass
        if d is None:
            anomalies["Date illisible (ignoree)"].append(f"ligne {ligne}, {colonne} : {valeur!r}")
            return None
    if d.year < 2000 or d.year > 2100:
        anomalies["Date hors plage 2000-2100 (ignoree)"].append(f"ligne {ligne}, {colonne} : {d}")
        return None
    if d > AUJOURDHUI:
        anomalies["Date dans le futur (conservee)"].append(f"ligne {ligne}, {colonne} : {d}")
    return d


def en_datetime(d, heure=8):
    if d is None:
        return None
    return timezone.make_aware(datetime.datetime.combine(d, datetime.time(heure, 0)))


# ---------------------------------------------------------------
# 1. Lecture du fichier
# ---------------------------------------------------------------
print("Lecture du fichier Excel (1 a 2 minutes)...")
debut = time.time()
classeur = openpyxl.load_workbook(args.fichier, read_only=True, data_only=True)

# --- Parametres : services et personnel par service
ws = classeur["Paramètres"]
tableau = list(ws.iter_rows(min_row=1, max_row=40, min_col=2, max_col=14, values_only=True))
entetes = tableau[0]
services_noms = [r[1] for r in tableau[1:] if r[1]]
personnel_par_service = {}
marqueurs = {cle_service(s) for s in services_noms} | {"dga_cm", "dga_sp", "dg", "df"}
for idx in range(2, len(entetes)):
    service = entetes[idx]
    if not service:
        continue
    personnes = []
    for r in tableau[1:]:
        v = r[idx]
        if v and cle_service(v) not in marqueurs:
            personnes.append(texte(v))
    personnel_par_service[service] = personnes
infos.append(f"Services du fichier : {', '.join(services_noms)}")

# --- Donnees
lignes = []
for numero, r in enumerate(classeur["DATA"].iter_rows(min_row=2, max_col=26, values_only=True), start=2):
    if any(c not in (None, "") for c in r[1:26]):
        lignes.append((numero, r))
print(f"{len(lignes)} lignes de courriers lues en {time.time() - debut:.0f} s")

# ---------------------------------------------------------------
# 2. Personnes
# ---------------------------------------------------------------
connus = {}
for service, personnes in personnel_par_service.items():
    for p in personnes:
        connus.setdefault(norm(p), p)

alias_utilises = collections.Counter()
nouvelles_personnes = collections.OrderedDict()


def resoudre(valeur, ligne, colonne):
    if valeur is None or valeur == "":
        return None
    if not isinstance(valeur, str):
        anomalies["Nom attendu, date ou nombre trouve (ignore)"].append(f"ligne {ligne}, {colonne} : {valeur!r}")
        return None
    n = norm(valeur)
    if not n:
        return None
    if n in connus:
        return connus[n]
    if cle_service(n) in marqueurs:
        anomalies["Nom attendu, service trouve (ignore)"].append(f"ligne {ligne}, {colonne} : {valeur!r}")
        return None
    for cle, canon in connus.items():
        if n.startswith(cle + " ") or (len(n.split()) >= 2 and cle.startswith(n + " ")):
            alias_utilises[(valeur.strip(), canon)] += 1
            return canon
    proche = difflib.get_close_matches(n, list(connus), n=1, cutoff=0.85)
    if proche:
        canon = connus[proche[0]]
        alias_utilises[(valeur.strip(), canon)] += 1
        return canon
    if n not in nouvelles_personnes:
        nouvelles_personnes[n] = " ".join(valeur.split())
    return nouvelles_personnes[n]


def decouper(nom):
    mots = nom.split()
    famille = [m for m in mots if m.isupper() and len(m) > 1]
    prenoms = [m for m in mots if m not in famille]
    if not prenoms and len(mots) >= 2:      # tout en majuscules : NOM Prenom(s)
        famille, prenoms = [mots[0]], mots[1:]
    return " ".join(famille) or nom, " ".join(prenoms)


MOT_DE_PASSE_STANDARD = "gmcsa.12"


def identifiant(nom):
    """Identifiant = premier prenom puis nom (ex. NJOCK Elie -> elie.njock)."""
    famille, prenoms = decouper(nom)
    base = (prenoms.split()[0] + " " + famille) if prenoms else famille
    return re.sub(r"[^a-z0-9]+", ".", norm(base)).strip(".")[:150]


# Resolution de toutes les lignes (J, N, Q)
lignes_res = []
compte_resp = collections.Counter()
for numero, r in lignes:
    resp = resoudre(r[9], numero, "RESPONSABLE SERVICE")
    red = resoudre(r[13], numero, "Redacteur")
    fin = resoudre(r[16], numero, "REAFFECTATION REDACTEUR FINAL")
    if resp:
        compte_resp[resp] += 1
    lignes_res.append((numero, r, resp, red, fin))

responsables_noms = {p for p, n in compte_resp.items() if n >= SEUIL_RESPONSABLE}
for service, personnes in personnel_par_service.items():
    if len(personnes) == 1:
        responsables_noms.add(personnes[0])

# ---------------------------------------------------------------
# 3. Natures -> categories
# ---------------------------------------------------------------
compte_nature = collections.Counter()
casse_nature = collections.defaultdict(collections.Counter)
for numero, r in lignes:
    nat = texte(r[3])
    if nat:
        k = norm(nat)
        compte_nature[k] += 1
        casse_nature[k][nat.upper()] += 1
categories_nom = {}
for k, n in compte_nature.items():
    if n >= SEUIL_CATEGORIE:
        categories_nom[k] = casse_nature[k].most_common(1)[0][0][:100]
couvert = sum(compte_nature[k] for k in categories_nom)
infos.append(
    f"Categories : {len(categories_nom)} natures frequentes (>= {SEUIL_CATEGORIE} courriers) "
    f"couvrent {couvert} courriers ; les {sum(compte_nature.values()) - couvert} autres iront en 'AUTRE'"
)


def service_de(valeur, ligne):
    if valeur in (None, ""):
        return None
    c = cle_service(valeur)
    c = ALIAS_SERVICES.get(c, c)
    for nom in services_noms:
        if cle_service(nom) == c:
            return nom
    anomalies["Service de destination inconnu (courrier sans service)"].append(f"ligne {ligne} : {valeur!r}")
    return None


def execution_de(valeur, ligne):
    if valeur in (None, ""):
        return ""
    t = norm(valeur)
    if isinstance(valeur, (datetime.datetime, datetime.date)) or not t:
        anomalies["Execution OUI/NON invalide (ignoree)"].append(f"ligne {ligne} : {valeur!r}")
        return ""
    if t.startswith("o"):
        return "OUI"
    if t.startswith("n"):
        return "NON"
    anomalies["Execution OUI/NON invalide (ignoree)"].append(f"ligne {ligne} : {valeur!r}")
    return ""


# ---------------------------------------------------------------
# 4. Preparation des enregistrements
# ---------------------------------------------------------------
fiches = []
for numero, r, resp, red, fin in lignes_res:
    d_courrier = date_de(r[1], numero, "DATE RECEPTION")
    dates = {
        "G": date_de(r[6], numero, "DATE TRANSMISSION AU DEPARTEMENT"),
        "I": date_de(r[8], numero, "DATE RECEPTION / DEPARTEMENT"),
        "K": date_de(r[10], numero, "DATE TRANSMISSION AU RESPONSABLE"),
        "M": date_de(r[12], numero, "DATE RECEPTION / RESPONSABLE"),
        "O": date_de(r[14], numero, "DATE AFFECTATION AU REDACTEUR"),
        "R": date_de(r[17], numero, "DATE AFFECTATION AU REDACTEUR FINAL"),
        "S": date_de(r[18], numero, "DATE RECEPTION / REDACTEUR FINAL"),
        "W": date_de(r[22], numero, "DATE TRAITEMENT"),
        "Y": date_de(r[24], numero, "DATE EXECUTION"),
    }
    if d_courrier is None:
        d_courrier = next((dates[k] for k in ("G", "I", "K", "O") if dates[k]), None)
        anomalies["Date de reception absente (date de repli utilisee)"].append(f"ligne {numero}")
        if d_courrier is None:
            d_courrier = AUJOURDHUI
    service = service_de(r[5], numero)
    execution = execution_de(r[23], numero)
    fiches.append({
        "ligne": numero, "r": r, "resp": resp, "red": red, "fin": fin,
        "date": d_courrier, "d": dates, "service": service, "execution": execution,
    })

# ---------------------------------------------------------------
# 5. Rapport de simulation
# ---------------------------------------------------------------
par_service = collections.Counter(f["service"] or "(aucun)" for f in fiches)
par_annee = collections.Counter(f["date"].year for f in fiches)


def statut_de(f):
    if f["execution"] == "OUI":
        return "CLOTURE"
    if f["d"]["W"]:
        return "TRAITE"
    if f["red"] or f["fin"]:
        return "EN_COURS"
    if f["service"] and (f["d"]["G"] or f["resp"]):
        return "TRANSMIS"
    return "ENREGISTRE"


par_statut = collections.Counter(statut_de(f) for f in fiches)

rapport = [
    "GSC - RAPPORT D'IMPORT DU FICHIER " + Path(args.fichier).name,
    f"Mode : {'IMPORT REEL' if args.appliquer else 'SIMULATION (rien n ecrit)'}",
    f"Genere le {datetime.datetime.now():%d/%m/%Y %H:%M}",
    "",
    f"Courriers a importer : {len(fiches)}",
    "Par annee : " + ", ".join(f"{a} = {n}" for a, n in sorted(par_annee.items())),
    "Par statut : " + ", ".join(f"{a} = {n}" for a, n in par_statut.most_common()),
    "Par service : " + ", ".join(f"{a} = {n}" for a, n in par_service.most_common()),
    "",
] + infos + [""]
rapport.append(f"Responsables (>= {SEUIL_RESPONSABLE} courriers ou seul du service) : " + ", ".join(sorted(responsables_noms)))
rapport.append("Personnel autorise par service (liste deroulante) :")
for s, ps in personnel_par_service.items():
    rapport.append(f"  - {s} : {len(ps)} personne(s)")
if alias_utilises:
    rapport += ["", "Noms regroupes (variantes d'ecriture) :"]
    for (v, c), n in alias_utilises.most_common():
        rapport.append(f"  - {v!r} -> {c} ({n} fois)")
if nouvelles_personnes:
    rapport += ["", "Personnes absentes de l'onglet Parametres (un compte sera cree) :"]
    for n in nouvelles_personnes.values():
        rapport.append(f"  - {n}")
rapport += ["", "ANOMALIES DU FICHIER"]
if not anomalies:
    rapport.append("  aucune")
for titre, liste in anomalies.items():
    rapport.append(f"  {titre} : {len(liste)}")
    for ligne in liste[:8]:
        rapport.append(f"      {ligne}")
    if len(liste) > 8:
        rapport.append(f"      ... et {len(liste) - 8} autres")


def ecrire_rapport():
    Path("RAPPORT_IMPORT.txt").write_text("\r\n".join(rapport), encoding="utf-8-sig")


if not args.appliquer:
    ecrire_rapport()
    print("\n".join(rapport[:14]))
    print("\nRapport complet : RAPPORT_IMPORT.txt")
    print("Rien n'a ete ecrit dans la base. Pour importer : ajoutez --appliquer")
    raise SystemExit(0)

# ---------------------------------------------------------------
# 6. IMPORT REEL
# ---------------------------------------------------------------
print("\nCreation de la structure...")
groupe_resp, _ = Group.objects.get_or_create(name="Responsable de service")
groupe_agent, _ = Group.objects.get_or_create(name="Agent")

utilisateur_import, _ = User.objects.get_or_create(
    username="import_excel",
    defaults={"is_active": False, "first_name": "Import", "last_name": "Excel"},
)

services = {}
for nom in services_noms:
    services[nom], _ = M.Service.objects.get_or_create(
        nom=nom,
        defaults={
            "type_structure": "DIRECTION" if nom in STRUCTURES_DIRECTION else "DEPARTEMENT",
            "description": "Cree par l'import du fichier SUIVI_COURRIER.xlsx",
            "actif": True,
        },
    )

comptes_crees = []
utilisateurs = {}
toutes_personnes = set(connus.values()) | set(nouvelles_personnes.values())
for nom in sorted(toutes_personnes):
    login = identifiant(nom)
    user = User.objects.filter(username=login).first()
    nouveau_compte = user is None
    if user is None:
        mdp = MOT_DE_PASSE_STANDARD
        famille, prenoms = decouper(nom)
        user = User.objects.create_user(
            username=login, password=mdp, is_active=True,
            last_name=famille[:150], first_name=prenoms[:150],
        )
        comptes_crees.append((nom, login, mdp,
                              "Responsable de service" if nom in responsables_noms else "Agent"))
    utilisateurs[nom] = user
    # Les comptes deja existants (crees a l'etape 2) gardent leur role.
    if nouveau_compte:
        if nom in responsables_noms:
            user.groups.add(groupe_resp)
        else:
            user.groups.add(groupe_agent)

for service_nom, personnes in personnel_par_service.items():
    for nom in personnes:
        M.PersonnelService.objects.get_or_create(
            service=services[service_nom], utilisateur=utilisateurs[nom],
        )

# Responsables par service : ceux du service (parametres) qui sont responsables
resp_par_service = collections.defaultdict(collections.Counter)
for f in fiches:
    if f["resp"] and f["service"]:
        resp_par_service[f["service"]][f["resp"]] += 1
for service_nom, service in services.items():
    if M.ResponsableService.objects.filter(service=service).exists():
        candidats = []   # responsables deja definis a l'etape 2
    else:
        candidats = [p for p in personnel_par_service.get(service_nom, []) if p in responsables_noms]
    for nom in candidats:
        M.ResponsableService.objects.get_or_create(
            service=service, utilisateur=utilisateurs[nom],
            defaults={
                "toutes_categories": True, "peut_affecter_agents": True,
                "peut_cloturer": True, "chef_departement": False,
                "inclure_structures_enfants": False, "actif": True,
            },
        )
    if service.responsable_id is None and resp_par_service.get(service_nom):
        principal = resp_par_service[service_nom].most_common(1)[0][0]
        service.responsable = utilisateurs[principal]
        service.save(update_fields=["responsable"])

categories = {}
for k, nom in categories_nom.items():
    categories[k], _ = M.CategorieCourrier.objects.get_or_create(nom=nom)
autre, _ = M.CategorieCourrier.objects.get_or_create(nom="AUTRE")

# --- compteurs de references
compteurs = {}


def prochaine_reference(annee):
    if annee not in compteurs:
        compteur, _ = M.CompteurReference.objects.get_or_create(
            sens="ENTRANT", annee=annee, defaults={"dernier_numero": 0})
        maxi = compteur.dernier_numero
        for ref in M.Courrier.objects.filter(reference__startswith=f"ENT-{annee}-").values_list("reference", flat=True):
            try:
                maxi = max(maxi, int(ref.rsplit("-", 1)[1]))
            except (ValueError, IndexError):
                pass
        compteurs[annee] = [compteur, maxi]
    compteurs[annee][1] += 1
    return f"ENT-{annee}-{compteurs[annee][1]:06d}"


deja = set(M.SuiviCourrier.objects.exclude(ligne_source=None).values_list("ligne_source", flat=True))
a_importer = [f for f in fiches if f["ligne"] not in deja]
print(f"{len(deja)} lignes deja importees, {len(a_importer)} a importer")

STATUT_AFF = {"CLOTURE": "TRAITE", "TRAITE": "TRAITE", "EN_COURS": "EN_COURS", "TRANSMIS": "TRANSMIS", "ENREGISTRE": "TRANSMIS"}


def importer(f):
    r, d = f["r"], f["d"]
    statut = statut_de(f)
    service = services.get(f["service"]) if f["service"] else None
    resp_user = utilisateurs.get(f["resp"]) if f["resp"] else None
    red_user = utilisateurs.get(f["red"]) if f["red"] else None
    fin_user = utilisateurs.get(f["fin"]) if f["fin"] else None

    nature = texte(r[3])
    categorie = categories.get(norm(nature), autre) if nature else autre
    objet = " - ".join(x for x in (nature, texte(r[4])) if x)[:250] or "(objet non renseigne)"

    courrier = M.Courrier(
        reference=prochaine_reference(f["date"].year),
        sens="ENTRANT",
        date_courrier=f["date"], date_reception_expedition=f["date"],
        expediteur=(texte(r[2]) or "NON RENSEIGNE")[:180],
        destinataire=DESTINATAIRE, objet=objet,
        categorie=categorie,
        service=service if statut != "ENREGISTRE" else None,
        responsable=resp_user if statut != "ENREGISTRE" else None,
        priorite="NORMALE", confidentialite="NORMALE",
        statut=statut,
        date_cloture=(d["Y"] or d["W"] or f["date"]) if statut == "CLOTURE" else None,
        cree_par=utilisateur_import,
    )
    courrier.save()

    transmetteur = utilisateur_import
    if service:
        M.Affectation.objects.create(
            courrier=courrier, service=service, agent=None, type_affectation="SERVICE",
            transmis_par=transmetteur,
            date_transmission=en_datetime(d["G"] or f["date"]),
            statut="TRANSMIS", observation=texte(r[7]),
            active=True,
            date_confirmation_reception=en_datetime(d["I"], 9),
            confirme_par=resp_user if d["I"] else None,
        )
        if red_user:
            M.Affectation.objects.create(
                courrier=courrier, service=service, agent=red_user, type_affectation="AGENT",
                transmis_par=resp_user or transmetteur,
                date_transmission=en_datetime(d["O"] or d["K"] or d["G"] or f["date"]),
                instruction=texte(r[15]),
                statut=STATUT_AFF[statut], observation=texte(r[11]),
                active=fin_user is None,
                date_confirmation_reception=en_datetime(d["S"], 10) if fin_user is None else None,
                confirme_par=red_user if (fin_user is None and d["S"]) else None,
            )
        if fin_user:
            M.Affectation.objects.create(
                courrier=courrier, service=service, agent=fin_user, type_affectation="AGENT",
                transmis_par=resp_user or transmetteur,
                date_transmission=en_datetime(d["R"] or d["O"] or f["date"]),
                instruction=texte(r[15]),
                statut=STATUT_AFF[statut], active=True,
                date_confirmation_reception=en_datetime(d["S"], 10),
                confirme_par=fin_user if d["S"] else None,
            )

    numero_ordre = texte(r[0]) if isinstance(r[0], str) else ""
    dossier = texte(r[19]).split(".")[0] if isinstance(r[19], float) else texte(r[19])
    M.SuiviCourrier.objects.create(
        courrier=courrier, ligne_source=f["ligne"],
        numero_ordre=numero_ordre[:30], nature=nature[:250],
        reference_excel=texte(r[4])[:250],
        date_transmission_departement=d["G"],
        observation_retour_departement=texte(r[7]),
        date_reception_departement=d["I"],
        responsable_nom=(f["resp"] or texte(r[9]))[:180],
        date_transmission_responsable=d["K"],
        observation_retour_responsable=texte(r[11]),
        date_reception_responsable=d["M"],
        redacteur_nom=(f["red"] or texte(r[13]))[:180],
        date_affectation_redacteur=d["O"],
        instructions_responsable=texte(r[15]),
        redacteur_final_nom=(f["fin"] or texte(r[16]))[:180],
        date_affectation_redacteur_final=d["R"],
        date_reception_redacteur_final=d["S"],
        numero_dossier=dossier[:60],
        assure=texte(r[20])[:250],
        action_menee=texte(r[21]),
        date_traitement=d["W"],
        execution=f["execution"],
        date_execution=d["Y"],
        observations=texte(r[25]),
    )
    M.Historique.objects.create(
        courrier=courrier, utilisateur=utilisateur_import, action="IMPORT_EXCEL",
        details=f"Repris du fichier SUIVI_COURRIER.xlsx (ligne {f['ligne']}).",
    )


debut = time.time()
fait = 0
for i in range(0, len(a_importer), TAILLE_LOT):
    lot = a_importer[i:i + TAILLE_LOT]
    with transaction.atomic():
        for f in lot:
            importer(f)
    fait += len(lot)
    reste = (time.time() - debut) / fait * (len(a_importer) - fait)
    print(f"  {fait}/{len(a_importer)} courriers importes (reste environ {reste / 60:.1f} min)")

for annee, (compteur, maxi) in compteurs.items():
    compteur.dernier_numero = maxi
    compteur.save(update_fields=["dernier_numero"])

if comptes_crees:
    lignes_c = [
        "GSC - COMPTES CREES PAR L'IMPORT (mots de passe provisoires)",
        f"Genere le {datetime.datetime.now():%d/%m/%Y %H:%M}",
        "CONFIDENTIEL : a remettre a chaque personne puis a supprimer.", "",
    ]
    for nom, login, mdp, profil in comptes_crees:
        lignes_c += [f"Nom : {nom}", f"Compte : {login}", f"Mot de passe : {mdp}", f"Profil : {profil}", ""]
    Path("COMPTES_IMPORT.txt").write_text("\r\n".join(lignes_c), encoding="utf-8-sig")
    rapport.append("")
    rapport.append(f"Comptes crees : {len(comptes_crees)} (voir COMPTES_IMPORT.txt)")

rapport.append(f"Courriers importes : {fait}")
ecrire_rapport()
print(f"\nTermine : {fait} courriers importes. Rapport : RAPPORT_IMPORT.txt"
      + (f" ; comptes : COMPTES_IMPORT.txt ({len(comptes_crees)})" if comptes_crees else ""))
