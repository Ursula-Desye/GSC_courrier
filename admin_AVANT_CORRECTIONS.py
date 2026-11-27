
from django.contrib import admin

from .models import (
    Service,
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
    ParametreGSC,
)


# =====================================================
# PERSONNALISATION DE L'ADMINISTRATION GSC
# =====================================================

admin.site.site_header = "GSC - Gestion et Suivi du Courrier"
admin.site.site_title = "Administration GSC"
admin.site.index_title = "Administration et tracabilite"


# =====================================================
# CLASSE DE BASE
# INTERDICTION DE SUPPRESSION PHYSIQUE
# =====================================================

class GSCAdmin(admin.ModelAdmin):

    def has_delete_permission(self, request, obj=None):
        return False


# =====================================================
# CLASSE DES MODELES EN LECTURE SEULE
# =====================================================

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
# SERVICES
# CREATION ET MODIFICATION AUTORISEES
# =====================================================

@admin.register(Service)
class ServiceAdmin(GSCAdmin):

    list_display = (
        "nom",
        "responsable",
        "actif",
    )

    list_filter = ("actif",)

    search_fields = (
        "nom",
        "description",
        "responsable__username",
        "responsable__first_name",
        "responsable__last_name",
    )

    list_select_related = ("responsable",)
    ordering = ("nom",)
    list_per_page = 25


# =====================================================
# CATEGORIES
# CONSULTATION UNIQUEMENT
# =====================================================

@admin.register(CategorieCourrier)
class CategorieCourrierAdmin(GSCReadOnlyAdmin):

    list_display = (
        "nom",
        "actif",
    )

    list_filter = ("actif",)
    search_fields = ("nom", "description")
    ordering = ("nom",)
    list_per_page = 25


# =====================================================
# COURRIERS
# MODIFICATION VIA L'APPLICATION GSC UNIQUEMENT
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
# GESTION PAR L'ADMINISTRATEUR
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
# RETOURS AU SECRETARIAT
# CONSULTATION UNIQUEMENT
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
# PIECES JOINTES ET VERSIONS
# CONSULTATION UNIQUEMENT
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
# BORDEREAUX COLLECTIFS
# CONSULTATION UNIQUEMENT
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


# =====================================================
# LIGNES DES BORDEREAUX
# CONSULTATION UNIQUEMENT
# =====================================================

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


# =====================================================
# RECEPTIONS DES BORDEREAUX
# CONSULTATION UNIQUEMENT
# =====================================================

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
# CONSULTATION UNIQUEMENT
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
# CONSULTATION UNIQUEMENT
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

    ordering = (
        "-annee",
        "sens",
    )


# =====================================================
# PARAMETRES GENERAUX
# UNE SEULE CONFIGURATION
# =====================================================

@admin.register(ParametreGSC)
class ParametreGSCAdmin(GSCAdmin):

    list_display = (
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

    list_per_page = 1

    def has_add_permission(self, request):

        if ParametreGSC.objects.exists():
            return False

        return super().has_add_permission(request)

    def save_model(self, request, obj, form, change):

        obj.modifie_par = request.user

        super().save_model(request, obj, form, change)
