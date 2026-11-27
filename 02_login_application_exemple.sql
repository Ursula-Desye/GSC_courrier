-- EXEMPLE À ADAPTER. Choisir un mot de passe fort et le conserver en lieu sûr.
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'gsc_user')
    CREATE LOGIN gsc_user WITH PASSWORD = 'ChangeMoi_MotDePasseFort_2026!';
GO
USE GESTION_COURRIER;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'gsc_user')
    CREATE USER gsc_user FOR LOGIN gsc_user;
GO
ALTER ROLE db_owner ADD MEMBER gsc_user;
GO
-- Pour la production, remplacer db_owner par des permissions minimales après validation.
