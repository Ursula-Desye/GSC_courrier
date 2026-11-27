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
