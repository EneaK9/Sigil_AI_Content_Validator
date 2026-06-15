-- 0004_add_reddit_platform.sql
-- The initial schema (0001) created platform_t without 'reddit', but the
-- application models / campaigns / adapter all use it -> inserts of reddit posts
-- fail. Add the missing enum value.
-- Safe to run in the Supabase SQL editor or via `supabase db push`.
-- Idempotent: ADD VALUE IF NOT EXISTS makes re-runs harmless.

alter type platform_t add value if not exists 'reddit';
