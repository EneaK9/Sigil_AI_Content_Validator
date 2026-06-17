-- 0003_add_campaign_client.sql
-- Add `client` column to campaigns for multi-client support.
-- Idempotent so it can be re-run safely.

alter table scrape_campaigns
  add column if not exists client text not null default 'sigil';

create index if not exists scrape_campaigns_client_platform_idx
  on scrape_campaigns (client, platform);

