r"""
GSC - PATCH "DEMANDE D'ACCES" (remplacement temporaire entre agents)

A placer dans D:\Downloads\GSC (a cote de manage.py), puis :
    python patch_acces.py
    python manage.py makemigrations courrier
    python manage.py migrate

Ce que fait le patch (sauvegardes .bak, relancable sans risque) :
 - models.py      : ajoute le modele DemandeAcces
 - permissions.py : acces temporaire d'un agent (jamais aux courriers confidentiels)
 - views.py       : liste et traitement prennent en compte l'acces temporaire
 - urls.py        : 4 nouvelles pages (/courriers/acces/...)
 - cree acces.py, admin_acces.py, templatetags/gsc_acces.py et 3 gabarits
 - ajoute le bandeau dans liste.html et detail.html s'ils existent
"""
import re
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
APP = BASE / "courrier"
if not (APP / "models.py").exists():
    print("[ERREUR] courrier/models.py introuvable : placez ce fichier a cote de manage.py")
    raise SystemExit(1)


def lire(p):
    brut = p.read_bytes().decode("utf-8-sig")
    crlf = "\r\n" in brut
    return brut.replace("\r\n", "\n"), crlf


def ecrire(p, texte, crlf):
    sauvegarde = p.with_name(p.name + ".acces.bak")
    if not sauvegarde.exists() and p.exists():
        shutil.copy2(p, sauvegarde)
    if crlf:
        texte = texte.replace("\n", "\r\n")
    p.write_bytes(texte.encode("utf-8"))


def remplacer(texte, ancien, nouveau, nom, marque):
    if marque in texte:
        print(f"[DEJA FAIT] {nom}")
        return texte, False
    if texte.count(ancien) != 1:
        print(f"[ERREUR] {nom} : repere introuvable ({texte.count(ancien)} occurrence(s)).")
        print("         Votre fichier differe de la version attendue : envoyez-le moi.")
        raise SystemExit(1)
    print(f"[OK] {nom}")
    return texte.replace(ancien, nouveau), True


# =====================================================================
# 1. MODELS
# =====================================================================
MODELE = '''

# =====================================================
# DEMANDES D'ACCES TEMPORAIRE (remplacement entre agents)
# =====================================================

class DemandeAcces(models.Model):

    class Portee(models.TextChoices):
        AGENT = "AGENT", "Tous les dossiers en cours d'un collègue"
        COURRIERS = "COURRIERS", "Courriers précis"

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        REFUSEE = "REFUSEE", "Refusée"
        ANNULEE = "ANNULEE", "Annulée par le demandeur"
        REVOQUEE = "REVOQUEE", "Révoquée"

    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="demandes_acces",
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="demandes_acces",
    )

    agent_cible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="demandes_acces_visant",
        verbose_name="Collègue remplacé",
    )

    portee = models.CharField(
        max_length=12,
        choices=Portee.choices,
        default=Portee.AGENT,
    )

    courriers = models.ManyToManyField(
        Courrier,
        blank=True,
        related_name="demandes_acces",
    )

    motif = models.TextField()
    jours_demandes = models.PositiveSmallIntegerField(default=7)

    statut = models.CharField(
        max_length=12,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
    )

    decide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="demandes_acces_decidees",
        null=True,
        blank=True,
    )

    date_decision = models.DateTimeField(null=True, blank=True)
    commentaire_decision = models.TextField(blank=True)
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Demande d'accès"
        verbose_name_plural = "Demandes d'accès"

    def est_valide(self):
        maintenant = timezone.now()
        return (
            self.statut == self.Statut.ACCEPTEE
            and self.date_debut is not None
            and self.date_fin is not None
            and self.date_debut <= maintenant <= self.date_fin
        )

    def est_expiree(self):
        return (
            self.statut == self.Statut.ACCEPTEE
            and self.date_fin is not None
            and self.date_fin < timezone.now()
        )

    def etat(self):
        if self.est_expiree():
            return "Expirée"
        return self.get_statut_display()

    def __str__(self):
        return f"Demande {self.pk} : {self.demandeur} -> {self.agent_cible}"
'''


def patch_models():
    p = APP / "models.py"
    t, crlf = lire(p)
    if "class DemandeAcces" in t:
        print("[DEJA FAIT] models.py")
        return
    ecrire(p, t.rstrip("\n") + "\n" + MODELE, crlf)
    print("[OK] models.py : DemandeAcces ajoute")


# =====================================================================
# 2. PERMISSIONS
# =====================================================================
PERM_FONCTIONS = '''

# ============================================================
# ACCES TEMPORAIRE ENTRE AGENTS (demandes d'acces validees)
# ============================================================

STATUTS_ACCES_TEMPORAIRE = [
    Courrier.Statut.TRANSMIS,
    Courrier.Statut.EN_COURS,
    Courrier.Statut.EN_ATTENTE,
    Courrier.Statut.TRAITE,
]


def demandes_acces_valides(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return DemandeAcces.objects.none()

    maintenant = timezone.now()

    return DemandeAcces.objects.filter(
        demandeur=user,
        statut=DemandeAcces.Statut.ACCEPTEE,
        date_debut__lte=maintenant,
        date_fin__gte=maintenant,
    ).select_related("agent_cible")


def demande_acces_pour_courrier(user, courrier):
    """Demande valide qui donne a l'utilisateur acces a ce courrier."""
    if (
        user is None
        or courrier is None
        or not getattr(user, "is_active", False)
        or courrier_est_confidentiel(courrier)
    ):
        return None

    for demande in demandes_acces_valides(user):
        if demande.portee == DemandeAcces.Portee.COURRIERS:
            if demande.courriers.filter(pk=courrier.pk).exists():
                return demande
        elif (
            courrier.statut in STATUTS_ACCES_TEMPORAIRE
            and Affectation.objects.filter(
                courrier=courrier,
                agent_id=demande.agent_cible_id,
                type_affectation="AGENT",
                active=True,
            ).exists()
        ):
            return demande

    return None


def agent_a_acces_temporaire(user, courrier):
    return demande_acces_pour_courrier(user, courrier) is not None


def acces_temporaire_q(user):
    """Condition Q des courriers ouverts par des demandes valides (ou None)."""
    demandes = list(demandes_acces_valides(user))

    if not demandes:
        return None

    condition = Q(pk__in=[])

    for demande in demandes:
        if demande.portee == DemandeAcces.Portee.COURRIERS:
            condition |= Q(
                pk__in=list(demande.courriers.values_list("pk", flat=True))
            )
        else:
            condition |= Q(
                affectations__agent_id=demande.agent_cible_id,
                affectations__active=True,
                affectations__type_affectation="AGENT",
                statut__in=STATUTS_ACCES_TEMPORAIRE,
            )

    return condition & ~Q(
        confidentialite__in=[
            Courrier.Confidentialite.CONFIDENTIELLE,
            Courrier.Confidentialite.STRICTE,
        ]
    ) & ~Q(priorite=Courrier.Priorite.CONFIDENTIELLE)


def libelle_remplacement(user, courrier):
    """Texte ajoute a l'historique quand un agent agit en remplacement."""
    if agent_est_affecte_au_courrier(user, courrier):
        return ""

    demande = demande_acces_pour_courrier(user, courrier)

    if demande is None:
        return ""

    nom = (
        demande.agent_cible.get_full_name()
        or demande.agent_cible.username
    )

    return f" (en remplacement de {nom}, demande n°{demande.pk})"


def utilisateur_peut_decider_demande(user, demande):
    if obtenir_profil(user) != "RESPONSABLE" or demande is None:
        return False

    return (
        services_accessibles_du_responsable(user)
        .filter(pk=demande.service_id)
        .exists()
        and responsable_peut_affecter_agents(user, demande.service)
    )
'''


def patch_permissions():
    p = APP / "permissions.py"
    t, crlf = lire(p)
    marque = "def agent_a_acces_temporaire"

    t, _ = remplacer(
        t,
        "    AutorisationConfidentialite,\n)\n",
        "    AutorisationConfidentialite,\n    DemandeAcces,\n)\n",
        "permissions.py : import", "    DemandeAcces,\n)",
    )

    ancien = (
        '    if profil == "AGENT":\n'
        "        return agent_est_affecte_au_courrier(\n"
        "            user,\n"
        "            courrier,\n"
        "        )\n"
        "\n"
        "    return False\n"
    )
    nouveau = (
        '    if profil == "AGENT":\n'
        "        return (\n"
        "            agent_est_affecte_au_courrier(user, courrier)\n"
        "            or agent_a_acces_temporaire(user, courrier)\n"
        "        )\n"
        "\n"
        "    return False\n"
    )
    t, _ = remplacer(t, ancien, nouveau, "permissions.py : consultation",
                     "or agent_a_acces_temporaire(user, courrier)\n        )\n\n    return False")

    ancien = (
        '    if profil == "AGENT":\n'
        "        return agent_est_affecte_au_courrier(\n"
        "            user,\n"
        "            courrier,\n"
        "        )\n"
        "\n"
        "    return (\n"
        "        utilisateur_est_responsable_du_courrier(\n"
    )
    nouveau = (
        '    if profil == "AGENT":\n'
        "        return (\n"
        "            agent_est_affecte_au_courrier(user, courrier)\n"
        "            or agent_a_acces_temporaire(user, courrier)\n"
        "        )\n"
        "\n"
        "    return (\n"
        "        utilisateur_est_responsable_du_courrier(\n"
    )
    t, _ = remplacer(t, ancien, nouveau, "permissions.py : traitement",
                     "or agent_a_acces_temporaire(user, courrier)\n        )\n\n    return (")

    if marque not in t:
        t = t.rstrip("\n") + "\n" + PERM_FONCTIONS
        print("[OK] permissions.py : fonctions d'acces temporaire")
    else:
        print("[DEJA FAIT] permissions.py : fonctions")

    ecrire(p, t, crlf)


# =====================================================================
# 3. VIEWS
# =====================================================================
def patch_views():
    p = APP / "views.py"
    t, crlf = lire(p)

    t, _ = remplacer(
        t,
        "    utilisateur_peut_gerer_autorisations_confidentielles,\n)\n\n\nUser = get_user_model()",
        "    utilisateur_peut_gerer_autorisations_confidentielles,\n"
        "    agent_a_acces_temporaire,\n    acces_temporaire_q,\n    libelle_remplacement,\n)\n\n\nUser = get_user_model()",
        "views.py : imports", "    acces_temporaire_q,\n")

    ancien = (
        '    if profil == "AGENT":\n'
        "        return qs.filter(\n"
        "            affectations__agent=user,\n"
        "            affectations__active=True,\n"
        '            affectations__type_affectation="AGENT",\n'
        "        ).distinct()\n"
    )
    nouveau = (
        '    if profil == "AGENT":\n'
        "        propre = Q(\n"
        "            affectations__agent=user,\n"
        "            affectations__active=True,\n"
        '            affectations__type_affectation="AGENT",\n'
        "        )\n"
        "        temporaire = acces_temporaire_q(user)\n"
        "\n"
        "        if temporaire is not None:\n"
        "            propre = propre | temporaire\n"
        "\n"
        "        return qs.filter(propre).distinct()\n"
    )
    t, _ = remplacer(t, ancien, nouveau, "views.py : liste de l'agent",
                     "temporaire = acces_temporaire_q(user)")

    ancien = (
        '    if profil == "AGENT":\n'
        "        affectations = affectations.filter(\n"
        "            agent=request.user,\n"
        '            type_affectation="AGENT",\n'
        "        )\n"
        '    elif profil == "RESPONSABLE":\n'
    )
    nouveau = (
        '    if profil == "AGENT":\n'
        "        propres = affectations.filter(\n"
        "            agent=request.user,\n"
        '            type_affectation="AGENT",\n'
        "        )\n"
        "\n"
        "        if propres.exists():\n"
        "            affectations = propres\n"
        "        elif agent_a_acces_temporaire(request.user, obj):\n"
        "            # Remplacement valide : on suit les affectations du collegue.\n"
        '            affectations = affectations.filter(type_affectation="AGENT")\n'
        "        else:\n"
        "            affectations = propres\n"
        '    elif profil == "RESPONSABLE":\n'
    )
    t, _ = remplacer(t, ancien, nouveau, "views.py : traitement en remplacement",
                     "elif agent_a_acces_temporaire(request.user, obj):")

    ancien = '                    details=f"Statut : {nouveau_statut}",\n'
    nouveau = (
        '                    details=(\n'
        '                        f"Statut : {nouveau_statut}"\n'
        "                        + libelle_remplacement(request.user, courrier)\n"
        "                    ),\n"
    )
    t, _ = remplacer(t, ancien, nouveau, "views.py : historique du remplacement",
                     "+ libelle_remplacement(request.user, courrier)")

    ecrire(p, t, crlf)


# =====================================================================
# 4. URLS
# =====================================================================
def patch_urls():
    p = APP / "urls.py"
    t, crlf = lire(p)

    t, _ = remplacer(
        t, "from . import views, bordereaux, exports\n",
        "from . import views, bordereaux, exports, acces\n",
        "urls.py : import", "bordereaux, exports, acces")

    routes = (
        "urlpatterns = [\n"
        "\n"
        "    # Demandes d'acces temporaire (remplacement entre agents)\n"
        '    path("acces/", acces.liste_demandes_acces, name="liste_demandes_acces"),\n'
        '    path("acces/nouvelle/", acces.nouvelle_demande_acces, name="nouvelle_demande_acces"),\n'
        '    path("acces/<int:pk>/decider/", acces.decider_demande_acces, name="decider_demande_acces"),\n'
        '    path("acces/<int:pk>/revoquer/", acces.revoquer_demande_acces, name="revoquer_demande_acces"),\n'
    )
    t, _ = remplacer(t, "urlpatterns = [\n", routes, "urls.py : routes",
                     "liste_demandes_acces")
    ecrire(p, t, crlf)


# =====================================================================
# 5. FICHIERS NOUVEAUX
# =====================================================================
ACCES_PY = r'''
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    Affectation,
    Courrier,
    DemandeAcces,
    Historique,
    PersonnelService,
)
from .permissions import (
    STATUTS_ACCES_TEMPORAIRE,
    courrier_est_confidentiel,
    obtenir_profil,
    services_accessibles_du_responsable,
    utilisateur_peut_decider_demande,
)

User = get_user_model()

DUREE_MAXIMUM_JOURS = 30


def nom_complet(user):
    return (user.get_full_name() or user.username) if user else ""


def services_communs(demandeur, cible):
    ids_demandeur = PersonnelService.objects.filter(
        utilisateur=demandeur, actif=True
    ).values_list("service_id", flat=True)

    return list(
        PersonnelService.objects.filter(
            utilisateur=cible, actif=True, service_id__in=ids_demandeur
        ).values_list("service_id", flat=True).order_by("service_id")
    )


# ------------------------------------------------------------
# FORMULAIRES
# ------------------------------------------------------------

class DemandeAccesForm(forms.Form):
    agent_cible = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Collègue à remplacer",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    portee = forms.ChoiceField(
        choices=DemandeAcces.Portee.choices,
        initial=DemandeAcces.Portee.AGENT,
        label="Dossiers concernés",
        widget=forms.RadioSelect(),
    )

    references = forms.CharField(
        required=False,
        label="Références des courriers (seulement pour « Courriers précis »)",
        help_text=(
            "Séparées par des virgules ou des retours à la ligne, "
            "par exemple ENT-2026-000123."
        ),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    jours = forms.IntegerField(
        min_value=1,
        max_value=DUREE_MAXIMUM_JOURS,
        initial=7,
        label=f"Durée souhaitée (jours, {DUREE_MAXIMUM_JOURS} maximum)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    motif = forms.CharField(
        label="Motif (absence, congé, surcharge...)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        self.demandeur = kwargs.pop("demandeur")
        super().__init__(*args, **kwargs)

        services = PersonnelService.objects.filter(
            utilisateur=self.demandeur, actif=True
        ).values_list("service_id", flat=True)

        self.fields["agent_cible"].queryset = (
            User.objects.filter(
                appartenances_service__service_id__in=services,
                appartenances_service__actif=True,
            )
            .exclude(pk=self.demandeur.pk)
            .distinct()
            .order_by("last_name", "first_name", "username")
        )
        self.fields["agent_cible"].label_from_instance = nom_complet

    def clean_motif(self):
        motif = self.cleaned_data["motif"].strip()
        if len(motif) < 5:
            raise forms.ValidationError("Veuillez préciser le motif.")
        return motif

    def clean(self):
        donnees = super().clean()
        cible = donnees.get("agent_cible")
        portee = donnees.get("portee")

        if not cible or not portee:
            return donnees

        communs = services_communs(self.demandeur, cible)
        if not communs:
            self.add_error(
                "agent_cible",
                "Ce collègue n'appartient pas à votre service.",
            )
            return donnees
        self.service_id = communs[0]

        self.courriers_trouves = []

        if portee == DemandeAcces.Portee.COURRIERS:
            brutes = (donnees.get("references") or "").replace(",", "\n")
            references = []
            for ligne in brutes.splitlines():
                ref = ligne.strip().upper()
                if ref and ref not in references:
                    references.append(ref)

            if not references:
                self.add_error(
                    "references",
                    "Indiquez au moins une référence de courrier.",
                )
                return donnees

            if len(references) > 100:
                self.add_error(
                    "references", "100 courriers au maximum par demande."
                )
                return donnees

            trouves = {
                c.reference: c
                for c in Courrier.objects.filter(
                    reference__in=references,
                    affectations__agent=cible,
                    affectations__active=True,
                    affectations__type_affectation="AGENT",
                ).distinct()
            }
            inconnus = [r for r in references if r not in trouves]
            if inconnus:
                self.add_error(
                    "references",
                    "Non trouvés chez ce collègue : " + ", ".join(inconnus[:10]),
                )
                return donnees

            self.courriers_trouves = list(trouves.values())

        elif DemandeAcces.objects.filter(
            demandeur=self.demandeur,
            agent_cible=cible,
            portee=DemandeAcces.Portee.AGENT,
            statut=DemandeAcces.Statut.EN_ATTENTE,
        ).exists():
            self.add_error(
                None,
                "Une demande identique est déjà en attente de validation.",
            )

        return donnees


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[("ACCEPTER", "Accepter"), ("REFUSER", "Refuser")],
        label="Décision",
        widget=forms.RadioSelect(),
    )

    jours = forms.IntegerField(
        min_value=1,
        max_value=DUREE_MAXIMUM_JOURS,
        label="Durée accordée (jours)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    commentaire = forms.CharField(
        required=False,
        label="Commentaire",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def clean(self):
        donnees = super().clean()
        if (
            donnees.get("decision") == "REFUSER"
            and not (donnees.get("commentaire") or "").strip()
        ):
            self.add_error(
                "commentaire", "Indiquez la raison du refus."
            )
        return donnees


# ------------------------------------------------------------
# OUTILS
# ------------------------------------------------------------

def courriers_de_la_demande(demande):
    if demande.portee == DemandeAcces.Portee.COURRIERS:
        return demande.courriers.all()

    return Courrier.objects.filter(
        affectations__agent=demande.agent_cible,
        affectations__active=True,
        affectations__type_affectation="AGENT",
        statut__in=STATUTS_ACCES_TEMPORAIRE,
    ).exclude(
        confidentialite__in=[
            Courrier.Confidentialite.CONFIDENTIELLE,
            Courrier.Confidentialite.STRICTE,
        ]
    ).exclude(
        priorite=Courrier.Priorite.CONFIDENTIELLE
    ).distinct()


def tracer(demande, utilisateur, action, details):
    lignes = [
        Historique(
            courrier=c,
            utilisateur=utilisateur,
            action=action,
            details=details,
            motif=demande.motif,
        )
        for c in courriers_de_la_demande(demande)
        if not courrier_est_confidentiel(c)
    ]
    Historique.objects.bulk_create(lignes, batch_size=500)


def demandes_a_decider(user):
    if obtenir_profil(user) != "RESPONSABLE":
        return DemandeAcces.objects.none()

    return DemandeAcces.objects.filter(
        statut=DemandeAcces.Statut.EN_ATTENTE,
        service__in=services_accessibles_du_responsable(user),
    )


# ------------------------------------------------------------
# VUES
# ------------------------------------------------------------

@login_required
def liste_demandes_acces(request):
    profil = obtenir_profil(request.user)
    base = DemandeAcces.objects.select_related(
        "demandeur", "agent_cible", "service", "decide_par"
    )

    if profil == "AGENT":
        qs = base.filter(demandeur=request.user)
    elif profil == "RESPONSABLE":
        qs = base.filter(
            service__in=services_accessibles_du_responsable(request.user)
        )
    elif profil == "ADMIN":
        qs = base
    else:
        raise PermissionDenied(
            "Cette page est réservée aux agents et aux responsables."
        )

    demandes = list(qs[:200])
    for d in demandes:
        d.peut_decider = (
            d.statut == DemandeAcces.Statut.EN_ATTENTE
            and utilisateur_peut_decider_demande(request.user, d)
        )
        d.peut_revoquer = (
            d.est_valide()
            and utilisateur_peut_decider_demande(request.user, d)
        )
        d.peut_annuler = (
            d.statut == DemandeAcces.Statut.EN_ATTENTE
            and d.demandeur_id == request.user.pk
        )

    return render(request, "courrier/acces_liste.html", {
        "demandes": demandes,
        "profil": profil,
    })


@login_required
def nouvelle_demande_acces(request):
    if obtenir_profil(request.user) != "AGENT":
        raise PermissionDenied(
            "Seuls les agents peuvent demander un accès temporaire."
        )

    if request.method == "POST":
        form = DemandeAccesForm(request.POST, demandeur=request.user)

        if form.is_valid():
            with transaction.atomic():
                demande = DemandeAcces.objects.create(
                    demandeur=request.user,
                    service_id=form.service_id,
                    agent_cible=form.cleaned_data["agent_cible"],
                    portee=form.cleaned_data["portee"],
                    motif=form.cleaned_data["motif"],
                    jours_demandes=form.cleaned_data["jours"],
                )
                if form.courriers_trouves:
                    demande.courriers.set(form.courriers_trouves)

            messages.success(
                request,
                "Votre demande a été envoyée au responsable du service.",
            )
            return redirect("liste_demandes_acces")
    else:
        form = DemandeAccesForm(demandeur=request.user)

    return render(request, "courrier/formulaire.html", {
        "form": form,
        "titre": "Demander l'accès aux dossiers d'un collègue",
        "libelle_bouton": "Envoyer la demande",
    })


@login_required
def decider_demande_acces(request, pk):
    demande = get_object_or_404(
        DemandeAcces.objects.select_related(
            "demandeur", "agent_cible", "service"
        ),
        pk=pk,
    )

    if not utilisateur_peut_decider_demande(request.user, demande):
        raise PermissionDenied(
            "Vous ne pouvez pas décider de cette demande."
        )

    if demande.statut != DemandeAcces.Statut.EN_ATTENTE:
        messages.info(request, "Cette demande a déjà été traitée.")
        return redirect("liste_demandes_acces")

    if request.method == "POST":
        form = DecisionForm(request.POST)

        if form.is_valid():
            decision = form.cleaned_data["decision"]

            with transaction.atomic():
                demande = (
                    DemandeAcces.objects.select_for_update().get(pk=pk)
                )

                if demande.statut != DemandeAcces.Statut.EN_ATTENTE:
                    raise PermissionDenied("Cette demande a déjà été traitée.")

                maintenant = timezone.now()
                demande.decide_par = request.user
                demande.date_decision = maintenant
                demande.commentaire_decision = (
                    form.cleaned_data["commentaire"].strip()
                )

                if decision == "ACCEPTER":
                    jours = form.cleaned_data["jours"]
                    demande.statut = DemandeAcces.Statut.ACCEPTEE
                    demande.date_debut = maintenant
                    demande.date_fin = maintenant + timedelta(days=jours)
                    demande.save()

                    tracer(
                        demande,
                        request.user,
                        "ACCES_TEMPORAIRE_ACCORDE",
                        (
                            f"Accès temporaire accordé à "
                            f"{nom_complet(demande.demandeur)} "
                            f"(remplacement de {nom_complet(demande.agent_cible)}) "
                            f"jusqu'au {demande.date_fin:%d/%m/%Y %H:%M}, "
                            f"demande n°{demande.pk}."
                        ),
                    )
                    messages.success(
                        request,
                        f"Accès accordé à {nom_complet(demande.demandeur)} "
                        f"pour {jours} jour(s).",
                    )
                else:
                    demande.statut = DemandeAcces.Statut.REFUSEE
                    demande.save()
                    messages.success(request, "La demande a été refusée.")

            return redirect("liste_demandes_acces")
    else:
        form = DecisionForm(initial={
            "decision": "ACCEPTER",
            "jours": min(demande.jours_demandes, DUREE_MAXIMUM_JOURS),
        })

    return render(request, "courrier/acces_decision.html", {
        "demande": demande,
        "form": form,
        "nombre_courriers": courriers_de_la_demande(demande).count(),
        "courriers_cites": (
            demande.courriers.all()[:20]
            if demande.portee == DemandeAcces.Portee.COURRIERS else []
        ),
    })


@login_required
def revoquer_demande_acces(request, pk):
    if request.method != "POST":
        raise PermissionDenied("Cette action doit être effectuée par formulaire.")

    with transaction.atomic():
        demande = get_object_or_404(
            DemandeAcces.objects.select_for_update().select_related(
                "demandeur", "agent_cible", "service"
            ),
            pk=pk,
        )

        if (
            demande.statut == DemandeAcces.Statut.EN_ATTENTE
            and demande.demandeur_id == request.user.pk
        ):
            demande.statut = DemandeAcces.Statut.ANNULEE
            demande.save(update_fields=["statut"])
            messages.success(request, "Votre demande a été annulée.")

        elif (
            demande.est_valide()
            and utilisateur_peut_decider_demande(request.user, demande)
        ):
            demande.statut = DemandeAcces.Statut.REVOQUEE
            demande.date_fin = timezone.now()
            demande.save(update_fields=["statut", "date_fin"])
            tracer(
                demande,
                request.user,
                "ACCES_TEMPORAIRE_REVOQUE",
                (
                    f"Accès temporaire de {nom_complet(demande.demandeur)} "
                    f"révoqué, demande n°{demande.pk}."
                ),
            )
            messages.success(request, "L'accès temporaire a été révoqué.")

        else:
            raise PermissionDenied("Vous ne pouvez pas modifier cette demande.")

    return redirect("liste_demandes_acces")
'''

ADMIN_ACCES = '''
from django.contrib import admin

from .models import DemandeAcces


@admin.register(DemandeAcces)
class DemandeAccesAdmin(admin.ModelAdmin):
    list_display = (
        "id", "demandeur", "agent_cible", "service", "portee",
        "statut", "date_creation", "date_fin",
    )
    list_filter = ("statut", "portee", "service")
    search_fields = (
        "demandeur__username", "agent_cible__username", "motif",
    )
    readonly_fields = ("date_creation",)
'''

TAGS_PY = '''
from django import template

from courrier.models import DemandeAcces
from courrier.permissions import (
    demande_acces_pour_courrier,
    demandes_acces_valides,
    obtenir_profil,
)

register = template.Library()


@register.inclusion_tag("courrier/_bandeau_acces.html", takes_context=True)
def bandeau_acces(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    profil = obtenir_profil(user) if user is not None else None
    donnees = {"profil": profil}

    if profil == "AGENT":
        donnees["acces_valides"] = list(demandes_acces_valides(user))
        donnees["en_attente"] = DemandeAcces.objects.filter(
            demandeur=user, statut=DemandeAcces.Statut.EN_ATTENTE
        ).count()

        courrier = context.get("courrier")
        if courrier is not None and hasattr(courrier, "pk"):
            donnees["remplacement"] = demande_acces_pour_courrier(user, courrier)

    elif profil == "RESPONSABLE":
        from courrier.acces import demandes_a_decider

        donnees["a_decider"] = demandes_a_decider(user).count()

    return donnees
'''

BANDEAU_HTML = '''{% if profil == "AGENT" %}
<div class="alert alert-light border d-flex flex-wrap align-items-center gap-2 py-2 mb-3">
  {% if remplacement %}
    <span class="badge text-bg-warning">Remplacement</span>
    <span>Accès temporaire : vous agissez en remplacement de
      <strong>{{ remplacement.agent_cible.get_full_name|default:remplacement.agent_cible.username }}</strong>
      jusqu'au {{ remplacement.date_fin|date:"d/m/Y H:i" }}.</span>
  {% else %}
    {% for a in acces_valides %}
      <span class="badge text-bg-warning">Remplacement</span>
      <span>Vous remplacez {{ a.agent_cible.get_full_name|default:a.agent_cible.username }} jusqu'au {{ a.date_fin|date:"d/m/Y" }}.</span>
    {% endfor %}
  {% endif %}
  <span class="ms-auto d-flex gap-2">
    <a class="btn btn-sm btn-outline-primary" href="{% url 'nouvelle_demande_acces' %}">Demander l'accès à d'autres dossiers</a>
    <a class="btn btn-sm btn-outline-secondary" href="{% url 'liste_demandes_acces' %}">Mes demandes{% if en_attente %} ({{ en_attente }}){% endif %}</a>
  </span>
</div>
{% elif profil == "RESPONSABLE" and a_decider %}
<div class="alert alert-warning d-flex align-items-center gap-2 py-2 mb-3">
  <span><strong>{{ a_decider }}</strong> demande{{ a_decider|pluralize }} d'accès en attente de votre décision.</span>
  <a class="btn btn-sm btn-warning ms-auto" href="{% url 'liste_demandes_acces' %}">Examiner</a>
</div>
{% endif %}
'''

LISTE_HTML = '''{% extends "__BASE__" %}
{% block __BLOCK__ %}
<div class="d-flex align-items-center mb-3">
  <h2 class="h4 mb-0">Demandes d'accès temporaire</h2>
  {% if profil == "AGENT" %}
  <a class="btn btn-primary ms-auto" href="{% url 'nouvelle_demande_acces' %}">Nouvelle demande</a>
  {% endif %}
</div>

{% if messages %}{% for m in messages %}<div class="alert alert-{{ m.tags }}">{{ m }}</div>{% endfor %}{% endif %}

<div class="table-responsive">
<table class="table table-sm align-middle">
  <thead>
    <tr><th>N°</th><th>Demandeur</th><th>Collègue remplacé</th><th>Dossiers</th><th>Motif</th><th>État</th><th>Validité</th><th></th></tr>
  </thead>
  <tbody>
  {% for d in demandes %}
    <tr>
      <td>{{ d.pk }}</td>
      <td>{{ d.demandeur.get_full_name|default:d.demandeur.username }}</td>
      <td>{{ d.agent_cible.get_full_name|default:d.agent_cible.username }}</td>
      <td>{{ d.get_portee_display }}</td>
      <td>{{ d.motif|truncatechars:60 }}</td>
      <td>{{ d.etat }}{% if d.commentaire_decision %}<br><small class="text-muted">{{ d.commentaire_decision|truncatechars:60 }}</small>{% endif %}</td>
      <td>{% if d.date_fin %}jusqu'au {{ d.date_fin|date:"d/m/Y H:i" }}{% else %}{{ d.jours_demandes }} j demandé(s){% endif %}</td>
      <td class="text-end">
        {% if d.peut_decider %}<a class="btn btn-sm btn-warning" href="{% url 'decider_demande_acces' d.pk %}">Examiner</a>{% endif %}
        {% if d.peut_revoquer or d.peut_annuler %}
        <form method="post" action="{% url 'revoquer_demande_acces' d.pk %}" class="d-inline">
          {% csrf_token %}
          <button class="btn btn-sm btn-outline-danger" type="submit">{% if d.peut_annuler %}Annuler{% else %}Révoquer{% endif %}</button>
        </form>
        {% endif %}
      </td>
    </tr>
  {% empty %}
    <tr><td colspan="8" class="text-muted">Aucune demande.</td></tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
'''

DECISION_HTML = '''{% extends "__BASE__" %}
{% block __BLOCK__ %}
<h2 class="h4 mb-3">Demande d'accès n°{{ demande.pk }}</h2>

<dl class="row">
  <dt class="col-sm-3">Demandeur</dt><dd class="col-sm-9">{{ demande.demandeur.get_full_name|default:demande.demandeur.username }}</dd>
  <dt class="col-sm-3">Remplace</dt><dd class="col-sm-9">{{ demande.agent_cible.get_full_name|default:demande.agent_cible.username }}</dd>
  <dt class="col-sm-3">Service</dt><dd class="col-sm-9">{{ demande.service }}</dd>
  <dt class="col-sm-3">Dossiers</dt><dd class="col-sm-9">{{ demande.get_portee_display }} ({{ nombre_courriers }} courrier{{ nombre_courriers|pluralize }}, hors confidentiels)</dd>
  <dt class="col-sm-3">Motif</dt><dd class="col-sm-9">{{ demande.motif|linebreaksbr }}</dd>
  <dt class="col-sm-3">Durée demandée</dt><dd class="col-sm-9">{{ demande.jours_demandes }} jour(s)</dd>
</dl>

{% if courriers_cites %}
<p class="mb-1"><strong>Courriers cités :</strong></p>
<ul>{% for c in courriers_cites %}<li>{{ c.reference }} – {{ c.objet|truncatechars:70 }}</li>{% endfor %}</ul>
{% endif %}

<div class="alert alert-info">
  Le demandeur pourra consulter et traiter ces courriers pendant la durée accordée.
  Il ne pourra ni les clôturer ni les retourner. Les courriers confidentiels restent exclus.
</div>

<form method="post">
  {% csrf_token %}
  {{ form.non_field_errors }}
  <div class="mb-3">{{ form.decision.label_tag }}{{ form.decision }}{{ form.decision.errors }}</div>
  <div class="mb-3">{{ form.jours.label_tag }}{{ form.jours }}{{ form.jours.errors }}</div>
  <div class="mb-3">{{ form.commentaire.label_tag }}{{ form.commentaire }}{{ form.commentaire.errors }}</div>
  <button class="btn btn-primary" type="submit">Valider ma décision</button>
  <a class="btn btn-outline-secondary" href="{% url 'liste_demandes_acces' %}">Retour</a>
</form>
{% endblock %}
'''


def trouver_gabarits():
    candidats = list(BASE.glob("**/templates/courrier/formulaire.html"))
    candidats = [c for c in candidats if ".venv" not in c.parts]
    return candidats[0].parent if candidats else None


def detecter_base(dossier):
    formulaire = dossier / "formulaire.html"
    texte = formulaire.read_text(encoding="utf-8-sig") if formulaire.exists() else ""
    m = re.search(r"""{%\s*extends\s+["']([^"']+)["']\s*%}""", texte)
    base = m.group(1) if m else "base.html"
    blocs = re.findall(r"{%\s*block\s+(\w+)\s*%}", texte)
    bloc = "content"
    for b in blocs:
        if b not in ("title", "titre", "extra_css", "extra_js", "head", "scripts"):
            bloc = b
            break
    return base, bloc


def creer_fichiers():
    ecrire(APP / "acces.py", ACCES_PY.lstrip("\n"), False)
    print("[OK] courrier/acces.py")
    ecrire(APP / "admin_acces.py", ADMIN_ACCES.lstrip("\n"), False)
    print("[OK] courrier/admin_acces.py")

    tags = APP / "templatetags"
    tags.mkdir(exist_ok=True)
    (tags / "__init__.py").touch()
    ecrire(tags / "gsc_acces.py", TAGS_PY.lstrip("\n"), False)
    print("[OK] courrier/templatetags/gsc_acces.py")

    admin = APP / "admin.py"
    if admin.exists():
        t, crlf = lire(admin)
        if "admin_acces" not in t:
            ecrire(admin, t.rstrip("\n") + "\n\nfrom . import admin_acces  # noqa: E402,F401\n", crlf)
            print("[OK] admin.py : demandes d'acces ajoutees")
        else:
            print("[DEJA FAIT] admin.py")

    dossier = trouver_gabarits()
    if dossier is None:
        print("[ATTENTION] gabarits introuvables (courrier/templates/courrier/formulaire.html).")
        print("            Les pages d'acces ne s'afficheront pas : envoyez-moi votre dossier templates.")
        return

    base, bloc = detecter_base(dossier)
    print(f"[INFO] gabarit de base : {base}  (bloc {bloc})")

    for nom, contenu in (
        ("acces_liste.html", LISTE_HTML),
        ("acces_decision.html", DECISION_HTML),
    ):
        (dossier / nom).write_text(
            contenu.replace("__BASE__", base).replace("__BLOCK__", bloc),
            encoding="utf-8",
        )
        print(f"[OK] {nom}")

    (dossier / "_bandeau_acces.html").write_text(BANDEAU_HTML, encoding="utf-8")
    print("[OK] _bandeau_acces.html")

    for nom in ("liste.html", "detail.html"):
        f = dossier / nom
        if not f.exists():
            print(f"[A FAIRE A LA MAIN] {nom} introuvable : ajoutez "
                  "{% load gsc_acces %} puis {% bandeau_acces %} en haut du contenu.")
            continue
        t, crlf = lire(f)
        if "bandeau_acces" in t:
            print(f"[DEJA FAIT] {nom}")
            continue
        m_ext = re.search(r"{%\s*extends[^%]*%}\n?", t)
        m_blk = re.search(r"{%\s*block\s+" + bloc + r"\s*%}\n?", t)
        if not m_ext or not m_blk:
            print(f"[A FAIRE A LA MAIN] {nom} : structure inattendue. Ajoutez "
                  "{% load gsc_acces %} apres extends puis {% bandeau_acces %} dans le bloc " + bloc + ".")
            continue
        t = (
            t[:m_ext.end()] + "{% load gsc_acces %}\n" + t[m_ext.end():m_blk.end()]
            + "{% bandeau_acces %}\n" + t[m_blk.end():]
        )
        ecrire(f, t, crlf)
        print(f"[OK] {nom} : bandeau ajoute")


patch_models()
patch_permissions()
patch_views()
patch_urls()
creer_fichiers()

print("""
Etape suivante :
  python manage.py makemigrations courrier
  python manage.py migrate
""")
