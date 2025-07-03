
-- Initialize database with required extensions and settings
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create database if it doesn't exist (for local development)
-- Note: This won't work in managed databases, they create the DB for you

-- Set timezone
SET timezone = 'UTC';

-- Create any additional database-level configurations here
-- This file is executed when the PostgreSQL container starts
