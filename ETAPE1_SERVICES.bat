@echo off
title GSC - Etape 1 : services
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" ( echo .venv introuvable & pause & exit /b 1 )
if not exist "SUIVI_COURRIER.xlsx" ( echo Copiez votre Excel ici sous le nom SUIVI_COURRIER.xlsx & pause & exit /b 1 )
call .venv\Scripts\activate.bat
python patch_suivi_excel.py
if errorlevel 1 goto erreur
python manage.py makemigrations courrier
if errorlevel 1 goto erreur
python manage.py migrate
if errorlevel 1 goto erreur
python etape1_services.py SUIVI_COURRIER.xlsx
if errorlevel 1 goto erreur
echo.
echo Etape 1 terminee. Ouvrez PERSONNEL_A_VERIFIER.xlsx, verifiez les roles, enregistrez, puis lancez ETAPE2_PERSONNEL.bat
pause
exit /b 0
:erreur
echo.
echo Une erreur s'est produite. Copiez le texte ci-dessus pour obtenir de l'aide.
pause
exit /b 1
