-- À exécuter dans SSMS avec un compte autorisé.
IF DB_ID(N'GESTION_COURRIER') IS NULL
    CREATE DATABASE GESTION_COURRIER;
GO
-- Créer un login applicatif dédié après validation de la politique de sécurité.
-- Ne pas utiliser le compte sa dans l'application.
