
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


# =====================================================
# SERVICE / DIRECTION / DEPARTEMENT / UNITE
# =====================================================

class Service(models.Model):

    class TypeStructure(models.TextChoices):
        DIRECTION = "DIRECTION", "Direction"
        DEPARTEMENT = "DEPARTEMENT", "Département"
        SERVICE = "SERVICE", "Service"
        UNITE = "UNITE", "Unité"

    nom = models.CharField(
        max_length=120,
        unique=True,
        verbose_name="Nom de la structure"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )

    # Ancien champ conservé pour compatibilité.
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="services_diriges",
        null=True,
        blank=True,
        verbose_name="Responsable principal"
    )

    # Nouvelle organisation hiérarchique.
    type_structure = models.CharField(
        max_length=20,
        choices=TypeStructure.choices,
        default=TypeStructure.SERVICE,
        verbose_name="Type de structure"
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="structures_enfants",
        null=True,
        blank=True,
        verbose_name="Structure de rattachement"
    )

    # Plusieurs responsables possibles.
    responsables = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ResponsableService",
        through_fields=("service", "utilisateur"),
        related_name="services_responsable_multi",
        blank=True,
        verbose_name="Responsables"
    )

    actif = models.BooleanField(
        default=True,
        verbose_name="Structure active"
    )

    class Meta:
        ordering = ["nom"]
        verbose_name = "Structure"
        verbose_name_plural = "Structures"

    def __str__(self):
        return self.nom


# =====================================================
# RESPONSABLES ET PERIMETRES
# =====================================================

class ResponsableService(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="responsables_configures"
    )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsabilites_services"
    )

    description_perimetre = models.TextField(
        blank=True,
        verbose_name="Description du périmètre"
    )

    toutes_categories = models.BooleanField(
        default=True,
        verbose_name="Toutes les catégories"
    )

    categories = models.ManyToManyField(
        "CategorieCourrier",
        blank=True,
        related_name="responsables_autorises"
    )

    chef_departement = models.BooleanField(
        default=False,
        verbose_name="Chef de département"
    )

    peut_affecter_agents = models.BooleanField(
        default=True,
        verbose_name="Peut affecter des agents"
    )

    peut_cloturer = models.BooleanField(
        default=True,
        verbose_name="Peut clôturer les courriers"
    )

    inclure_structures_enfants = models.BooleanField(
        default=False,
        verbose_name="Accès aux structures rattachées"
    )

    actif = models.BooleanField(default=True)

    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["service__nom", "utilisateur__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "utilisateur"],
                name="unique_responsable_service"
            )
        ]
        verbose_name = "Responsable de structure"
        verbose_name_plural = "Responsables des structures"

    def __str__(self):
        return f"{self.utilisateur} - {self.service}"


# =====================================================
# COMPTEUR DES REFERENCES
# =====================================================

class CompteurReference(models.Model):

    sens = models.CharField(max_length=10)
    annee = models.PositiveIntegerField()
    dernier_numero = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sens", "annee"],
                name="unique_compteur_sens_annee"
            )
        ]
        verbose_name = "Compteur de référence"
        verbose_name_plural = "Compteurs de références"

    def __str__(self):
        return f"{self.sens}-{self.annee}: {self.dernier_numero}"


# =====================================================
# CATEGORIE DE COURRIER
# =====================================================

class CategorieCourrier(models.Model):

    nom = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nom de la catégorie"
    )

    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Catégorie de courrier"
        verbose_name_plural = "Catégories de courriers"

    def __str__(self):
        return self.nom


# =====================================================
# COURRIER
# =====================================================

class Courrier(models.Model):

    class Sens(models.TextChoices):
        ENTRANT = "ENTRANT", "Entrant"
        SORTANT = "SORTANT", "Sortant"

    class Priorite(models.TextChoices):
        NORMALE = "NORMALE", "Normale"
        URGENTE = "URGENTE", "Urgente"
        TRES_URGENTE = "TRES_URGENTE", "Très urgente"
        CONFIDENTIELLE = (
            "CONFIDENTIELLE",
            "Confidentielle (ancienne valeur)"
        )

    class Confidentialite(models.TextChoices):
        NORMALE = "NORMALE", "Normale"
        CONFIDENTIELLE = "CONFIDENTIELLE", "Confidentielle"
        STRICTE = "STRICTE", "Strictement confidentielle"

    class Statut(models.TextChoices):
        ENREGISTRE = "ENREGISTRE", "Enregistré"
        TRANSMIS = "TRANSMIS", "Transmis"
        EN_COURS = "EN_COURS", "En cours"
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        TRAITE = "TRAITE", "Traité"
        CLOTURE = "CLOTURE", "Clôturé"

    class ModeReception(models.TextChoices):
        PHYSIQUE = "PHYSIQUE", "Courrier physique"
        EMAIL = "EMAIL", "E-mail"
        COURSIER = "COURSIER", "Coursier"
        DEPOT = "DEPOT", "Dépôt direct"
        AUTRE = "AUTRE", "Autre"

    class StatutOrientation(models.TextChoices):
        NON_EVALUE = "NON_EVALUE", "Non évalué"
        A_VALIDER = "A_VALIDER", "À valider"
        AUTOMATIQUE = "AUTOMATIQUE", "Orienté automatiquement"
        VALIDEE = "VALIDEE", "Orientation validée"
        REFUSEE = "REFUSEE", "Orientation refusée"

    reference = models.CharField(
        max_length=30,
        unique=True,
        blank=True
    )

    sens = models.CharField(
        max_length=10,
        choices=Sens.choices
    )

    date_courrier = models.DateField(
        default=timezone.localdate
    )

    # Ancien champ conservé.
    date_reception_expedition = models.DateField(
        default=timezone.localdate
    )

    mode_reception = models.CharField(
        max_length=20,
        choices=ModeReception.choices,
        blank=True
    )

    date_reception_physique = models.DateTimeField(
        null=True,
        blank=True
    )

    nom_livreur = models.CharField(
        max_length=180,
        blank=True
    )

    date_expedition = models.DateField(
        null=True,
        blank=True
    )

    expediteur = models.CharField(max_length=180)
    destinataire = models.CharField(max_length=180)
    objet = models.CharField(max_length=250)
    description = models.TextField(blank=True)

    categorie = models.ForeignKey(
        CategorieCourrier,
        on_delete=models.PROTECT,
        related_name="courriers",
        null=True,
        blank=True
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="courriers",
        null=True,
        blank=True
    )

    # Ancien responsable conservé.
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courriers_responsables",
        null=True,
        blank=True
    )

    # Destinataire nominatif des courriers strictement confidentiels.
    destinataire_confidentiel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courriers_strictement_destines",
        null=True,
        blank=True
    )

    priorite = models.CharField(
        max_length=20,
        choices=Priorite.choices,
        default=Priorite.NORMALE
    )

    confidentialite = models.CharField(
        max_length=20,
        choices=Confidentialite.choices,
        default=Confidentialite.NORMALE
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.ENREGISTRE
    )

    # Informations du moteur d'orientation.
    orientation_statut = models.CharField(
        max_length=20,
        choices=StatutOrientation.choices,
        default=StatutOrientation.NON_EVALUE
    )

    orientation_confiance = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    orientation_motif = models.TextField(blank=True)

    orientation_service_propose = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="orientations_proposees",
        null=True,
        blank=True
    )

    orientation_validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orientations_validees",
        null=True,
        blank=True
    )

    orientation_date = models.DateTimeField(
        null=True,
        blank=True
    )

    orientation_automatique = models.BooleanField(default=False)

    date_limite = models.DateField(
        null=True,
        blank=True
    )

    date_cloture = models.DateField(
        null=True,
        blank=True
    )

    document = models.FileField(
        upload_to="courriers/%Y/%m/",
        blank=True,
        null=True
    )

    courrier_origine = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="courriers_reponse",
        null=True,
        blank=True
    )

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courriers_crees"
    )

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Courrier"
        verbose_name_plural = "Courriers"

        permissions = [
            ("transmettre_courrier", "Peut transmettre un courrier"),
            ("cloturer_courrier", "Peut clôturer un courrier"),
            ("traiter_courrier", "Peut traiter un courrier"),
            ("retourner_courrier", "Peut retourner un courrier"),
            ("reouvrir_courrier", "Peut rouvrir un courrier"),
            ("valider_orientation", "Peut valider une orientation"),
            ("consulter_confidentiel", "Peut consulter un courrier confidentiel"),
        ]

    def save(self, *args, **kwargs):

        if not self.reference:

            prefix = (
                "ENT"
                if self.sens == self.Sens.ENTRANT
                else "SOR"
            )

            annee = timezone.localdate().year

            with transaction.atomic():

                compteur, cree = (
                    CompteurReference.objects
                    .select_for_update()
                    .get_or_create(
                        sens=self.sens,
                        annee=annee,
                        defaults={"dernier_numero": 0}
                    )
                )

                if cree or compteur.dernier_numero == 0:

                    anciennes_references = (
                        Courrier.objects
                        .filter(
                            reference__startswith=f"{prefix}-{annee}-"
                        )
                        .values_list("reference", flat=True)
                    )

                    maximum = 0

                    for ancienne in anciennes_references:
                        try:
                            numero = int(ancienne.rsplit("-", 1)[1])
                            maximum = max(maximum, numero)
                        except (ValueError, IndexError):
                            continue

                    compteur.dernier_numero = max(
                        compteur.dernier_numero,
                        maximum
                    )

                compteur.dernier_numero += 1

                compteur.save(
                    update_fields=["dernier_numero"]
                )

                self.reference = (
                    f"{prefix}-{annee}-"
                    f"{compteur.dernier_numero:06d}"
                )

                super().save(*args, **kwargs)

        else:
            super().save(*args, **kwargs)

    def est_strictement_confidentiel(self):
        return self.confidentialite == self.Confidentialite.STRICTE

    def __str__(self):
        return f"{self.reference} – {self.objet}"


# =====================================================
# AFFECTATION / TRANSMISSION
# =====================================================

class Affectation(models.Model):

    class TypeAffectation(models.TextChoices):
        SERVICE = "SERVICE", "Transmission au service"
        AGENT = "AGENT", "Affectation à un agent"

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="affectations"
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="affectations"
    )

    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="affectations_agent"
    )

    type_affectation = models.CharField(
        max_length=20,
        choices=TypeAffectation.choices,
        default=TypeAffectation.SERVICE
    )

    transmis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transmissions_effectuees"
    )

    date_transmission = models.DateTimeField(
        default=timezone.now
    )

    instruction = models.TextField(blank=True)

    date_limite = models.DateField(
        null=True,
        blank=True
    )

    statut = models.CharField(
        max_length=30,
        default="TRANSMIS"
    )

    observation = models.TextField(blank=True)

    active = models.BooleanField(
        default=True,
        verbose_name="Affectation active"
    )

    date_confirmation_reception = models.DateTimeField(
        null=True,
        blank=True
    )

    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="affectations_confirmees",
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-date_transmission"]
        verbose_name = "Affectation"
        verbose_name_plural = "Affectations"

    def save(self, *args, **kwargs):

        # Déduction du type pour les anciennes créations.
        if self.agent_id and self.type_affectation == self.TypeAffectation.SERVICE:
            self.type_affectation = self.TypeAffectation.AGENT

        super().save(*args, **kwargs)

    def __str__(self):
        if self.agent_id:
            return f"{self.courrier.reference} - {self.agent}"
        return f"{self.courrier.reference} - {self.service}"


# =====================================================
# DELEGATION TEMPORAIRE DE TRANSMISSION
# =====================================================

class DelegationTransmission(models.Model):

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delegations_recues"
    )

    autorise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delegations_autorisees"
    )

    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    motif = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Délégation de transmission"
        verbose_name_plural = "Délégations de transmission"

    def est_valide(self):
        maintenant = timezone.now()

        return (
            self.actif
            and self.date_debut <= maintenant
            and self.date_fin >= maintenant
        )

    def __str__(self):
        return f"Délégation de {self.utilisateur}"


# =====================================================
# RETOUR D'UN COURRIER AU SECRETARIAT
# =====================================================

class RetourCourrier(models.Model):

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="retours"
    )

    retourne_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courriers_retournes"
    )

    motif = models.TextField()
    date_retour = models.DateTimeField(auto_now_add=True)

    nouveau_courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="origine_retour",
        null=True,
        blank=True
    )

    traite = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date_retour"]
        verbose_name = "Retour de courrier"
        verbose_name_plural = "Retours de courriers"

    def __str__(self):
        return f"Retour {self.courrier.reference}"


# =====================================================
# PIECES JOINTES ET VERSIONS
# =====================================================

class PieceJointe(models.Model):

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="pieces_jointes"
    )

    fichier = models.FileField(
        upload_to="courriers/pieces_jointes/%Y/%m/"
    )

    nom_original = models.CharField(max_length=255)
    type_mime = models.CharField(max_length=120, blank=True)
    taille = models.PositiveBigIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)

    version_precedente = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="versions_suivantes",
        null=True,
        blank=True
    )

    ajoute_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pieces_jointes_ajoutees"
    )

    ajoute_le = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    motif_retrait = models.TextField(blank=True)

    retire_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pieces_jointes_retirees",
        null=True,
        blank=True
    )

    retire_le = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-ajoute_le"]
        verbose_name = "Pièce jointe"
        verbose_name_plural = "Pièces jointes"

    def __str__(self):
        return f"{self.nom_original} - {self.courrier.reference}"


# =====================================================
# BORDEREAU COLLECTIF DE TRANSMISSION
# =====================================================

class BordereauTransmission(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="bordereaux"
    )

    date_transmission = models.DateTimeField(
        default=timezone.now
    )

    transmis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bordereaux_transmis"
    )

    statut = models.CharField(
        max_length=20,
        choices=[
            ("TRANSMIS", "Transmis"),
            ("RECEPTIONNE", "Réceptionné"),
        ],
        default="TRANSMIS"
    )

    class Meta:
        ordering = ["-date_transmission"]
        verbose_name = "Bordereau de transmission"
        verbose_name_plural = "Bordereaux de transmission"

    def __str__(self):
        return f"Bordereau {self.pk} - {self.service}"


class LigneBordereau(models.Model):

    bordereau = models.ForeignKey(
        BordereauTransmission,
        on_delete=models.PROTECT,
        related_name="lignes"
    )

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="lignes_bordereaux"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bordereau", "courrier"],
                name="unique_courrier_bordereau"
            )
        ]
        verbose_name = "Ligne de bordereau"
        verbose_name_plural = "Lignes de bordereau"

    def __str__(self):
        return f"{self.courrier.reference}"


class ReceptionBordereau(models.Model):

    bordereau = models.OneToOneField(
        BordereauTransmission,
        on_delete=models.PROTECT,
        related_name="reception"
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT
    )

    receptionne_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    date_reception = models.DateTimeField(auto_now_add=True)
    observation = models.TextField(blank=True)

    class Meta:
        verbose_name = "Réception de bordereau"
        verbose_name_plural = "Réceptions de bordereaux"

    def __str__(self):
        return f"Réception bordereau {self.bordereau_id}"


# =====================================================
# HISTORIQUE ET TRACABILITE
# =====================================================

class Historique(models.Model):

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="historique"
    )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    avant = models.TextField(blank=True)
    apres = models.TextField(blank=True)
    motif = models.TextField(blank=True)

    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action"]
        verbose_name = "Historique"
        verbose_name_plural = "Historiques"

    def __str__(self):
        return f"{self.action} - {self.courrier.reference}"


# =====================================================
# AUTORISATIONS D'ACCES AUX COURRIERS CONFIDENTIELS
# =====================================================

class AutorisationConfidentialite(models.Model):

    class TypeAcces(models.TextChoices):
        CONTENU = "CONTENU", "Consulter le contenu"
        PIECES_JOINTES = "PIECES_JOINTES", "Consulter les pièces jointes"
        HISTORIQUE = "HISTORIQUE", "Consulter l'historique"

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="autorisations_confidentialite"
    )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="autorisations_confidentialite"
    )

    type_acces = models.CharField(
        max_length=20,
        choices=TypeAcces.choices,
        default=TypeAcces.CONTENU
    )

    autorise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="autorisations_confidentialite_accordees"
    )

    motif = models.TextField()

    date_debut = models.DateTimeField(default=timezone.now)

    date_fin = models.DateTimeField(
        null=True,
        blank=True
    )

    actif = models.BooleanField(default=True)

    revoque_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="autorisations_confidentialite_revoquees",
        null=True,
        blank=True
    )

    date_revocation = models.DateTimeField(
        null=True,
        blank=True
    )

    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Autorisation confidentielle"
        verbose_name_plural = "Autorisations confidentielles"

    def est_valide(self):
        maintenant = timezone.now()

        return (
            self.actif
            and self.date_debut <= maintenant
            and (
                self.date_fin is None
                or self.date_fin >= maintenant
            )
            and self.date_revocation is None
        )

    def __str__(self):
        return (
            f"{self.utilisateur} - "
            f"{self.courrier.reference} - {self.type_acces}"
        )


# =====================================================
# REGLES D'ORIENTATION AUTOMATIQUE
# =====================================================

class RegleOrientation(models.Model):

    class ModeCorrespondance(models.TextChoices):
        AU_MOINS_UN = "AU_MOINS_UN", "Au moins un mot-clé"
        TOUS = "TOUS", "Tous les mots-clés"

    nom = models.CharField(max_length=150)

    categorie = models.ForeignKey(
        CategorieCourrier,
        on_delete=models.PROTECT,
        related_name="regles_orientation",
        null=True,
        blank=True
    )

    mots_cles = models.TextField(
        blank=True,
        help_text="Mots-clés séparés par des virgules"
    )

    mode_correspondance = models.CharField(
        max_length=20,
        choices=ModeCorrespondance.choices,
        default=ModeCorrespondance.AU_MOINS_UN
    )

    service_destination = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="regles_orientation"
    )

    priorite_regle = models.PositiveIntegerField(default=10)

    seuil_confiance = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=80.00
    )

    actif = models.BooleanField(default=True)

    description = models.TextField(blank=True)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="regles_orientation_creees",
        null=True,
        blank=True
    )

    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priorite_regle", "nom"]
        verbose_name = "Règle d'orientation"
        verbose_name_plural = "Règles d'orientation"

    def __str__(self):
        return self.nom


# =====================================================
# JOURNAL DES ACCES CONFIDENTIELS
# =====================================================

class JournalAccesConfidentiel(models.Model):

    class Action(models.TextChoices):
        CONSULTATION_CONTENU = (
            "CONSULTATION_CONTENU",
            "Consultation du contenu"
        )
        CONSULTATION_PIECE = (
            "CONSULTATION_PIECE",
            "Consultation d'une pièce jointe"
        )
        CONSULTATION_HISTORIQUE = (
            "CONSULTATION_HISTORIQUE",
            "Consultation de l'historique"
        )
        EXPORT = "EXPORT", "Export"

    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.PROTECT,
        related_name="journal_acces_confidentiels"
    )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="journal_acces_confidentiels"
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices
    )

    motif = models.TextField(blank=True)

    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action"]
        verbose_name = "Journal d'accès confidentiel"
        verbose_name_plural = "Journaux des accès confidentiels"

    def __str__(self):
        return (
            f"{self.utilisateur} - "
            f"{self.courrier.reference} - {self.action}"
        )


# =====================================================
# PARAMETRES GENERAUX GSC
# =====================================================

class ParametreGSC(models.Model):

    delai_defaut_jours = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Délai de traitement par défaut"
    )

    duree_conservation_annees = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Durée de conservation (années)"
    )

    alerte_retard_active = models.BooleanField(default=True)

    notification_email_active = models.BooleanField(default=True)

    # Seuil minimal de confiance pour une orientation automatique.
    seuil_orientation_automatique = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=80.00,
        verbose_name="Seuil de confiance de l'orientation automatique"
    )

    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paramètre GSC"
        verbose_name_plural = "Paramètres GSC"

    def __str__(self):
        return "Paramètres généraux GSC"
