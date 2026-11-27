@echo off
title GSC - Serveur (ne pas fermer cette fenetre)
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Environnement .venv introuvable dans %cd%
    echo Lancez d'abord : python -m venv .venv  puis  pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo GSC demarre... le navigateur va s'ouvrir dans quelques secondes.
echo Pour arreter l'application : fermez cette fenetre ou appuyez sur Ctrl+C.
echo.

start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000/"

python manage.py runserver 0.0.0.0:8000

echo.
echo Le serveur s'est arrete. Si un message d'erreur est affiche ci-dessus, copiez-le.
pause
