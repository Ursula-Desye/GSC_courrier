@echo off
title GSC - Etape 2 : personnel
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" ( echo .venv introuvable & pause & exit /b 1 )
call .venv\Scripts\activate.bat
echo VERIFICATION (rien n'est ecrit)
python etape2_personnel.py
if errorlevel 1 goto erreur
echo.
set /p REP=Tapez OUI pour creer les comptes, sinon fermez cette fenetre : 
if /i not "%REP%"=="OUI" goto fin
python etape2_personnel.py --appliquer
if errorlevel 1 goto erreur
if exist COMPTES_PERSONNEL.txt start notepad COMPTES_PERSONNEL.txt
pause
exit /b 0
:erreur
echo.
echo Corrigez le fichier PERSONNEL_A_VERIFIER.xlsx ou copiez le texte ci-dessus.
pause
exit /b 1
:fin
echo Annule.
pause
