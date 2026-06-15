-- 0001_init.sql
-- Sigil social scraper initial schema.
-- Safe to run in the Supabase SQL editor or via `supabase db push`.
-- Idempotent guards (IF NOT EXISTS / DO blocks) make re-runs harmless.

-- Enums --------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'platform_t') then
    create type platform_t as enum ('tiktok','instagram','facebook','linkedin','twitter');
  end if;
  if not exists (select 1 from pg_type where typname = 'run_status_t') then
    create type run_status_t as enum ('requested','running','succeeded','failed','aborted');
  end if;
  if not exists (select 1 from pg_type where typname = 'transcription_t') then
    create type transcription_t as enum ('not_required','pending','processing','done','failed');
  end if;
end$$;

-- Campaigns ----------------------------------------------------------------
create table if not exists scrape_campaigns (
  id           uuid primary key default gen_random_uuid(),
  platform     platform_t not null,
  topic        text not null,
  country      text,
  seeds        jsonb not null default '[]',   -- hashtags/queries/urls per platform
  daily_target int not null default 0,
  enabled      boolean not null default true,
  created_at   timestamptz not null default now()
);

-- Runs ---------------------------------------------------------------------
create table if not exists scrape_runs (
  id               uuid primary key default gen_random_uuid(),
  campaign_id      uuid references scrape_campaigns(id),
  platform         platform_t not null,
  apify_run_id     text,
  apify_dataset_id text,
  status           run_status_t not null default 'requested',
  items_ingested   int not null default 0,
  items_failed     int not null default 0,
  cost_usd         numeric(10,4),
  error            text,
  requested_at     timestamptz not null default now(),
  started_at       timestamptz,
  finished_at      timestamptz
);
create index if not exists scrape_runs_status_idx on scrape_runs (status);

-- Posts --------------------------------------------------------------------
create table if not exists posts (
  id                 uuid primary key default gen_random_uuid(),
  platform           platform_t not null,
  platform_post_id   text not null,
  campaign_id        uuid references scrape_campaigns(id),
  url                text,
  author_handle      text,
  author_id          text,
  author_url         text,
  content_text       text,
  lang               text,
  posted_at          timestamptz,
  like_count         bigint,
  comment_count      bigint,
  share_count        bigint,
  view_count         bigint,
  media_type         text,
  has_video          boolean not null default false,
  video_url          text,
  audio_url          text,
  thumbnail_url      text,
  hashtags           text[] default '{}',
  mentions           text[] default '{}',
  country            text,
  country_confidence numeric(4,3),
  topic              text,
  -- transcription seam (not populated by the scraper beyond pending/not_required):
  transcription_status transcription_t not null default 'not_required',
  transcript         text,
  raw                jsonb not null,
  scraped_at         timestamptz not null default now(),
  constraint posts_platform_post_id_key unique (platform, platform_post_id)  -- dedup key
);
create index if not exists posts_campaign_id_idx on posts (campaign_id);
create index if not exists posts_pending_transcription_idx
  on posts (transcription_status)
  where transcription_status = 'pending';
