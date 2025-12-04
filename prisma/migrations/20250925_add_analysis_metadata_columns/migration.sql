-- Add metadata columns to analyses table if they are missing
ALTER TABLE "analyses"
    ADD COLUMN IF NOT EXISTS "merchant" TEXT,
    ADD COLUMN IF NOT EXISTS "title" TEXT,
    ADD COLUMN IF NOT EXISTS "tags" JSONB,
    ADD COLUMN IF NOT EXISTS "notes" TEXT;
