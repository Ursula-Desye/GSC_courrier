
from django.contrib import admin

from .models import (
    Service,
    ResponsableService,
    CompteurReference,
    CategorieCourrier,
    Courrier,
    Affectation,
    DelegationTransmission,
    RetourCourrier,
    PieceJointe,
    BordereauTransmission,
    LigneBordereau,
    ReceptionBordereau,
    Historique,
    AutorisationConfidentialite,
    RegleOrientation,
    JournalAccesConfidentiel,
    ParametreGSC,
)


# =====================================================
# PERSONNALISATION DE L'ADMINISTRATION GSC
# =====================================================

admin.site.site_header = "GSC - Gestion et Suivi du Courrier"
admin.site.site_title = "Administration GSC"
admin.site.index_title = "Administration et traçabilité"


# =====================================================
# CLASSES DE BASE
# =====================================================

class GSCAdmin(admin.ModelAdmin):

    def has_delete_permission(self, request, obj=None):
        # Suppression définitive interdite par défaut
        return False


class GSCReadOnlyAdmin(GSCAdmin):

    def get_readonly_fields(self, request, obj=None):
        return [
            field.name
            for field in self.model._meta.fields
        ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return super().has_view_permission(request, obj)


# =====================================================
# STRUCTURES ORGANISATIONNELLES
# =====================================================

@admin.register(Service)
class ServiceAdmin(GSCAdmin):

    list_display = (
        "nom",
        "type_structure",
        "parent",
        "responsable",
        "actif",
    )

    list_filter = (
        "type_structure",
        "actif",
        "parent",
    )

    search_fields = (
        "nom",
        "description",
        "responsable__username",
        "responsable__first_name",
        "responsable__last_name",
    )

    list_select_related = (
        "responsable",
        "parent",
    )

    ordering = ("type_structure", "nom")
    list_per_page = 25

    fieldsets = (
        (
            "Identification de la structure",
            {
                "fields": (
                    "nom",
                    "type_structure",
                    "description",
                    "actif",
                )
            },
        ),
        (
            "Organisation hiérarchique",
            {
                "fields": (
                    "parent",
                    "responsable",
                )
            },
        ),
    )


# =====================================================
# CHEFS DE DEPARTEMENT ET RESPONSABLES
# =====================================================

@admin.register(ResponsableService)
class ResponsableServiceAdmin(GSCAdmin):

    list_display = (
        "utilisateur",
        "service",
        "chef_departement",
        "peut_affecter_agents",
        "peut_cloturer",
        "inclure_structures_enfants",
        "actif",
    )

    list_filter = (
        "chef_departement",
        "peut_affecter_agents",
        "peut_cloturer",
        "actif",
        "service__type_structure",
    )

    search_fields = (
        "utilisateur__username",
        "utilisateur__first_name",
        "utilisateur__last_name",
        "service__nom",
        "description_perimetre",
    )

    list_select_related = (
        "utilisateur",
        "service",
    )

    filter_horizontal = ("categories",)

    ordering = (
        "service__nom",
        "utilisateur__username",
    )

    list_per_page = 25

    fieldsets = (
        (
            "Désignation",
            {
                "fields": (
                    "service",
                    "utilisateur",
                    "actif",
                    "chef_departement",
                )
            },
        ),
        (
            "Périmètre de responsabilité",
            {
                "fields": (
                    "description_perimetre",
                    "toutes_categories",
                    "categories",
                    "inclure_structures_enfants",
                )
            },
        ),
        (
            "Autorisations",
            {
                "fields": (
                    "peut_affecter_agents",
                    "peut_cloturer",
                )
            },
        ),
    )

    readonly_fields = ("date_creation",)


# =====================================================
# CATEGORIES DE COURRIER
# AJOUT ET MODIFICATION AUTORISES
# SUPPRESSION DEFINITIVE INTERDITE
# =====================================================

@admin.register(CategorieCourrier)
class CategorieCourrierAdmin(GSCAdmin):

    list_display = (
        "nom",
        "description",
        "actif",
    )

    list_filter = (
        "actif",
    )

    search_fields = (
        "nom",
        "description",
    )

    ordering = ("nom",)
    list_per_page = 25

    fields = (
        "nom",
        "description",
        "actif",
    )


# =====================================================
# COURRIERS
# MODIFICATION VIA L'APPLICATION GSC
# =====================================================

@admin.register(Courrier)
class CourrierAdmin(GSCReadOnlyAdmin):

    list_display = (
        "reference",
        "sens",
        "date_courrier",
        "expediteur",
        "destinataire",
        "objet",
        "service",
        "statut",
        "priorite",
        "confidentialite",
    )

    list_filter = (
        "sens",
        "statut",
        "priorite",
        "confidentialite",
        "service",
        "date_courrier",
    )

    search_fields = (
        "reference",
        "objet",
        "description",
        "expediteur",
        "destinataire",
    )

    list_select_related = (
        "service",
        "responsable",
        "cree_par",
        "categorie",
    )

    ordering = ("-cree_le",)
    list_per_page = 25


# =====================================================
# AFFECTATIONS
# CONSULTATION UNIQUEMENT
# =====================================================

@admin.register(Affectation)
class AffectationAdmin(GSCReadOnlyAdmin):

    list_display = (
        "courrier",
        "service",
        "agent",
        "transmis_par",
        "date_transmission",
        "date_limite",
        "statut",
        "active",
        "date_confirmation_reception",
    )

    list_filter = (
        "service",
        "statut",
        "active",
        "date_transmission",
    )

    search_fields = (
        "courrier__reference",
        "courrier__objet",
        "service__nom",
        "agent__username",
        "transmis_par__username",
    )

    list_select_related = (
        "courrier",
        "service",
        "agent",
        "transmis_par",
        "confirme_par",
    )

    ordering = ("-date_transmission",)
    list_per_page = 25


# =====================================================
# DELEGATIONS TEMPORAIRES
# =====================================================

@admin.register(DelegationTransmission)
class DelegationTransmissionAdmin(GSCAdmin):

    list_display = (
        "utilisateur",
        "autorise_par",
        "date_debut",
        "date_fin",
        "actif",
    )

    list_filter = (
        "actif",
        "date_debut",
        "date_fin",
    )

    search_fields = (
        "utilisateur__username",
        "utilisateur__first_name",
        "utilisateur__last_name",
        "autorise_par__username",
        "motif",
    )

    list_select_related = (
        "utilisateur",
        "autorise_par",
    )

    ordering = ("-date_debut",)
    list_per_page = 25

    def get_readonly_fields(self, request, obj=None):
        champs = [
            "autorise_par",
            "cree_le",
        ]

        if obj:
            champs.extend([
                "utilisateur",
                "date_debut",
                "date_fin",
                "motif",
            ])

        return champs

    def save_model(self, request, obj, form, change):
        if not change:
            obj.autorise_par = request.user

        super().save_model(request, obj, form, change)


# =====================================================
# RETOURS DE COURRIER
# =====================================================

@admin.register(RetourCourrier)
class RetourCourrierAdmin(GSCReadOnlyAdmin):

    list_display = (
        "courrier",
        "retourne_par",
        "date_retour",
        "traite",
        "nouveau_courrier",
    )

    list_filter = (
        "traite",
        "date_retour",
    )

    search_fields = (
        "courrier__reference",
        "motif",
        "retourne_par__username",
    )

    list_select_related = (
        "courrier",
        "retourne_par",
        "nouveau_courrier",
    )

    ordering = ("-date_retour",)
    list_per_page = 25


# =====================================================
# PIECES JOINTES
# =====================================================

@admin.register(PieceJointe)
class PieceJointeAdmin(GSCReadOnlyAdmin):

    list_display = (
        "nom_original",
        "courrier",
        "version",
        "active",
        "ajoute_par",
        "ajoute_le",
        "retire_par",
        "retire_le",
    )

    list_filter = (
        "active",
        "ajoute_le",
    )

    search_fields = (
        "nom_original",
        "courrier__reference",
    )

    list_select_related = (
        "courrier",
        "ajoute_par",
        "retire_par",
        "version_precedente",
    )

    ordering = ("-ajoute_le",)
    list_per_page = 25


# =====================================================
# BORDEREAUX DE TRANSMISSION
# =====================================================

@admin.register(BordereauTransmission)
class BordereauTransmissionAdmin(GSCReadOnlyAdmin):

    list_display = (
        "id",
        "service",
        "date_transmission",
        "transmis_par",
        "statut",
    )

    list_filter = (
        "service",
        "statut",
        "date_transmission",
    )

    list_select_related = (
        "service",
        "transmis_par",
    )

    ordering = ("-date_transmission",)
    list_per_page = 25


@admin.register(LigneBordereau)
class LigneBordereauAdmin(GSCReadOnlyAdmin):

    list_display = (
        "bordereau",
        "courrier",
    )

    search_fields = (
        "courrier__reference",
        "courrier__objet",
    )

    list_select_related = (
        "bordereau",
        "courrier",
    )


@admin.register(ReceptionBordereau)
class ReceptionBordereauAdmin(GSCReadOnlyAdmin):

    list_display = (
        "bordereau",
        "service",
        "receptionne_par",
        "date_reception",
    )

    list_filter = (
        "service",
        "date_reception",
    )

    list_select_related = (
        "bordereau",
        "service",
        "receptionne_par",
    )


# =====================================================
# HISTORIQUE
# =====================================================

@admin.register(Historique)
class HistoriqueAdmin(GSCReadOnlyAdmin):

    list_display = (
        "courrier",
        "utilisateur",
        "action",
        "date_action",
    )

    list_filter = (
        "action",
        "date_action",
    )

    search_fields = (
        "courrier__reference",
        "courrier__objet",
        "utilisateur__username",
        "action",
        "details",
        "motif",
    )

    list_select_related = (
        "courrier",
        "utilisateur",
    )

    ordering = ("-date_action",)
    list_per_page = 50


# =====================================================
# COMPTEURS DE REFERENCES
# =====================================================

@admin.register(CompteurReference)
class CompteurReferenceAdmin(GSCReadOnlyAdmin):

    list_display = (
        "sens",
        "annee",
        "dernier_numero",
    )

    list_filter = (
        "sens",
        "annee",
    )

    ordering = ("-annee", "sens")


# =====================================================
# AUTORISATIONS CONFIDENTIALITE
# =====================================================

@admin.register(AutorisationConfidentialite)
class AutorisationConfidentialiteAdmin(GSCAdmin):

    list_display = (
        "courrier",
        "utilisateur",
        "type_acces",
        "autorise_par",
        "date_debut",
        "date_fin",
        "actif",
    )

    list_filter = (
        "type_acces",
        "actif",
        "date_debut",
    )

    search_fields = (
        "courrier__reference",
        "utilisateur__username",
        "autorise_par__username",
        "motif",
    )

    list_select_related = (
        "courrier",
        "utilisateur",
        "autorise_par",
    )

    readonly_fields = ("date_creation",)


# =====================================================
# REGLES D'ORIENTATION
# =====================================================

@admin.register(RegleOrientation)
class RegleOrientationAdmin(GSCAdmin):

    list_display = (
        "nom",
        "categorie",
        "service_destination",
        "priorite_regle",
        "seuil_confiance",
        "actif",
    )

    list_filter = (
        "actif",
        "categorie",
        "service_destination",
    )

    search_fields = (
        "nom",
        "mots_cles",
        "service_destination__nom",
    )

    list_select_related = (
        "categorie",
        "service_destination",
        "cree_par",
    )

    readonly_fields = ("cree_le",)


# =====================================================
# JOURNAL DES ACCES CONFIDENTIELS
# =====================================================

@admin.register(JournalAccesConfidentiel)
class JournalAccesConfidentielAdmin(GSCReadOnlyAdmin):

    list_display = (
        "courrier",
        "utilisateur",
        "action",
        "date_action",
    )

    list_filter = (
        "action",
        "date_action",
    )

    search_fields = (
        "courrier__reference",
        "utilisateur__username",
        "motif",
    )

    list_select_related = (
        "courrier",
        "utilisateur",
    )

    ordering = ("-date_action",)
    list_per_page = 50


# =====================================================
# PARAMETRES GENERAUX GSC
# UNE SEULE CONFIGURATION
# =====================================================

@admin.register(ParametreGSC)
class ParametreGSCAdmin(GSCAdmin):

    list_display = (
        "appellation_unite",
        "appellation_unite_personnalisee",
        "delai_defaut_jours",
        "duree_conservation_annees",
        "alerte_retard_active",
        "notification_email_active",
        "modifie_par",
        "modifie_le",
    )

    readonly_fields = (
        "modifie_par",
        "modifie_le",
    )

    fieldsets = (
        (
            "Organisation de GSC",
            {
                "fields": (
                    "appellation_unite",
                    "appellation_unite_personnalisee",
                )
            },
        ),
        (
            "Délais et conservation",
            {
                "fields": (
                    "delai_defaut_jours",
                    "duree_conservation_annees",
                )
            },
        ),
        (
            "Alertes et notifications",
            {
                "fields": (
                    "alerte_retard_active",
                    "notification_email_active",
                )
            },
        ),
        (
            "Orientation automatique",
            {
                "fields": (
                    "seuil_orientation_automatique",
                )
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "modifie_par",
                    "modifie_le",
                )
            },
        ),
    )

    list_per_page = 1

    def has_add_permission(self, request):
        if ParametreGSC.objects.exists():
            return False
        return super().has_add_permission(request)

    def save_model(self, request, obj, form, change):
        obj.modifie_par = request.user
        super().save_model(request, obj, form, change)


# =====================================================
# SUIVI EXCEL ET PERSONNEL DES SERVICES
# =====================================================

from .models import SuiviCourrier, PersonnelService


@admin.register(SuiviCourrier)
class SuiviCourrierAdmin(GSCAdmin):

    list_display = (
        "courrier", "numero_ordre", "numero_dossier", "assure",
        "redacteur_nom", "execution", "date_execution",
    )
    list_filter = ("execution", "date_execution")
    search_fields = (
        "courrier__reference", "numero_ordre", "numero_dossier",
        "assure", "reference_excel", "nature",
        "responsable_nom", "redacteur_nom", "action_menee",
    )
    raw_id_fields = ("courrier",)
    list_per_page = 50


@admin.register(PersonnelService)
class PersonnelServiceAdmin(GSCAdmin):

    list_display = ("service", "utilisateur", "actif")
    list_filter = ("service", "actif")
    search_fields = ("utilisateur__username", "utilisateur__last_name", "service__nom")

from . import admin_acces  # noqa: E402,F401
