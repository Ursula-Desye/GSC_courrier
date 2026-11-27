
from django.contrib.auth.models import User
from django.db import transaction
from courrier.models import Courrier

with transaction.atomic():

    accueil = User.objects.get(username="test_accueil")

    objet = "TEST DU CIRCUIT DE TRANSMISSION GSC"
    expediteur = "EXPEDITEUR TEST GSC"

    if Courrier.objects.filter(
        objet=objet,
        expediteur=expediteur,
        cree_par=accueil
    ).exists():
        raise Exception(
            "Ce courrier de test existe déjà. "
            "Aucune nouvelle création effectuée."
        )

    courrier = Courrier.objects.create(
        sens="ENTRANT",
        expediteur=expediteur,
        destinataire="GMC ASSURANCES - TEST",
        objet=objet,
        description=(
            "Courrier fictif destiné aux tests fonctionnels "
            "de transmission, réception et traitement dans GSC."
        ),
        mode_reception="PHYSIQUE",
        confidentialite="NORMALE",
        priorite="NORMALE",
        statut="ENREGISTRE",
        cree_par=accueil,
    )

print("\nCOURRIER FICTIF CREE AVEC SUCCES")
print("Référence :", courrier.reference)
print("Créé par :", courrier.cree_par.username)
print("Statut :", courrier.get_statut_display())
print("Confidentialité :", courrier.get_confidentialite_display())
