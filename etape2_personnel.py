r"""
GSC - ETAPE 2 : creer les comptes du personnel (chefs de departement,
responsables de service, agents) depuis PERSONNEL_A_VERIFIER.xlsx

    python etape2_personnel.py             -> verification, rien n'est ecrit
    python etape2_personnel.py --appliquer -> creation reelle

Prerequis : etape 1 (services) faite.
Roles : Chef de departement et Responsable de service -> groupe
"Responsable de service" (le chef a en plus l'indicateur chef de departement) ;
Agent -> groupe "Agent". Un compte existant n'a jamais son mot de passe modifie.
"""
from pathlib import Path
import collections
import datetime
import os
import re
import secrets
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

APPLIQUER = "--appliquer" in sys.argv
FICHIER = "PERSONNEL_A_VERIFIER.xlsx"
CHEF, RESP, AGENT = "Chef de département", "Responsable de service", "Agent"
PRIORITE = {CHEF: 0, RESP: 1, AGENT: 2}

if not Path(FICHIER).exists():
    raise SystemExit(f"Fichier introuvable : {FICHIER} (a placer dans ce dossier)")

import django
django.setup()
import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from courrier import models as M

User = get_user_model()


def norm(v):
    s = unicodedata.normalize("NFD", str(v))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.casefold().split())


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


roles_ok = {norm(r): r for r in PRIORITE}
services = {s.nom: s for s in M.Service.objects.all()}
lignes, erreurs = [], []
ws = openpyxl.load_workbook(FICHIER, data_only=True)["Personnel"]
for n, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
    nom = " ".join(str(r[0]).split()) if r[0] else ""
    if not nom:
        continue
    service = " ".join(str(r[1]).split()) if r[1] else ""
    role = roles_ok.get(norm(r[2])) if r[2] else None
    login = identifiant(nom)
    if service not in services:
        erreurs.append(f"ligne {n} ({nom}) : service inconnu {service!r} (lancez d'abord l'etape 1)")
    if role is None:
        erreurs.append(f"ligne {n} ({nom}) : role invalide {r[2]!r}")
    if not login:
        erreurs.append(f"ligne {n} ({nom}) : identifiant vide")
    lignes.append((nom, service, role, login))

par_login = collections.defaultdict(set)
for nom, _, _, login in lignes:
    par_login[login].add(nom)
for login, noms in par_login.items():
    if len(noms) > 1:
        erreurs.append(f"identifiant {login!r} utilise par plusieurs personnes : {', '.join(sorted(noms))}")

compte = collections.Counter(l[2] for l in lignes)
print(f"{len(lignes)} lignes, {len(par_login)} personnes : " + ", ".join(f"{k} = {v}" for k, v in compte.items()))
if erreurs:
    print("\nERREURS A CORRIGER DANS LE FICHIER (rien n'a ete ecrit) :")
    for e in erreurs:
        print("  -", e)
    raise SystemExit(1)

print("\nPlan :")
for nom, service, role, login in lignes:
    existe = "existe" if User.objects.filter(username=login).exists() else "nouveau"
    print(f"  {nom:<28} {service:<26} {role:<24} compte {login} ({existe})")

if not APPLIQUER:
    print("\nVerification terminee, rien n'a ete ecrit. Pour creer : ajoutez --appliquer")
    raise SystemExit(0)

groupe_resp, _ = Group.objects.get_or_create(name="Responsable de service")
groupe_agent, _ = Group.objects.get_or_create(name="Agent")
crees = []
with transaction.atomic():
    meilleur = {}
    for nom, service, role, login in lignes:
        if login not in meilleur or PRIORITE[role] < PRIORITE[meilleur[login][1]]:
            meilleur[login] = (nom, role)

    utilisateurs = {}
    for login, (nom, role) in meilleur.items():
        user = User.objects.filter(username=login).first()
        if user is None:
            mot_de_passe = MOT_DE_PASSE_STANDARD
            famille, prenoms = decouper(nom)
            user = User.objects.create_user(
                username=login, password=mot_de_passe, is_active=True,
                last_name=famille[:150], first_name=prenoms[:150],
            )
            crees.append((nom, login, mot_de_passe, role))
        if role == AGENT:
            user.groups.add(groupe_agent)
            user.groups.remove(groupe_resp)
        else:
            user.groups.add(groupe_resp)
            user.groups.remove(groupe_agent)
        utilisateurs[login] = user

    for nom, service, role, login in lignes:
        user, svc = utilisateurs[login], services[service]
        M.PersonnelService.objects.get_or_create(service=svc, utilisateur=user)
        if role in (CHEF, RESP):
            M.ResponsableService.objects.update_or_create(
                service=svc, utilisateur=user,
                defaults={
                    "chef_departement": role == CHEF,
                    "toutes_categories": True, "peut_affecter_agents": True,
                    "peut_cloturer": True, "inclure_structures_enfants": False,
                    "actif": True,
                },
            )
        else:
            M.ResponsableService.objects.filter(service=svc, utilisateur=user).update(actif=False)

    for svc in {services[l[1]] for l in lignes}:
        if svc.responsable_id is None:
            candidats = [l for l in lignes if l[1] == svc.nom and l[2] in (CHEF, RESP)]
            candidats.sort(key=lambda l: PRIORITE[l[2]])
            if candidats:
                svc.responsable = utilisateurs[candidats[0][3]]
                svc.save(update_fields=["responsable"])

if crees:
    out = [
        "GSC - COMPTES CREES (mots de passe provisoires)",
        f"Genere le {datetime.datetime.now():%d/%m/%Y %H:%M}",
        "CONFIDENTIEL : a remettre a chaque personne puis a supprimer.", "",
    ]
    for nom, login, mdp, role in crees:
        out += [f"Nom : {nom}", f"Compte : {login}", f"Mot de passe : {mdp}", f"Role : {role}", ""]
    Path("COMPTES_PERSONNEL.txt").write_text("\r\n".join(out), encoding="utf-8-sig")
print(f"\nTermine : {len(crees)} compte(s) cree(s)" + (" -> COMPTES_PERSONNEL.txt" if crees else "")
      + f", {len(meilleur) - len(crees)} deja existant(s) conserve(s).")
