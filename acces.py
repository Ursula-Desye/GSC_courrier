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
