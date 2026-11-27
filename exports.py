from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
)

from .models import Courrier
from .views import courriers_accessibles
from .permissions import utilisateur_peut_consulter_contenu_courrier


# ============================================================
# RECUPERATION DES COURRIERS EXPORTABLES
# ============================================================

def obtenir_courriers_export(request):

    if not request.user.is_authenticated:
        raise PermissionDenied

    courriers = courriers_accessibles(request.user)

    recherche = request.GET.get("q", "").strip()
    sens = request.GET.get("sens", "").strip()
    statut = request.GET.get("statut", "").strip()

    if recherche:
        courriers = courriers.filter(
            Q(reference__icontains=recherche)
            | Q(objet__icontains=recherche)
            | Q(expediteur__icontains=recherche)
            | Q(destinataire__icontains=recherche)
            | Q(description__icontains=recherche)
        )

    if sens in [
        Courrier.Sens.ENTRANT,
        Courrier.Sens.SORTANT,
    ]:
        courriers = courriers.filter(sens=sens)

    statuts_valides = [
        choix[0] for choix in Courrier.Statut.choices
    ]

    if statut in statuts_valides:
        courriers = courriers.filter(statut=statut)

    # Un export contient des informations sur le contenu du courrier.
    # Les courriers dont le contenu n'est pas consultable sont exclus.
    identifiants_autorises = []

    for courrier in courriers.iterator(chunk_size=500):
        if utilisateur_peut_consulter_contenu_courrier(
            request.user,
            courrier,
        ):
            identifiants_autorises.append(courrier.pk)

    return (
        Courrier.objects
        .filter(pk__in=identifiants_autorises)
        .select_related(
            "service",
            "responsable",
            "categorie",
            "cree_par",
        )
        .order_by("-date_courrier", "-pk")
    )


# ============================================================
# UTILITAIRES
# ============================================================

def valeur_texte(valeur):

    if valeur is None:
        return ""

    return str(valeur)


def valeur_pdf(valeur):

    texte = valeur_texte(valeur)

    return escape(texte).replace("\n", "<br/>")


def nom_fichier_export(extension):

    return (
        f"GSC_Courriers_"
        f"{timezone.localdate():%Y%m%d}.{extension}"
    )


# ============================================================
# EXPORT EXCEL
# ============================================================

@login_required
def exporter_courriers_excel(request):

    courriers = obtenir_courriers_export(request)

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Courriers"

    entetes = [
        "Référence",
        "Sens",
        "Date du courrier",
        "Date réception / expédition",
        "Expéditeur",
        "Destinataire",
        "Objet",
        "Catégorie",
        "Service",
        "Responsable",
        "Priorité",
        "Confidentialité",
        "Statut",
        "Date limite",
        "Date de clôture",
        "Enregistré par",
        "Date d'enregistrement",
    ]

    feuille.append(entetes)

    for cellule in feuille[1]:

        cellule.font = Font(
            bold=True,
            color="FFFFFF",
            size=10,
        )

        cellule.fill = PatternFill(
            fill_type="solid",
            fgColor="17365D",
        )

        cellule.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    for courrier in courriers.iterator(chunk_size=1000):

        valeurs = [
            valeur_texte(courrier.reference),
            courrier.get_sens_display(),
            courrier.date_courrier,
            courrier.date_reception_expedition,
            valeur_texte(courrier.expediteur),
            valeur_texte(courrier.destinataire),
            valeur_texte(courrier.objet),
            valeur_texte(courrier.categorie),
            valeur_texte(courrier.service),
            valeur_texte(courrier.responsable),
            courrier.get_priorite_display(),
            courrier.get_confidentialite_display(),
            courrier.get_statut_display(),
            courrier.date_limite,
            courrier.date_cloture,
            valeur_texte(courrier.cree_par),
            (
                timezone.localtime(courrier.cree_le).replace(tzinfo=None)
                if courrier.cree_le
                else None
            ),
        ]

        feuille.append(valeurs)

        derniere_ligne = feuille.max_row

        # Evite l'interpretation des champs textuels comme formules Excel.
        colonnes_texte = [
            1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16
        ]

        for numero_colonne in colonnes_texte:

            cellule = feuille.cell(
                row=derniere_ligne,
                column=numero_colonne,
            )

            if cellule.value is not None:
                cellule.data_type = "s"

    largeurs = [
        22, 14, 15, 22, 25, 25, 40, 20, 22,
        22, 16, 20, 18, 15, 15, 22, 22,
    ]

    for index, largeur in enumerate(largeurs, start=1):

        feuille.column_dimensions[
            get_column_letter(index)
        ].width = largeur

    feuille.freeze_panes = "A2"
    feuille.auto_filter.ref = feuille.dimensions
    feuille.row_dimensions[1].height = 32

    for ligne in feuille.iter_rows(min_row=2):

        for cellule in ligne:
            cellule.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

        for numero_colonne in [3, 4, 14, 15]:
            ligne[numero_colonne - 1].number_format = "DD/MM/YYYY"

        ligne[16].number_format = "DD/MM/YYYY HH:MM"

    tampon = BytesIO()

    classeur.save(tampon)
    tampon.seek(0)

    response = HttpResponse(
        tampon.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{nom_fichier_export("xlsx")}"'
    )

    response["X-Content-Type-Options"] = "nosniff"

    return response


# ============================================================
# EXPORT PDF
# ============================================================

@login_required
def exporter_courriers_pdf(request):

    courriers = obtenir_courriers_export(request)

    tampon = BytesIO()

    document = SimpleDocTemplate(
        tampon,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="GSC - Liste des courriers",
        author="GSC",
    )

    styles = getSampleStyleSheet()

    titre_style = ParagraphStyle(
        "TitreGSC",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17365D"),
        spaceAfter=8,
    )

    info_style = ParagraphStyle(
        "InfoGSC",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        alignment=TA_LEFT,
        spaceAfter=8,
    )

    cellule_style = ParagraphStyle(
        "CelluleGSC",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )

    entete_style = ParagraphStyle(
        "EnteteGSC",
        parent=cellule_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    elements = []

    elements.append(
        Paragraph(
            "GSC - GESTION ET SUIVI DU COURRIER",
            titre_style,
        )
    )

    nombre_courriers = courriers.count()

    elements.append(
        Paragraph(
            (
                f"État des courriers au "
                f"{timezone.localtime():%d/%m/%Y à %H:%M}"
                f" | Nombre de courriers : {nombre_courriers}"
            ),
            info_style,
        )
    )

    entetes = [
        "Référence",
        "Date",
        "Sens",
        "Expéditeur",
        "Destinataire",
        "Objet",
        "Service",
        "Statut",
    ]

    donnees = [
        [
            Paragraph(valeur_pdf(titre), entete_style)
            for titre in entetes
        ]
    ]

    for courrier in courriers.iterator(chunk_size=1000):

        valeurs = [
            valeur_texte(courrier.reference),
            (
                courrier.date_courrier.strftime("%d/%m/%Y")
                if courrier.date_courrier
                else ""
            ),
            courrier.get_sens_display(),
            valeur_texte(courrier.expediteur),
            valeur_texte(courrier.destinataire),
            valeur_texte(courrier.objet),
            valeur_texte(courrier.service),
            courrier.get_statut_display(),
        ]

        donnees.append([
            Paragraph(
                valeur_pdf(valeur),
                cellule_style,
            )
            for valeur in valeurs
        ])

    if nombre_courriers == 0:

        donnees.append([
            Paragraph(
                "Aucun courrier disponible pour les critères sélectionnés.",
                cellule_style,
            ),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ])

    tableau = Table(
        donnees,
        colWidths=[
            27 * mm,
            18 * mm,
            18 * mm,
            35 * mm,
            35 * mm,
            65 * mm,
            35 * mm,
            24 * mm,
        ],
        repeatRows=1,
    )

    tableau.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#17365D"),
        ),
        (
            "TEXTCOLOR",
            (0, 0),
            (-1, 0),
            colors.white,
        ),
        (
            "GRID",
            (0, 0),
            (-1, -1),
            0.35,
            colors.HexColor("#D5DDE8"),
        ),
        (
            "VALIGN",
            (0, 0),
            (-1, -1),
            "TOP",
        ),
        (
            "LEFTPADDING",
            (0, 0),
            (-1, -1),
            4,
        ),
        (
            "RIGHTPADDING",
            (0, 0),
            (-1, -1),
            4,
        ),
        (
            "TOPPADDING",
            (0, 0),
            (-1, -1),
            5,
        ),
        (
            "BOTTOMPADDING",
            (0, 0),
            (-1, -1),
            5,
        ),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [
                colors.white,
                colors.HexColor("#F1F5FA"),
            ],
        ),
    ]))

    # Correction : le tableau créé s'appelle "tableau".
    elements.append(tableau)

    document.build(elements)

    tampon.seek(0)

    response = HttpResponse(
        tampon.getvalue(),
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{nom_fichier_export("pdf")}"'
    )

    response["X-Content-Type-Options"] = "nosniff"

    return response