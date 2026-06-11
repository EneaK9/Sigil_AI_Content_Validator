-- 0002_validation.sql
-- Add validation columns to the posts table for storing policy compliance results.
-- Safe to run in the Supabase SQL editor or via `supabase db push`.
-- Idempotent guards make re-runs harmless.

-- Validation status enum
do $$
begin
  if not exists (select 1 from pg_type where typname = 'validation_status_t') then
    create type validation_status_t as enum ('pending', 'processing', 'pass', 'fail', 'error');
  end if;
end$$;

-- Add validation columns to posts table
ALTER TABLE posts ADD COLUMN IF NOT EXISTS validation_status validation_status_t DEFAULT 'pending';
ALTER TABLE posts ADD COLUMN IF NOT EXISTS verdict text;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS violations jsonb DEFAULT '[]';
ALTER TABLE posts ADD COLUMN IF NOT EXISTS validation_confidence numeric(4,3);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS validation_recommendation text;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS validated_at timestamptz;

-- Index for efficiently querying pending validations
CREATE INDEX IF NOT EXISTS posts_validation_status_idx 
  ON posts (validation_status) 
  WHERE validation_status = 'pending';

-- Index for efficiently querying failed validations (violations)
CREATE INDEX IF NOT EXISTS posts_verdict_fail_idx 
  ON posts (verdict) 
  WHERE verdict = 'FAIL';

-- Composite index for platform + validation status queries
CREATE INDEX IF NOT EXISTS posts_platform_validation_idx 
  ON posts (platform, validation_status);
