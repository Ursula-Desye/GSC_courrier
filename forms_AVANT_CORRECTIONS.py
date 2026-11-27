
from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    Courrier,
    Affectation,
    Service,
    CategorieCourrier,
)
from .permissions import (
    obtenir_profil,
    services_accessibles_du_responsable,
)


User = get_user_model()


# ============================================================
# VALIDATION DES FICHIERS
# ============================================================

EXTENSIONS_AUTORISEES = {
    ".pdf", ".doc", ".docx",
    ".xls", ".xlsx",
    ".jpg", ".jpeg", ".png",
}

TAILLE_MAXIMALE_FICHIER = 20 * 1024 * 1024


def valider_fichier(fichier):
    if not fichier:
        return fichier

    extension = Path(fichier.name).suffix.lower()

    if extension not in EXTENSIONS_AUTORISEES:
        raise forms.ValidationError(
            "Format non autorisé. Formats acceptés : "
            "PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG et PNG."
        )

    if fichier.size > TAILLE_MAXIMALE_FICHIER:
        raise forms.ValidationError(
            "Le fichier ne doit pas dépasser 20 Mo."
        )

    return fichier


# ============================================================
# TELEVERSEMENT MULTIPLE
# ============================================================

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []

        fichiers = data if isinstance(data, (list, tuple)) else [data]
        fichiers_valides = []

        for fichier in fichiers:
            fichier_valide = super().clean(fichier, initial)

            if fichier_valide:
                fichiers_valides.append(
                    valider_fichier(fichier_valide)
                )

        return fichiers_valides


# ============================================================
# SERVICES ACCESSIBLES
# ============================================================

def obtenir_services_accessibles(user):
    services = Service.objects.filter(actif=True)

    if not user or not user.is_authenticated:
        return services.none()

    profil = obtenir_profil(user)

    if profil == "RESPONSABLE":
        accessibles = services_accessibles_du_responsable(user)

        if hasattr(accessibles, "values_list"):
            identifiants = accessibles.values_list("pk", flat=True)
        else:
            identifiants = [
                service.pk for service in accessibles
            ]

        return services.filter(pk__in=identifiants)

    return services


def obtenir_responsables_service(service):
    if not service:
        return User.objects.none()

    responsables_multi = User.objects.filter(
        responsabilites_services__service=service,
        responsabilites_services__actif=True,
        is_active=True,
    )

    responsables_anciens = User.objects.none()

    if service.responsable_id:
        responsables_anciens = User.objects.filter(
            pk=service.responsable_id,
            is_active=True,
        )

    return (responsables_multi | responsables_anciens).distinct()


# ============================================================
# FORMULAIRE COURRIER
# ============================================================

class CourrierForm(forms.ModelForm):

    documents = MultipleFileField(
        required=False,
        label="Documents complémentaires",
        help_text=(
            "Sélectionnez plusieurs fichiers si nécessaire. "
            "Formats autorisés : PDF, DOC, DOCX, XLS, XLSX, JPG et PNG. "
            "20 Mo maximum par fichier."
        ),
    )

    class Meta:
        model = Courrier

        fields = [
            "sens",
            "date_courrier",
            "date_reception_expedition",
            "mode_reception",
            "date_reception_physique",
            "nom_livreur",
            "date_expedition",
            "expediteur",
            "destinataire",
            "objet",
            "description",
            "categorie",
            "service",
            "responsable",
            "destinataire_confidentiel",
            "priorite",
            "confidentialite",
            "date_limite",
            "document",
        ]

        widgets = {
            "sens": forms.Select(attrs={
                "class": "form-select",
            }),

            "date_courrier": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),

            "date_reception_expedition": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),

            "mode_reception": forms.Select(attrs={
                "class": "form-select",
            }),

            "date_reception_physique": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),

            "nom_livreur": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nom du livreur",
            }),

            "date_expedition": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),

            "expediteur": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nom ou organisme expéditeur",
            }),

            "destinataire": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Destinataire du courrier",
            }),

            "objet": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Objet du courrier",
            }),

            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Description ou résumé du courrier",
            }),

            "categorie": forms.Select(attrs={
                "class": "form-select",
            }),

            "service": forms.Select(attrs={
                "class": "form-select",
            }),

            "responsable": forms.Select(attrs={
                "class": "form-select",
            }),

            "destinataire_confidentiel": forms.Select(attrs={
                "class": "form-select",
            }),

            "priorite": forms.Select(attrs={
                "class": "form-select",
            }),

            "confidentialite": forms.Select(attrs={
                "class": "form-select",
            }),

            "date_limite": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),

            "document": forms.ClearableFileInput(attrs={
                "class": "form-control",
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)

        super().__init__(*args, **kwargs)

        obligatoires = [
            "sens",
            "date_courrier",
            "objet",
            "expediteur",
            "destinataire",
            "categorie",
            "confidentialite",
        ]

        for champ in obligatoires:
            self.fields[champ].required = True

        # Catégories actives
        categories = CategorieCourrier.objects.filter(actif=True)

        if self.instance and self.instance.pk:
            if self.instance.categorie_id:
                categories = (
                    categories
                    | CategorieCourrier.objects.filter(
                        pk=self.instance.categorie_id
                    )
                )

        self.fields["categorie"].queryset = categories.distinct()

        # Services accessibles
        if self.user:
            services = obtenir_services_accessibles(self.user)
        else:
            services = Service.objects.filter(actif=True)

        if self.instance and self.instance.pk:
            if self.instance.service_id:
                services = (
                    services
                    | Service.objects.filter(
                        pk=self.instance.service_id
                    )
                )

        self.fields["service"].queryset = services.distinct()

        # Service sélectionné dans le formulaire
        service_selectionne = None

        if self.is_bound:
            service_id = self.data.get(
                self.add_prefix("service")
            )

            if service_id:
                service_selectionne = (
                    Service.objects
                    .filter(pk=service_id, actif=True)
                    .first()
                )

        if not service_selectionne and self.instance and self.instance.pk:
            service_selectionne = self.instance.service

        # Responsables autorisés
        if service_selectionne:
            responsables = obtenir_responsables_service(
                service_selectionne
            )
        else:
            responsables = User.objects.filter(
                responsabilites_services__actif=True,
                responsabilites_services__service__actif=True,
                is_active=True,
            )

            anciens = User.objects.filter(
                services_diriges__actif=True,
                is_active=True,
            )

            responsables = (responsables | anciens).distinct()

        if self.instance and self.instance.pk:
            if self.instance.responsable_id:
                responsables = (
                    responsables
                    | User.objects.filter(
                        pk=self.instance.responsable_id
                    )
                )

        self.fields["responsable"].queryset = responsables.distinct()
        self.fields["responsable"].required = False

        # Destinataires confidentiels
        destinataires = User.objects.filter(
            is_active=True
        ).order_by("username")

        if self.instance and self.instance.pk:
            if self.instance.destinataire_confidentiel_id:
                destinataires = (
                    destinataires
                    | User.objects.filter(
                        pk=self.instance.destinataire_confidentiel_id
                    )
                )

        self.fields[
            "destinataire_confidentiel"
        ].queryset = destinataires.distinct()

        # Champs facultatifs
        facultatifs = [
            "date_reception_expedition",
            "mode_reception",
            "date_reception_physique",
            "nom_livreur",
            "date_expedition",
            "description",
            "service",
            "responsable",
            "destinataire_confidentiel",
            "priorite",
            "date_limite",
            "document",
        ]

        for champ in facultatifs:
            self.fields[champ].required = False

        self.fields["document"].help_text = (
            "Document principal du courrier. "
            "Formats autorisés : PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG et PNG. "
            "Taille maximale : 20 Mo."
        )

    def clean_document(self):
        fichier = self.cleaned_data.get("document")

        if fichier:
            valider_fichier(fichier)

        return fichier

    def clean_documents(self):
        fichiers = self.cleaned_data.get("documents", [])

        for fichier in fichiers:
            valider_fichier(fichier)

        return fichiers

    def clean(self):
        cleaned_data = super().clean()

        sens = cleaned_data.get("sens")
        confidentialite = cleaned_data.get("confidentialite")

        date_courrier = cleaned_data.get("date_courrier")
        date_reception = cleaned_data.get(
            "date_reception_expedition"
        )
        date_physique = cleaned_data.get(
            "date_reception_physique"
        )
        date_expedition = cleaned_data.get("date_expedition")

        service = cleaned_data.get("service")
        responsable = cleaned_data.get("responsable")
        destinataire = cleaned_data.get(
            "destinataire_confidentiel"
        )

        # Cohérence des dates
        if date_courrier and date_reception:
            if date_reception < date_courrier:
                self.add_error(
                    "date_reception_expedition",
                    "La date de réception ne peut pas être antérieure "
                    "à la date du courrier.",
                )

        if date_courrier and date_expedition:
            if date_expedition < date_courrier:
                self.add_error(
                    "date_expedition",
                    "La date d'expédition ne peut pas être antérieure "
                    "à la date du courrier.",
                )

        if date_reception and date_physique:
            if date_physique.date() < date_reception:
                self.add_error(
                    "date_reception_physique",
                    "La date de réception physique ne peut pas être "
                    "antérieure à la date de réception.",
                )

        # Cohérence du sens
        if sens == Courrier.Sens.ENTRANT and date_expedition:
            self.add_error(
                "date_expedition",
                "Un courrier entrant ne doit pas avoir de date "
                "d'expédition interne.",
            )

        if sens == Courrier.Sens.SORTANT and date_physique:
            self.add_error(
                "date_reception_physique",
                "La date de réception physique concerne les "
                "courriers entrants.",
            )

        # Vérification du service
        if service and self.user:
            autorises = obtenir_services_accessibles(self.user)

            if not autorises.filter(pk=service.pk).exists():
                self.add_error(
                    "service",
                    "Vous ne pouvez pas sélectionner ce service.",
                )

        # Vérification du responsable
        if responsable:
            if not service:
                self.add_error(
                    "responsable",
                    "Vous devez d'abord sélectionner un service.",
                )
            else:
                responsables_autorises = obtenir_responsables_service(
                    service
                )

                if not responsables_autorises.filter(
                    pk=responsable.pk
                ).exists():
                    self.add_error(
                        "responsable",
                        "Cet utilisateur n'est pas responsable "
                        "du service sélectionné.",
                    )

        # Confidentialité stricte
        if confidentialite == Courrier.Confidentialite.STRICTE:
            if not destinataire:
                self.add_error(
                    "destinataire_confidentiel",
                    "Vous devez désigner un destinataire confidentiel "
                    "pour un courrier strictement confidentiel.",
                )
            elif not destinataire.is_active:
                self.add_error(
                    "destinataire_confidentiel",
                    "Le destinataire sélectionné n'est pas actif.",
                )
        else:
            cleaned_data["destinataire_confidentiel"] = None

        return cleaned_data


# ============================================================
# FORMULAIRE DE TRANSMISSION ET D'AFFECTATION MULTIPLE
# ============================================================

class AffectationForm(forms.ModelForm):

    agents = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Agents à affecter",
        help_text=(
            "Sélectionnez un ou plusieurs agents. "
            "Chaque agent recevra une affectation individuelle."
        ),
        widget=forms.SelectMultiple(attrs={
            "class": "form-select",
            "size": 8,
        }),
    )

    class Meta:
        model = Affectation

        fields = [
            "service",
            "instruction",
            "date_limite",
        ]

        widgets = {
            "service": forms.Select(attrs={
                "class": "form-select",
            }),

            "instruction": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Instructions relatives au traitement",
            }),

            "date_limite": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.courrier = kwargs.pop("courrier", None)

        super().__init__(*args, **kwargs)

        # Services accessibles
        if self.user:
            services = obtenir_services_accessibles(self.user)
        else:
            services = Service.objects.filter(actif=True)

        if self.instance and self.instance.pk:
            if self.instance.service_id:
                services = (
                    services
                    | Service.objects.filter(
                        pk=self.instance.service_id
                    )
                )

        self.fields["service"].queryset = (
            services.filter(actif=True)
            .distinct()
            .order_by("nom")
        )

        self.fields["service"].required = True

        # Agents actifs du profil AGENT
        agents_autorises = []

        for utilisateur in User.objects.filter(
            is_active=True
        ).order_by("username"):

            if obtenir_profil(utilisateur) == "AGENT":
                agents_autorises.append(utilisateur.pk)

        self.fields["agents"].queryset = User.objects.filter(
            pk__in=agents_autorises,
            is_active=True,
        ).order_by("username")

        if self.instance and self.instance.pk:
            if self.instance.agent_id:
                self.fields["agents"].initial = [
                    self.instance.agent_id
                ]

    def clean_date_limite(self):
        date_limite = self.cleaned_data.get("date_limite")

        if date_limite and date_limite < timezone.localdate():
            raise forms.ValidationError(
                "La date limite ne peut pas être antérieure à aujourd'hui."
            )

        return date_limite

    def clean(self):
        cleaned_data = super().clean()

        service = cleaned_data.get("service")
        agents = cleaned_data.get("agents")

        if service and not service.actif:
            self.add_error(
                "service",
                "Le service sélectionné est inactif.",
            )

        if service and self.user:
            autorises = obtenir_services_accessibles(self.user)

            if not autorises.filter(pk=service.pk).exists():
                self.add_error(
                    "service",
                    "Vous ne pouvez pas affecter un courrier à ce service.",
                )

        if agents:
            for agent in agents:
                if not agent.is_active:
                    self.add_error(
                        "agents",
                        "Un des agents sélectionnés n'est pas actif.",
                    )
                    break

                if obtenir_profil(agent) != "AGENT":
                    self.add_error(
                        "agents",
                        "Tous les utilisateurs sélectionnés doivent "
                        "avoir le profil AGENT.",
                    )
                    break

        return cleaned_data
