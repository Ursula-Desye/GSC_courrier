r"""
GSC - Preparation de l'integration du fichier SUIVI_COURRIER.xlsx

A placer dans D:\Downloads\GSC (a cote de manage.py) puis lancer :
    python patch_suivi_excel.py

Ce script ajoute (avec sauvegardes .bak, et sans rien casser si relance) :
  - courrier/models.py : modeles SuiviCourrier (toutes les colonnes de l'Excel)
                         et PersonnelService (listes deroulantes par service)
  - courrier/admin.py  : consultation de ces deux tables dans l'administration
  - courrier/forms.py  : la liste des agents d'une affectation est limitee
                         au personnel du service (regle INDIRECT de l'Excel)
  - courrier/views.py  : la liste des courriers d'un Responsable est calculee
                         en base (avant : 1 requete par courrier, plusieurs
                         minutes avec 33 000 courriers). Meme resultat.
Il faut ensuite lancer :  python manage.py makemigrations courrier
                          python manage.py migrate
"""
from pathlib import Path
import shutil
import sys

BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent

MODELES = '''

# =====================================================
# PERSONNEL AUTORISE PAR SERVICE (liste deroulante Excel)
# =====================================================

class PersonnelService(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="personnel"
    )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="appartenances_service"
    )

    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["service__nom", "utilisateur__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "utilisateur"],
                name="unique_personnel_service"
            )
        ]
        verbose_name = "Personnel de service"
        verbose_name_plural = "Personnel des services"

    def __str__(self):
        return f"{self.utilisateur} - {self.service}"


# =====================================================
# SUIVI DU COURRIER (colonnes du fichier SUIVI_COURRIER.xlsx)
# =====================================================

class SuiviCourrier(models.Model):

    class Execution(models.TextChoices):
        OUI = "OUI", "Oui"
        NON = "NON", "Non"

    courrier = models.OneToOneField(
        Courrier,
        on_delete=models.PROTECT,
        related_name="suivi_excel"
    )

    ligne_source = models.PositiveIntegerField(
        null=True, blank=True, db_index=True,
        verbose_name="Ligne du fichier Excel"
    )

    numero_ordre = models.CharField(max_length=30, blank=True, verbose_name="N\u00b0 d'ordre")
    nature = models.CharField(max_length=250, blank=True, verbose_name="Correspondance")
    reference_excel = models.CharField(max_length=250, blank=True, verbose_name="R\u00e9f\u00e9rence")

    date_transmission_departement = models.DateField(null=True, blank=True)
    observation_retour_departement = models.TextField(blank=True)
    date_reception_departement = models.DateField(null=True, blank=True)

    responsable_nom = models.CharField(max_length=180, blank=True, verbose_name="Responsable du service")
    date_transmission_responsable = models.DateField(null=True, blank=True)
    observation_retour_responsable = models.TextField(blank=True)
    date_reception_responsable = models.DateField(null=True, blank=True)

    redacteur_nom = models.CharField(max_length=180, blank=True, verbose_name="R\u00e9dacteur")
    date_affectation_redacteur = models.DateField(null=True, blank=True)
    instructions_responsable = models.TextField(blank=True)

    redacteur_final_nom = models.CharField(max_length=180, blank=True, verbose_name="R\u00e9affectation r\u00e9dacteur final")
    date_affectation_redacteur_final = models.DateField(null=True, blank=True)
    date_reception_redacteur_final = models.DateField(null=True, blank=True)

    numero_dossier = models.CharField(max_length=60, blank=True, db_index=True, verbose_name="N\u00b0 dossier")
    assure = models.CharField(max_length=250, blank=True, verbose_name="Assur\u00e9 / Tiers")
    action_menee = models.TextField(blank=True, verbose_name="Action men\u00e9e")
    date_traitement = models.DateField(null=True, blank=True)

    execution = models.CharField(
        max_length=3, choices=Execution.choices, blank=True,
        verbose_name="Ex\u00e9cution (OUI/NON)"
    )
    date_execution = models.DateField(null=True, blank=True)
    observations = models.TextField(blank=True)

    class Meta:
        ordering = ["-courrier__cree_le"]
        verbose_name = "Suivi du courrier"
        verbose_name_plural = "Suivis des courriers"

    def clean(self):
        from django.core.exceptions import ValidationError

        aujourdhui = timezone.localdate()
        erreurs = {}

        for champ in (
            "date_transmission_departement", "date_reception_departement",
            "date_transmission_responsable", "date_reception_responsable",
            "date_affectation_redacteur", "date_affectation_redacteur_final",
            "date_reception_redacteur_final", "date_traitement",
            "date_execution",
        ):
            valeur = getattr(self, champ)
            if valeur and valeur > aujourdhui:
                erreurs[champ] = "La date ne peut pas \u00eatre dans le futur."

        if erreurs:
            raise ValidationError(erreurs)

    def __str__(self):
        return f"Suivi {self.courrier_id} - dossier {self.numero_dossier or '-'}"
'''

ADMIN = '''

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
'''

FORMS_ANCRE = (
    "        if self.instance and self.instance.pk:\n"
    "            if self.instance.agent_id:\n"
    "                self.fields[\"agents\"].initial = ["
)
FORMS_AJOUT = '''        # Liste deroulante dependante du service (regle INDIRECT de l'Excel) :
        # si le service a un personnel defini, seuls ses membres sont proposes.
        if self.courrier is not None and getattr(self.courrier, "service_id", None):
            from .models import PersonnelService

            ids_personnel = list(
                PersonnelService.objects.filter(
                    service_id=self.courrier.service_id,
                    actif=True,
                ).values_list("utilisateur_id", flat=True)
            )

            if ids_personnel:
                self.fields["agents"].queryset = (
                    self.fields["agents"].queryset.filter(pk__in=ids_personnel)
                )

'''


VIEWS_ANCIEN = '''    if profil == "RESPONSABLE":
        services = services_accessibles_du_responsable(user)

        ids_courriers = qs.filter(
            service__in=services
        ).values_list("id", flat=True)

        ids_valides = []

        for courrier in qs.filter(pk__in=ids_courriers):
            if responsable_peut_gerer_categorie(user, courrier):
                ids_valides.append(courrier.pk)

        return qs.filter(pk__in=ids_valides)
'''

VIEWS_NOUVEAU = '''    if profil == "RESPONSABLE":
        # Meme regle qu'avant (service + categories autorisees), calculee
        # en base au lieu d'une boucle courrier par courrier.
        from .permissions import responsabilites_actives

        services = services_accessibles_du_responsable(user)
        ids_services = list(services.values_list("pk", flat=True))

        condition = Q(pk__in=[])

        for service_id in Service.objects.filter(
            responsable=user,
            actif=True,
            pk__in=ids_services,
        ).values_list("pk", flat=True):
            condition |= Q(service_id=service_id)

        for responsabilite in responsabilites_actives(user):
            if responsabilite.toutes_categories:
                condition |= Q(service_id=responsabilite.service_id)
            else:
                condition |= Q(
                    service_id=responsabilite.service_id,
                    categorie_id__in=list(
                        responsabilite.categories.values_list("pk", flat=True)
                    ),
                )

        return qs.filter(condition, service__in=services)
'''


def lire(chemin):
    brut = chemin.read_bytes().decode("utf-8")
    return brut.replace("\r\n", "\n"), "\r\n" in brut


def ecrire(chemin, texte, crlf):
    shutil.copy2(chemin, chemin.with_name(chemin.name + ".bak"))
    if crlf:
        texte = texte.replace("\n", "\r\n")
    chemin.write_bytes(texte.encode("utf-8"))


def patch_models():
    p = BASE / "courrier" / "models.py"
    texte, crlf = lire(p)
    if "class SuiviCourrier" in texte:
        return "[DEJA FAIT] models.py"
    ecrire(p, texte.rstrip("\n") + "\n" + MODELES, crlf)
    return "[OK] models.py : SuiviCourrier et PersonnelService ajoutes"


def patch_admin():
    p = BASE / "courrier" / "admin.py"
    texte, crlf = lire(p)
    if "class SuiviCourrierAdmin" in texte:
        return "[DEJA FAIT] admin.py"
    if "class GSCAdmin" not in texte:
        return "[ARRET] admin.py : GSCAdmin introuvable, rien modifie"
    ecrire(p, texte.rstrip("\n") + "\n" + ADMIN, crlf)
    return "[OK] admin.py : suivi Excel et personnel des services ajoutes"


def patch_forms():
    p = BASE / "courrier" / "forms.py"
    texte, crlf = lire(p)
    if "PersonnelService" in texte:
        return "[DEJA FAIT] forms.py"
    n = texte.count(FORMS_ANCRE)
    if n != 1:
        return (f"[ARRET] forms.py : point d'insertion trouve {n} fois (1 attendu). "
                "Rien modifie : envoyez-moi forms.py.")
    ecrire(p, texte.replace(FORMS_ANCRE, FORMS_AJOUT + FORMS_ANCRE), crlf)
    return "[OK] forms.py : agents limites au personnel du service"


def patch_views():
    p = BASE / "courrier" / "views.py"
    texte, crlf = lire(p)
    if "responsabilites_actives(user)" in texte:
        return "[DEJA FAIT] views.py"
    n = texte.count(VIEWS_ANCIEN)
    if n != 1:
        return (f"[ARRET] views.py : bloc Responsable trouve {n} fois (1 attendu). "
                "Rien modifie : envoyez-moi views.py.")
    ecrire(p, texte.replace(VIEWS_ANCIEN, VIEWS_NOUVEAU), crlf)
    return "[OK] views.py : liste des courriers du Responsable acceleree"


if __name__ == "__main__":
    for requis in ("models.py", "admin.py", "forms.py", "views.py"):
        if not (BASE / "courrier" / requis).exists():
            raise SystemExit(f"Fichier introuvable : {BASE / 'courrier' / requis}")
    for fonction in (patch_models, patch_admin, patch_forms, patch_views):
        print(fonction())
    print("\nEtape suivante :")
    print("  python manage.py makemigrations courrier")
    print("  python manage.py migrate")
