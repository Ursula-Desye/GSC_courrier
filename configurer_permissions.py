
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import Group, Permission

droits = {
    "Administrateur": [],
    "Secrétariat": [
        "view_courrier", "add_courrier", "change_courrier",
        "transmettre_courrier",
        "view_affectation", "add_affectation", "change_affectation",
        "view_historique",
    ],
    "Responsable de service": [
        "view_courrier", "change_courrier",
        "transmettre_courrier", "cloturer_courrier",
        "view_affectation", "add_affectation", "change_affectation",
        "view_historique",
    ],
    "Agent": [
        "view_courrier", "view_affectation", "view_historique",
    ],
    "Direction": [
        "view_courrier", "view_affectation", "view_historique",
    ],
}

for nom, permissions in droits.items():
    groupe = Group.objects.get(name=nom)
    groupe.permissions.clear()

    if permissions:
        groupe.permissions.set(
            Permission.objects.filter(codename__in=permissions)
        )

    print(f"{nom} : {groupe.permissions.count()} permissions attribuées")

print("\nConfiguration des permissions terminée.")
