-- Bootstrap the GAAIA database with two separate schemas.
--
-- auth  — user accounts and OAuth identities (authentication layer)
-- data  — all user-generated content: sessions, messages, facts, etc.
--
-- SQLAlchemy's create_all() creates the actual tables on first backend start.
-- This file only needs to ensure the schemas exist before that happens.

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS data;
