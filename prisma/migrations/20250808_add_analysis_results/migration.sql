-- Add JSON columns for analysis results and settings
ALTER TABLE "analyses"
  ADD COLUMN "settings" JSONB,
  ADD COLUMN "results" JSONB;
