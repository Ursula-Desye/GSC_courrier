from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Courrier,
    Affectation,
    Historique,
    Service,
    BordereauTransmission,
    LigneBordereau,
    ReceptionBordereau,
)

from .permissions import (
    obtenir_profil,
    utilisateur_est_responsable_du_service,
    utilisateur_peut_transmettre,
    utilisateur_peut_consulter_contenu_courrier,
)


# ============================================================
# FORMULAIRE DE CREATION D'UN BORDEREAU
# ============================================================

class CreationBordereauForm(forms.Form):

    service = forms.ModelChoiceField(
        queryset=Service.objects.none(),
        label="Service destinataire",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    courriers = forms.ModelMultipleChoiceField(
        queryset=Courrier.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Courriers à transmettre",
    )

    instruction = forms.CharField(
        required=False,
        label="Instruction de transmission",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "class": "form-control",
            "placeholder": "Instructions destinées au service...",
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user

        services = Service.objects.filter(
            actif=True,
            responsable__isnull=False,
            responsable__is_active=True,
        ).select_related("responsable").order_by("nom")

        self.fields["service"].queryset = services

        if user and user.is_authenticated:

            from .views import courriers_accessibles

            accessibles = courriers_accessibles(user)

            self.fields["courriers"].queryset = (
                accessibles
                .filter(
                    sens=Courrier.Sens.ENTRANT,
                    statut=Courrier.Statut.ENREGISTRE,
                )
                .exclude(affectations__active=True)
                .distinct()
                .order_by("-cree_le", "-pk")
            )

    def clean(self):

        cleaned = super().clean()

        service = cleaned.get("service")
        courriers = cleaned.get("courriers")

        if service:
            if (
                not service.actif
                or not service.responsable_id
                or not service.responsable.is_active
            ):
                self.add_error(
                    "service",
                    "Le service doit être actif et posséder un responsable actif.",
                )

        if service and courriers:

            for courrier in courriers:

                if not utilisateur_peut_transmettre(
                    self.user,
                    courrier,
                ):
                    self.add_error(
                        "courriers",
                        (
                            "Vous n'êtes pas autorisé à transmettre "
                            f"le courrier {courrier.reference}."
                        ),
                    )
                    continue

                if courrier.sens != Courrier.Sens.ENTRANT:
                    self.add_error(
                        "courriers",
                        f"Le courrier {courrier.reference} n'est pas entrant.",
                    )

                if courrier.statut != Courrier.Statut.ENREGISTRE:
                    self.add_error(
                        "courriers",
                        f"Le courrier {courrier.reference} n'est plus disponible.",
                    )

                if Affectation.objects.filter(
                    courrier=courrier,
                    active=True,
                ).exists():
                    self.add_error(
                        "courriers",
                        (
                            f"Le courrier {courrier.reference} possède déjà "
                            "une transmission active."
                        ),
                    )

                if (
                    courrier.service_id
                    and courrier.service_id != service.pk
                ):
                    self.add_error(
                        "courriers",
                        (
                            f"Le courrier {courrier.reference} est déjà "
                            "rattaché à un autre service."
                        ),
                    )

        return cleaned


# ============================================================
# FORMULAIRE DE RECEPTION
# ============================================================

class ReceptionBordereauForm(forms.Form):

    observation = forms.CharField(
        required=False,
        label="Observation à la réception",
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "form-control",
            "placeholder": "Observations éventuelles...",
        }),
    )


# ============================================================
# HISTORIQUE
# ============================================================

def enregistrer_historique_bordereau(
    courrier,
    utilisateur,
    action,
    details,
):
    Historique.objects.create(
        courrier=courrier,
        utilisateur=utilisateur,
        action=action,
        details=details,
    )


# ============================================================
# LISTE DES BORDEREAUX
# ============================================================

@login_required
def liste_bordereaux(request):

    profil = obtenir_profil(request.user)

    profils_autorises = [
        "ADMIN",
        "DIRECTION",
        "ACCUEIL",
        "SECRETARIAT",
        "RESPONSABLE",
    ]

    if profil not in profils_autorises:
        raise PermissionDenied

    from .views import courriers_accessibles

    accessibles = courriers_accessibles(request.user)

    lignes_accessibles = (
        LigneBordereau.objects
        .filter(courrier__in=accessibles)
        .select_related("courrier")
        .order_by("pk")
    )

    bordereaux = (
        BordereauTransmission.objects
        .select_related("service", "transmis_par")
        .prefetch_related(
            Prefetch(
                "lignes",
                queryset=lignes_accessibles,
                to_attr="lignes_accessibles",
            )
        )
        .filter(lignes__courrier__in=accessibles)
        .distinct()
        .order_by("-date_transmission", "-pk")
    )

    if profil == "RESPONSABLE":

        # Le contrôle tient compte des responsables déclarés dans
        # ResponsableService ainsi que de l'ancien champ responsable.
        services_responsable = [
            service.pk
            for service in Service.objects.filter(actif=True)
            if utilisateur_est_responsable_du_service(
                request.user,
                service,
            )
        ]

        bordereaux = bordereaux.filter(
            service_id__in=services_responsable,
            service__actif=True,
        )

    return render(
        request,
        "courrier/bordereaux/liste.html",
        {
            "bordereaux": bordereaux,
            "profil": profil,
        },
    )


# ============================================================
# CREATION D'UN BORDEREAU
# ============================================================

@login_required
def creer_bordereau(request):

    profil = obtenir_profil(request.user)

    if profil not in ["ACCUEIL", "SECRETARIAT"]:
        raise PermissionDenied

    if request.method == "POST":

        form = CreationBordereauForm(
            request.POST,
            user=request.user,
        )

        if form.is_valid():

            service_selectionne = form.cleaned_data["service"]
            courriers_selectionnes = form.cleaned_data["courriers"]
            instruction = form.cleaned_data["instruction"]

            identifiants = list(
                courriers_selectionnes.values_list("pk", flat=True)
            )

            if not identifiants:
                messages.error(
                    request,
                    "Sélectionnez au moins un courrier.",
                )

                return render(
                    request,
                    "courrier/bordereaux/formulaire.html",
                    {"form": form},
                )

            try:

                with transaction.atomic():

                    service = (
                        Service.objects
                        .select_for_update()
                        .select_related("responsable")
                        .get(pk=service_selectionne.pk)
                    )

                    if (
                        not service.actif
                        or not service.responsable_id
                        or not service.responsable.is_active
                    ):
                        raise PermissionDenied(
                            "Le service destinataire ou son responsable "
                            "n'est plus actif."
                        )

                    courriers_verrouilles = list(
                        Courrier.objects
                        .select_for_update()
                        .filter(pk__in=identifiants)
                        .order_by("pk")
                    )

                    if len(courriers_verrouilles) != len(set(identifiants)):
                        raise PermissionDenied

                    for courrier in courriers_verrouilles:

                        if not utilisateur_peut_transmettre(
                            request.user,
                            courrier,
                        ):
                            raise PermissionDenied

                        if courrier.sens != Courrier.Sens.ENTRANT:
                            raise PermissionDenied

                        if courrier.statut != Courrier.Statut.ENREGISTRE:
                            raise PermissionDenied

                        if Affectation.objects.filter(
                            courrier=courrier,
                            active=True,
                        ).exists():
                            raise PermissionDenied

                        if (
                            courrier.service_id
                            and courrier.service_id != service.pk
                        ):
                            raise PermissionDenied

                    bordereau = BordereauTransmission.objects.create(
                        service=service,
                        transmis_par=request.user,
                    )

                    for courrier in courriers_verrouilles:

                        LigneBordereau.objects.create(
                            bordereau=bordereau,
                            courrier=courrier,
                        )

                        Affectation.objects.create(
                            courrier=courrier,
                            service=service,
                            agent=None,
                            transmis_par=request.user,
                            date_transmission=timezone.now(),
                            instruction=instruction,
                            active=True,
                            statut="TRANSMIS",
                        )

                        courrier.service = service
                        courrier.responsable = service.responsable
                        courrier.statut = Courrier.Statut.TRANSMIS

                        courrier.save(
                            update_fields=[
                                "service",
                                "responsable",
                                "statut",
                                "modifie_le",
                            ]
                        )

                        enregistrer_historique_bordereau(
                            courrier,
                            request.user,
                            "TRANSMISSION_BORDEREAU",
                            (
                                f"Courrier transmis au service {service.nom} "
                                f"par le bordereau numéro {bordereau.pk}."
                            ),
                        )

            except PermissionDenied:
                raise

            messages.success(
                request,
                (
                    f"Bordereau numéro {bordereau.pk} créé avec succès. "
                    f"{len(courriers_verrouilles)} courrier(s) transmis."
                ),
            )

            return redirect(
                "detail_bordereau",
                pk=bordereau.pk,
            )

    else:

        form = CreationBordereauForm(user=request.user)

    return render(
        request,
        "courrier/bordereaux/formulaire.html",
        {"form": form},
    )


# ============================================================
# DETAIL D'UN BORDEREAU
# ============================================================

@login_required
def detail_bordereau(request, pk):

    profil = obtenir_profil(request.user)

    bordereau = get_object_or_404(
        BordereauTransmission.objects.select_related(
            "service",
            "transmis_par",
        ),
        pk=pk,
    )

    autorise = (
        profil in [
            "ADMIN",
            "DIRECTION",
            "ACCUEIL",
            "SECRETARIAT",
        ]
        or (
            profil == "RESPONSABLE"
            and utilisateur_est_responsable_du_service(
                request.user,
                bordereau.service,
            )
        )
    )

    if not autorise:
        raise PermissionDenied

    from .views import courriers_accessibles

    accessibles = courriers_accessibles(request.user)

    lignes = list(
        LigneBordereau.objects
        .filter(
            bordereau=bordereau,
            courrier__in=accessibles,
        )
        .select_related("courrier")
        .order_by("pk")
    )

    if not lignes:
        raise PermissionDenied

    # Chaque ligne reçoit un indicateur de consultation du contenu.
    # Le template doit respecter cet indicateur avant d'afficher
    # l'expéditeur et l'objet du courrier.
    for ligne in lignes:

        ligne.peut_voir_contenu = (
            utilisateur_peut_consulter_contenu_courrier(
                request.user,
                ligne.courrier,
            )
        )

    peut_receptionner = (
        profil == "RESPONSABLE"
        and bordereau.service.actif
        and utilisateur_est_responsable_du_service(
            request.user,
            bordereau.service,
        )
        and bordereau.statut == "TRANSMIS"
    )

    reception = getattr(bordereau, "reception", None)

    return render(
        request,
        "courrier/bordereaux/detail.html",
        {
            "bordereau": bordereau,
            "lignes": lignes,
            "reception": reception,
            "peut_receptionner": peut_receptionner,
            "reception_form": ReceptionBordereauForm(),
        },
    )


# ============================================================
# RECEPTION COLLECTIVE D'UN BORDEREAU
# ============================================================

@login_required
@require_POST
def receptionner_bordereau(request, pk):

    profil = obtenir_profil(request.user)

    if profil != "RESPONSABLE":
        raise PermissionDenied

    form = ReceptionBordereauForm(request.POST)

    if not form.is_valid():

        messages.error(
            request,
            "Les informations de réception sont invalides.",
        )

        return redirect("detail_bordereau", pk=pk)

    with transaction.atomic():

        bordereau = (
            BordereauTransmission.objects
            .select_for_update()
            .select_related("service")
            .filter(pk=pk)
            .first()
        )

        if not bordereau:
            raise PermissionDenied

        if not utilisateur_est_responsable_du_service(
            request.user,
            bordereau.service,
        ):
            raise PermissionDenied

        if not bordereau.service.actif:
            raise PermissionDenied

        if bordereau.statut != "TRANSMIS":

            messages.warning(
                request,
                "Ce bordereau a déjà été réceptionné.",
            )

            return redirect("detail_bordereau", pk=pk)

        lignes = list(
            LigneBordereau.objects
            .filter(bordereau=bordereau)
            .select_related("courrier")
            .order_by("pk")
        )

        if not lignes:

            messages.error(
                request,
                "Ce bordereau ne contient aucun courrier.",
            )

            return redirect("detail_bordereau", pk=pk)

        courriers_ids = [ligne.courrier_id for ligne in lignes]

        courriers_verrouilles = {
            courrier.pk: courrier
            for courrier in (
                Courrier.objects
                .select_for_update()
                .filter(pk__in=courriers_ids)
                .order_by("pk")
            )
        }

        if len(courriers_verrouilles) != len(set(courriers_ids)):
            raise PermissionDenied

        affectations = {}

        for ligne in lignes:

            courrier = courriers_verrouilles[ligne.courrier_id]

            if (
                courrier.service_id != bordereau.service_id
                or courrier.statut != Courrier.Statut.TRANSMIS
            ):
                raise PermissionDenied

            affectation = (
                Affectation.objects
                .select_for_update()
                .filter(
                    courrier=courrier,
                    service=bordereau.service,
                    active=True,
                )
                .order_by("-date_transmission", "-pk")
                .first()
            )

            if not affectation:
                raise PermissionDenied

            affectations[courrier.pk] = affectation

        ReceptionBordereau.objects.create(
            bordereau=bordereau,
            service=bordereau.service,
            receptionne_par=request.user,
            observation=form.cleaned_data["observation"],
        )

        bordereau.statut = "RECEPTIONNE"
        bordereau.save(update_fields=["statut"])

        for ligne in lignes:

            courrier = courriers_verrouilles[ligne.courrier_id]
            affectation = affectations[courrier.pk]

            if not affectation.date_confirmation_reception:

                affectation.date_confirmation_reception = timezone.now()
                affectation.confirme_par = request.user

                affectation.save(
                    update_fields=[
                        "date_confirmation_reception",
                        "confirme_par",
                    ]
                )

            enregistrer_historique_bordereau(
                courrier,
                request.user,
                "RECEPTION_BORDEREAU",
                (
                    f"Réception confirmée par {request.user} "
                    f"pour le bordereau numéro {bordereau.pk}."
                ),
            )

    messages.success(
        request,
        "La réception du bordereau et de tous ses courriers "
        "a été enregistrée.",
    )

    return redirect("detail_bordereau", pk=pk)