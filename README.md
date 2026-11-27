# GSC – Gestion et Suivi du Courrier

Starter local Django + Microsoft SQL Server.

## Prérequis Windows
- Python 3.12 64 bits recommandé
- SQL Server Developer ou Express (moteur local)
- SQL Server Management Studio (SSMS)
- Microsoft ODBC Driver 18 for SQL Server (64 bits)
- Visual Studio Code (facultatif)

## Installation
1. Décompresser le dossier.
2. Ouvrir PowerShell dans le dossier GSC.
3. Créer l'environnement :
   `py -3.12 -m venv .venv`
4. Activer :
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
   `\.venv\Scripts\Activate.ps1`
5. Installer :
   `python -m pip install --upgrade pip`
   `pip install -r requirements.txt`
6. Copier `.env.example` vers `.env` :
   `Copy-Item .env.example .env`
   Modifier `.env` avec le nom d'instance, le compte SQL et le mot de passe. Django charge automatiquement ce fichier.
7. Dans SSMS, exécuter `scripts_sql/01_creation_base.sql`, puis adapter et exécuter `02_login_application_exemple.sql`.
8. Vérifier le nom du serveur/instance SQL et le pilote ODBC.
9. Générer les tables Django :
   `python manage.py makemigrations courrier`
   `python manage.py migrate`
10. Créer l'administrateur :
   `python manage.py createsuperuser`
11. Lancer :
   `python manage.py runserver`
12. Ouvrir `http://127.0.0.1:8000/`.

## Important
- L'exemple SQL donne temporairement db_owner au compte applicatif pour faciliter le prototype local. Ne pas reprendre ce droit en production.
- Ne pas exposer le serveur de développement Django sur le réseau de production.
- Les pièces jointes sont stockées dans `media/`; prévoir contrôle d'accès, antivirus, sauvegarde et limites de taille avant production.
- La numérotation fournie est un prototype mono-utilisateur. Avant usage concurrent, remplacer par un mécanisme transactionnel de séquence SQL afin d'éviter les doublons.
- Les droits fins par service, les validations métier, les exports et les alertes seront renforcés dans les prochaines phases.
