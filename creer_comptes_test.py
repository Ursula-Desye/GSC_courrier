
import secrets
from django.contrib.auth.models import User, Group
from django.db import transaction

COMPTES = [
    ("test_admin", None, True),
    ("test_accueil", "Accueil", False),
    ("test_secretariat", "Secrétariat", False),
    ("test_direction", "Direction", False),
    ("test_responsable", "Responsable de service", False),
    ("test_agent", "Agent", False),
]

# Ne jamais écraser un compte existant.
noms = [compte[0] for compte in COMPTES]
existants = list(
    User.objects.filter(username__in=noms)
    .values_list("username", flat=True)
)

if existants:
    raise Exception(
        "Création annulée. Ces comptes existent déjà : "
        + ", ".join(existants)
    )

identifiants = []

with transaction.atomic():
    for username, groupe_nom, administrateur in COMPTES:
        mot_de_passe = secrets.token_urlsafe(16)

        utilisateur = User.objects.create_user(
            username=username,
            password=mot_de_passe,
            is_active=True,
        )

        if administrateur:
            utilisateur.is_staff = True
            utilisateur.is_superuser = True
            utilisateur.save(update_fields=["is_staff", "is_superuser"])
        else:
            groupe, _ = Group.objects.get_or_create(name=groupe_nom)
            utilisateur.groups.add(groupe)

        identifiants.append((username, mot_de_passe))

print("\n==========================================")
print("      COMPTES DE TEST GSC CREES")
print("==========================================")

for username, password in identifiants:
    print(f"\nUtilisateur : {username}")
    print(f"Mot de passe : {password}")

print("\nConservez ces mots de passe en lieu sûr.")
print("Ne les utilisez pas pour les comptes réels.")
