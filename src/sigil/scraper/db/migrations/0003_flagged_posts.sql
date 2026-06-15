-- 0003_flagged_posts.sql
-- Dedicated table for posts that were judged CLEAR_VIOLATION.
-- Stores report-ready, flattened cells (NOT the raw verdict object) so the
-- separate dashboard module can read/review rows straight from the database.
-- Safe to run in the Supabase SQL editor or via `supabase db push`.
-- Idempotent guards (IF NOT EXISTS) make re-runs harmless.

create table if not exists flagged_posts (
  id                       uuid primary key default gen_random_uuid(),
  post_id                  uuid references posts(id),
  platform                 platform_t not null,
  -- Single primary label for the violation (e.g. "Antisemitism").
  category                 text,
  -- Flattened warning detail (joined with "; ").
  warnings_count           int not null default 0,
  warning_categories       text,
  warning_affected_groups  text,
  -- Post metadata (mirrors the source post row at flag time).
  platform_post_id         text,
  url                      text,
  author                   text,
  content_text             text,
  posted_at                timestamptz,
  like_count               bigint,
  comment_count            bigint,
  view_count               bigint,
  hashtags                 text,
  -- Flattened violation detail (joined with "; ").
  violation_quotes         text,
  violation_policy_refs    text,
  -- Enhanced second-pass LLM output.
  tos_cross_reference      text,
  violation_explanation    text,
  report_text              text,
  -- Review workflow.
  added_at                 timestamptz not null default now(),
  is_reviewed              boolean not null default false,
  -- One flagged row per source post (idempotent re-validation).
  constraint flagged_posts_post_id_key unique (post_id)
);

-- Dashboard fetches unreviewed rows newest-first.
create index if not exists flagged_posts_unreviewed_idx
  on flagged_posts (added_at desc)
  where is_reviewed = false;

create index if not exists flagged_posts_platform_idx on flagged_posts (platform);
