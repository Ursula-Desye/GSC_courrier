
import unicodedata

from django.db.models import Q
from django.utils import timezone

from .models import (
    Courrier,
    Service,
    Affectation,
    DelegationTransmission,
    ResponsableService,
    AutorisationConfidentialite,
)


# ============================================================
# NORMALISATION DES NOMS DE GROUPES
# ============================================================

def normaliser_nom(valeur):
    valeur = unicodedata.normalize("NFD", str(valeur or ""))
    valeur = "".join(
        caractere
        for caractere in valeur
        if unicodedata.category(caractere) != "Mn"
    )
    return " ".join(valeur.strip().casefold().split())


# ============================================================
# IDENTIFICATION DES PROFILS
# ============================================================

def obtenir_profil(user):
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return None

    if getattr(user, "is_superuser", False):
        return "ADMIN"

    groupes = {
        normaliser_nom(nom)
        for nom in user.groups.values_list("name", flat=True)
    }

    correspondances = [
        ("accueil", "ACCUEIL"),
        ("secretariat", "SECRETARIAT"),
        ("direction", "DIRECTION"),
        ("responsable de service", "RESPONSABLE"),
        ("responsable", "RESPONSABLE"),
        ("agent", "AGENT"),
    ]

    for nom, profil in correspondances:
        if normaliser_nom(nom) in groupes:
            return profil

    return None


def obtenir_profils(user):
    profil = obtenir_profil(user)
    return {profil} if profil else set()


# ============================================================
# IDENTIFICATION DES ROLES
# ============================================================

def est_administrateur(user):
    return obtenir_profil(user) == "ADMIN"


def utilisateur_est_direction(user):
    return obtenir_profil(user) == "DIRECTION"


def utilisateur_est_responsable(user):
    return obtenir_profil(user) == "RESPONSABLE"


def utilisateur_est_agent(user):
    return obtenir_profil(user) == "AGENT"


def utilisateur_est_secretariat(user):
    return obtenir_profil(user) == "SECRETARIAT"


def utilisateur_est_accueil(user):
    return obtenir_profil(user) == "ACCUEIL"


# ============================================================
# PERMISSIONS GENERALES
# ============================================================

def utilisateur_peut_consulter(user):
    profil = obtenir_profil(user)

    if profil is None:
        return False

    return (
        profil == "ADMIN"
        or user.has_perm("courrier.view_courrier")
    )


def utilisateur_peut_enregistrer(user):
    profil = obtenir_profil(user)

    return (
        profil in ["ADMIN", "ACCUEIL", "SECRETARIAT"]
        and user.has_perm("courrier.add_courrier")
    )


def utilisateur_peut_modifier(user):
    profil = obtenir_profil(user)

    return (
        profil in ["SECRETARIAT", "RESPONSABLE"]
        and user.has_perm("courrier.change_courrier")
    )


# ============================================================
# RESPONSABILITES DES STRUCTURES
# ============================================================

def responsabilites_actives(user):
    if not user or not getattr(user, "is_authenticated", False):
        return ResponsableService.objects.none()

    return ResponsableService.objects.filter(
        utilisateur=user,
        actif=True,
        service__actif=True,
    ).select_related(
        "service",
        "service__parent",
    ).prefetch_related(
        "categories",
    )


def services_du_responsable(user):
    if obtenir_profil(user) != "RESPONSABLE":
        return Service.objects.none()

    services_configures = Service.objects.filter(
        responsables_configures__utilisateur=user,
        responsables_configures__actif=True,
        actif=True,
    )

    anciens_services = Service.objects.filter(
        responsable=user,
        actif=True,
    )

    return (services_configures | anciens_services).distinct()


def utilisateur_est_responsable_du_service(user, service):
    if (
        obtenir_profil(user) not in ["RESPONSABLE", "DIRECTION"]
        or service is None
        or not service.actif
    ):
        return False

    return (
        service.responsable_id == user.pk
        or ResponsableService.objects.filter(
            utilisateur=user,
            service=service,
            actif=True,
            service__actif=True,
        ).exists()
    )


def responsabilite_sur_service(user, service):
    if service is None:
        return None

    return ResponsableService.objects.filter(
        utilisateur=user,
        service=service,
        actif=True,
        service__actif=True,
    ).first()


def services_accessibles_du_responsable(user):
    services = services_du_responsable(user)
    ids = set(services.values_list("id", flat=True))

    responsabilites = responsabilites_actives(user).filter(
        inclure_structures_enfants=True
    )

    for responsabilite in responsabilites:
        nouveaux_ids = set(
            Service.objects.filter(
                parent=responsabilite.service,
                actif=True,
            ).values_list("id", flat=True)
        )

        ids.update(nouveaux_ids)

        while nouveaux_ids:
            enfants = Service.objects.filter(
                parent_id__in=nouveaux_ids,
                actif=True,
            )

            nouveaux_ids = set(
                enfants.values_list("id", flat=True)
            )

            ids.update(nouveaux_ids)

    return Service.objects.filter(
        id__in=ids,
        actif=True,
    )


def utilisateur_est_responsable_du_courrier(user, courrier):
    if (
        courrier is None
        or not courrier.service_id
        or obtenir_profil(user) != "RESPONSABLE"
    ):
        return False

    return services_accessibles_du_responsable(user).filter(
        pk=courrier.service_id
    ).exists()


def responsable_peut_gerer_categorie(user, courrier):
    if courrier is None or not courrier.service_id:
        return False

    responsabilites = responsabilites_actives(user).filter(
        service_id=courrier.service_id
    )

    # Une responsabilité configurée est prioritaire.
    # Elle ne doit jamais être contournée par l'ancien champ
    # Service.responsable.
    if responsabilites.exists():
        for responsabilite in responsabilites:
            if responsabilite.toutes_categories:
                return True

            if (
                courrier.categorie_id
                and responsabilite.categories.filter(
                    pk=courrier.categorie_id
                ).exists()
            ):
                return True

        return False

    # Compatibilité avec les anciennes configurations seulement
    # lorsqu'aucune responsabilité détaillée n'existe.
    return Service.objects.filter(
        pk=courrier.service_id,
        responsable=user,
        actif=True,
    ).exists()


def responsable_peut_affecter_agents(user, service):
    if service is None:
        return False

    responsabilite = responsabilite_sur_service(user, service)

    if responsabilite:
        return responsabilite.peut_affecter_agents

    return service.responsable_id == getattr(user, "pk", None)


def responsable_peut_cloturer(user, service):
    if service is None:
        return False

    responsabilite = responsabilite_sur_service(user, service)

    if responsabilite:
        return responsabilite.peut_cloturer

    return service.responsable_id == getattr(user, "pk", None)


# ============================================================
# CONFIDENTIALITE
# ============================================================

def courrier_est_confidentiel(courrier):
    if courrier is None:
        return False

    return (
        courrier.confidentialite in [
            Courrier.Confidentialite.CONFIDENTIELLE,
            Courrier.Confidentialite.STRICTE,
        ]
        or courrier.priorite == Courrier.Priorite.CONFIDENTIELLE
    )


def courrier_est_strictement_confidentiel(courrier):
    if courrier is None:
        return False

    return (
        courrier.confidentialite
        == Courrier.Confidentialite.STRICTE
    )


def autorisation_confidentielle_valide(
    user,
    courrier,
    type_acces="CONTENU",
):
    if (
        user is None
        or courrier is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False

    maintenant = timezone.now()

    return AutorisationConfidentialite.objects.filter(
        utilisateur=user,
        courrier=courrier,
        type_acces=type_acces,
        actif=True,
        date_debut__lte=maintenant,
        date_revocation__isnull=True,
    ).filter(
        Q(date_fin__isnull=True)
        | Q(date_fin__gte=maintenant)
    ).exists()


def utilisateur_est_destinataire_confidentiel(user, courrier):
    return bool(
        user
        and courrier
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and courrier.destinataire_confidentiel_id == user.pk
    )


def utilisateur_peut_consulter_contenu_confidentiel(
    user,
    courrier,
):
    if (
        user is None
        or courrier is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False

    if not courrier_est_confidentiel(courrier):
        return utilisateur_peut_consulter_courrier(user, courrier)

    # Le destinataire désigné bénéficie uniquement du droit CONTENU.
    if utilisateur_est_destinataire_confidentiel(user, courrier):
        return True

    return autorisation_confidentielle_valide(
        user,
        courrier,
        "CONTENU",
    )


def utilisateur_peut_consulter_piece_confidentielle(
    user,
    courrier,
):
    if user is None or courrier is None:
        return False

    if not courrier_est_confidentiel(courrier):
        return (
            utilisateur_peut_consulter_courrier(user, courrier)
            and utilisateur_peut_consulter_contenu_courrier(
                user,
                courrier,
            )
        )

    # Le destinataire désigné n'a PAS automatiquement accès
    # aux pièces jointes.
    return autorisation_confidentielle_valide(
        user,
        courrier,
        "PIECES_JOINTES",
    )


def utilisateur_peut_consulter_historique_confidentiel(
    user,
    courrier,
):
    if user is None or courrier is None:
        return False

    if not courrier_est_confidentiel(courrier):
        return (
            utilisateur_peut_consulter_courrier(
                user,
                courrier,
            )
            and utilisateur_peut_consulter_contenu_courrier(
                user,
                courrier,
            )
        )

    # Le destinataire désigné n'a PAS automatiquement accès
    # à l'historique.
    return autorisation_confidentielle_valide(
        user,
        courrier,
        "HISTORIQUE",
    )


def courrier_est_deja_transmis(courrier):
    if courrier is None:
        return False

    return (
        courrier.statut != Courrier.Statut.ENREGISTRE
        or courrier.affectations.filter(active=True).exists()
    )


# ============================================================
# DELEGATION TEMPORAIRE DE TRANSMISSION
# ============================================================

def utilisateur_a_delegation_valide(user):
    if obtenir_profil(user) != "SECRETARIAT":
        return False

    maintenant = timezone.now()

    return DelegationTransmission.objects.filter(
        utilisateur=user,
        actif=True,
        date_debut__lte=maintenant,
        date_fin__gte=maintenant,
        autorise_par__is_active=True,
        autorise_par__is_superuser=True,
    ).exists()


# ============================================================
# CONSULTATION DES METADONNEES
# ============================================================

def utilisateur_peut_consulter_courrier(user, courrier):
    profil = obtenir_profil(user)

    if profil is None or courrier is None:
        return False

    if courrier_est_confidentiel(courrier):
        # Une désignation nominative permet d'accéder à la fiche
        # pour consulter le contenu, mais pas les pièces ni l'historique.
        if utilisateur_est_destinataire_confidentiel(user, courrier):
            return True

        # Un droit CONTENU autorise l'accès à la fiche.
        # Les droits PIECES_JOINTES et HISTORIQUE seuls ne donnent
        # pas accès au contenu du courrier.
        if autorisation_confidentielle_valide(
            user, courrier, "CONTENU"
        ):
            return True

        # Pour accéder directement à une pièce ou à l'historique,
        # la vue dédiée peut vérifier le droit correspondant.
        # On autorise ici l'accès technique à la fiche uniquement
        # pour les personnes disposant de l'un de ces droits.
        if (
            autorisation_confidentielle_valide(
                user, courrier, "PIECES_JOINTES"
            )
            or autorisation_confidentielle_valide(
                user, courrier, "HISTORIQUE"
            )
        ):
            return True

    if not utilisateur_peut_consulter(user):
        return False

    if profil == "ADMIN":
        return not courrier_est_confidentiel(courrier)

    if profil in ["ACCUEIL", "SECRETARIAT"]:
        return True

    if profil == "DIRECTION":
        if not courrier.service_id:
            return False

        return utilisateur_est_responsable_du_service(
            user,
            courrier.service,
        )

    if profil == "RESPONSABLE":
        return (
            utilisateur_est_responsable_du_courrier(
                user,
                courrier,
            )
            and responsable_peut_gerer_categorie(
                user,
                courrier,
            )
        )

    if profil == "AGENT":
        return agent_est_affecte_au_courrier(
            user,
            courrier,
        )

    return False


# ============================================================
# CONSULTATION DU CONTENU
# ============================================================

def utilisateur_peut_consulter_contenu_courrier(
    user,
    courrier,
):
    if user is None or courrier is None:
        return False

    if courrier_est_confidentiel(courrier):
        return utilisateur_peut_consulter_contenu_confidentiel(
            user,
            courrier,
        )

    return (
        utilisateur_peut_consulter_courrier(user, courrier)
        and getattr(user, "is_active", False)
    )


# ============================================================
# MODIFICATION D'UN COURRIER
# ============================================================

def utilisateur_peut_modifier_courrier(user, courrier):
    profil = obtenir_profil(user)

    if profil is None or courrier is None:
        return False

    if profil in ["ACCUEIL", "DIRECTION", "AGENT"]:
        return False

    if not user.has_perm("courrier.change_courrier"):
        return False

    if profil == "ADMIN":
        return not courrier_est_confidentiel(courrier)

    if not utilisateur_peut_consulter_contenu_courrier(
        user,
        courrier,
    ):
        return False

    if profil == "SECRETARIAT":
        return not courrier_est_deja_transmis(courrier)

    if profil == "RESPONSABLE":
        return (
            utilisateur_est_responsable_du_courrier(
                user,
                courrier,
            )
            and responsable_peut_gerer_categorie(
                user,
                courrier,
            )
            and courrier.statut != Courrier.Statut.CLOTURE
        )

    return False


# ============================================================
# TRANSMISSION INITIALE
# ============================================================

def utilisateur_peut_transmettre(user, courrier=None):
    profil = obtenir_profil(user)

    if profil not in ["ACCUEIL", "SECRETARIAT"]:
        return False

    if not user.has_perm("courrier.transmettre_courrier"):
        return False

    if courrier is not None:
        if courrier.sens != Courrier.Sens.ENTRANT:
            return False

        if courrier.statut != Courrier.Statut.ENREGISTRE:
            return False

        if courrier_est_deja_transmis(courrier):
            return False

    if profil == "ACCUEIL":
        return True

    return utilisateur_a_delegation_valide(user)


# ============================================================
# AFFECTATION A UN AGENT
# ============================================================

def utilisateur_peut_affecter_agent(user, courrier):
    if obtenir_profil(user) != "RESPONSABLE":
        return False

    if courrier is None or not courrier.service_id:
        return False

    if not user.has_perm("courrier.change_courrier"):
        return False

    if not utilisateur_est_responsable_du_courrier(
        user,
        courrier,
    ):
        return False

    if not responsable_peut_gerer_categorie(user, courrier):
        return False

    if not responsable_peut_affecter_agents(
        user,
        courrier.service,
    ):
        return False

    if not utilisateur_peut_consulter_contenu_courrier(
        user,
        courrier,
    ):
        return False

    return (
        courrier.sens == Courrier.Sens.ENTRANT
        and courrier.statut in [
            Courrier.Statut.TRANSMIS,
            Courrier.Statut.EN_COURS,
            Courrier.Statut.EN_ATTENTE,
        ]
    )


# ============================================================
# VERIFICATION D'UNE AFFECTATION AGENT
# ============================================================

def agent_est_affecte_au_courrier(user, courrier):
    if user is None or courrier is None:
        return False

    return Affectation.objects.filter(
        courrier=courrier,
        agent=user,
        type_affectation="AGENT",
        active=True,
    ).exists()


# ============================================================
# TRAITEMENT
# ============================================================

def utilisateur_peut_traiter_courrier(user, courrier):
    profil = obtenir_profil(user)

    if profil not in ["AGENT", "RESPONSABLE"]:
        return False

    if courrier is None:
        return False

    if courrier.sens != Courrier.Sens.ENTRANT:
        return False

    if courrier.statut not in [
        Courrier.Statut.TRANSMIS,
        Courrier.Statut.EN_COURS,
        Courrier.Statut.EN_ATTENTE,
    ]:
        return False

    if not user.has_perm("courrier.traiter_courrier"):
        return False

    if not utilisateur_peut_consulter_contenu_courrier(
        user,
        courrier,
    ):
        return False

    if profil == "AGENT":
        return agent_est_affecte_au_courrier(
            user,
            courrier,
        )

    return (
        utilisateur_est_responsable_du_courrier(
            user,
            courrier,
        )
        and responsable_peut_gerer_categorie(
            user,
            courrier,
        )
    )


# ============================================================
# CLOTURE
# ============================================================

def utilisateur_peut_cloturer(user):
    return (
        obtenir_profil(user) == "RESPONSABLE"
        and user.has_perm("courrier.cloturer_courrier")
    )


def utilisateur_peut_cloturer_courrier(user, courrier):
    if obtenir_profil(user) != "RESPONSABLE":
        return False

    if courrier is None or not courrier.service_id:
        return False

    if not user.has_perm("courrier.cloturer_courrier"):
        return False

    if not utilisateur_peut_consulter_contenu_courrier(
        user,
        courrier,
    ):
        return False

    return (
        courrier.sens == Courrier.Sens.ENTRANT
        and courrier.statut == Courrier.Statut.TRAITE
        and utilisateur_est_responsable_du_courrier(
            user,
            courrier,
        )
        and responsable_peut_gerer_categorie(
            user,
            courrier,
        )
        and responsable_peut_cloturer(
            user,
            courrier.service,
        )
    )


# ============================================================
# RETOUR AU SECRETARIAT
# ============================================================

def utilisateur_peut_retourner_courrier(user, courrier):
    if obtenir_profil(user) != "RESPONSABLE":
        return False

    if courrier is None:
        return False

    if not user.has_perm("courrier.retourner_courrier"):
        return False

    if not utilisateur_peut_consulter_contenu_courrier(
        user,
        courrier,
    ):
        return False

    return (
        courrier.sens == Courrier.Sens.ENTRANT
        and courrier.statut in [
            Courrier.Statut.TRANSMIS,
            Courrier.Statut.EN_COURS,
            Courrier.Statut.EN_ATTENTE,
            Courrier.Statut.TRAITE,
        ]
        and utilisateur_est_responsable_du_courrier(
            user,
            courrier,
        )
        and responsable_peut_gerer_categorie(
            user,
            courrier,
        )
    )


# ============================================================
# REOUVERTURE
# ============================================================

def utilisateur_peut_reouvrir_courrier(user, courrier):
    profil = obtenir_profil(user)

    if profil is None or courrier is None:
        return False

    if courrier.statut != Courrier.Statut.CLOTURE:
        return False

    if not user.has_perm("courrier.reouvrir_courrier"):
        return False

    if not utilisateur_peut_consulter_contenu_courrier(
        user,
        courrier,
    ):
        return False

    if profil == "ADMIN":
        return not courrier_est_confidentiel(courrier)

    if profil == "RESPONSABLE":
        return (
            courrier.sens == Courrier.Sens.ENTRANT
            and utilisateur_est_responsable_du_courrier(
                user,
                courrier,
            )
            and responsable_peut_gerer_categorie(
                user,
                courrier,
            )
        )

    return False


# ============================================================
# VALIDATION D'ORIENTATION
# ============================================================

def utilisateur_peut_valider_orientation(user):
    profil = obtenir_profil(user)

    return (
        profil in ["ACCUEIL", "SECRETARIAT"]
        and user.has_perm("courrier.valider_orientation")
    )


# ============================================================
# GESTION DES AUTORISATIONS CONFIDENTIELLES
# ============================================================

def utilisateur_peut_gerer_autorisations_confidentielles(
    user,
    courrier,
):
    if user is None or courrier is None:
        return False

    profil = obtenir_profil(user)

    if profil not in ["SECRETARIAT", "RESPONSABLE", "DIRECTION"]:
        return False

    if not user.has_perm("courrier.consulter_confidentiel"):
        return False

    if profil == "SECRETARIAT":
        return True

    if not courrier.service_id:
        return False

    if profil == "DIRECTION":
        return utilisateur_est_responsable_du_service(
            user,
            courrier.service,
        )

    return (
        utilisateur_est_responsable_du_courrier(
            user,
            courrier,
        )
        and responsable_peut_gerer_categorie(
            user,
            courrier,
        )
    )
