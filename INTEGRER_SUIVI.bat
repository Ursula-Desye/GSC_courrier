@echo off
title GSC - Integration du fichier SUIVI_COURRIER
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Environnement .venv introuvable. Lancez d'abord LANCER_GSC.bat une fois.
    pause
    exit /b 1
)
if not exist "SUIVI_COURRIER.xlsx" (
    echo Copiez votre fichier Excel dans ce dossier sous le nom SUIVI_COURRIER.xlsx
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo ETAPE 1/4 - Preparation des modeles
python patch_suivi_excel.py
if errorlevel 1 goto erreur

echo.
echo ETAPE 2/4 - Mise a jour de la base de donnees
python manage.py makemigrations courrier
if errorlevel 1 goto erreur
python manage.py migrate
if errorlevel 1 goto erreur

echo.
echo ETAPE 3/4 - Simulation (rien n'est ecrit)
python import_suivi_excel.py SUIVI_COURRIER.xlsx
if errorlevel 1 goto erreur
start notepad RAPPORT_IMPORT.txt

echo.
echo ETAPE 4/4 - Import reel
echo Lisez RAPPORT_IMPORT.txt. IMPORTANT : faites d'abord une sauvegarde
echo de la base GESTION_COURRIER dans SSMS (clic droit, Taches, Sauvegarder).
echo.
set /p REP=Tapez OUI pour importer les courriers, sinon fermez cette fenetre : 
if /i not "%REP%"=="OUI" goto fin

python import_suivi_excel.py SUIVI_COURRIER.xlsx --appliquer
if errorlevel 1 goto erreur
if exist COMPTES_IMPORT.txt start notepad COMPTES_IMPORT.txt
echo.
echo Termine. Fermez le serveur GSC s'il tourne, puis relancez LANCER_GSC.bat
pause
exit /b 0

:erreur
echo.
echo Une erreur s'est produite. Copiez le texte ci-dessus pour obtenir de l'aide.
pause
exit /b 1

:fin
echo Import annule.
pause
