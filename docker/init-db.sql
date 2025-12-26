-- Initialize database for Axon MCP Server

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schemas if needed
CREATE SCHEMA IF NOT EXISTS public;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE axon_mcp TO axon;
GRANT ALL ON SCHEMA public TO axon;

-- Set search path
ALTER DATABASE axon_mcp SET search_path TO public;

-- Create initial indexes (migrations will create tables)
-- This file is executed only on first container startup

