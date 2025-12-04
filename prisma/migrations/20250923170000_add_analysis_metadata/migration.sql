-- Add merchant/title/tags/notes metadata columns to analyses table
ALTER TABLE "analyses"
    ADD COLUMN "merchant" TEXT,
    ADD COLUMN "title" TEXT,
    ADD COLUMN "tags" JSONB,
    ADD COLUMN "notes" TEXT;
