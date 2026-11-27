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
