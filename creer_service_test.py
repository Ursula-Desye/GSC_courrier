
from django.contrib.auth.models import User
from django.db import transaction
from courrier.models import Service, ResponsableService

with transaction.atomic():

    responsable = User.objects.get(username="test_responsable")

    service, cree = Service.objects.get_or_create(
        nom="SERVICE TEST GSC",
        defaults={
            "description": "Service fictif destiné aux tests fonctionnels de GSC.",
            "type_structure": "SERVICE",
            "responsable": responsable,
            "actif": True,
        }
    )

    if not cree:
        raise Exception(
            "Le service SERVICE TEST GSC existe déjà. "
            "Vérification manuelle nécessaire."
        )

    ResponsableService.objects.create(
        service=service,
        utilisateur=responsable,
        description_perimetre="Responsable du service fictif de test GSC.",
        toutes_categories=True,
        chef_departement=False,
        peut_affecter_agents=True,
        peut_cloturer=True,
        inclure_structures_enfants=False,
        actif=True,
    )

print("\nSERVICE DE TEST CREE AVEC SUCCES")
print("Service :", service.nom)
print("Responsable :", responsable.username)
print("Type :", service.type_structure)
