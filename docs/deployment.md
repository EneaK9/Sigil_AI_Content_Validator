# Deployment (containerless / systemd)

Sigil ships as a plain installable Python package. This guide deploys it without
containers: a virtualenv on the host plus two systemd services.

## Components & ports

| Process | Command | Port |
| --- | --- | --- |
| Scheduler (runner + collector + status) | `sigil-scheduler` | `:8002` (status HTTP) |
| Validation API | `uvicorn sigil.scraper.api:app` | `:8001` |
| Migrations (one-shot) | `sigil-migrate` | — |

The scheduler is the steady-state scraper. The validation API is optional and
only needed if you want to trigger validation / read violations over HTTP; the
`sigil` CLI can do the same from the shell.

## 1. Provision the host

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin sigil
sudo mkdir -p /opt/sigil
sudo chown sigil:sigil /opt/sigil
```

## 2. Install

```bash
sudo -u sigil bash -lc '
  cd /opt/sigil
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install /path/to/sigil   # or: pip install . from a checkout
'
```

Place the runtime files next to the venv:

- `/opt/sigil/.env` — secrets and tuning (see `.env.example`; `chmod 600`).
- `/opt/sigil/campaigns.yaml` — campaign definitions.

The policy markdown files ship inside the package, so nothing else is needed.

## 3. Run migrations

```bash
sudo -u sigil bash -lc 'cd /opt/sigil && set -a && . ./.env && set +a && .venv/bin/sigil-migrate'
```

Migrations are idempotent, so re-running after every deploy is safe.

## 4. systemd units

`/etc/systemd/system/sigil-scheduler.service`

```ini
[Unit]
Description=Sigil scraper scheduler (runner + collector + status)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sigil
Group=sigil
WorkingDirectory=/opt/sigil
EnvironmentFile=/opt/sigil/.env
ExecStart=/opt/sigil/.venv/bin/sigil-scheduler
Restart=on-failure
RestartSec=5
# Graceful shutdown: the scheduler handles SIGTERM and drains its loops.
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/sigil-api.service`

```ini
[Unit]
Description=Sigil validation API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sigil
Group=sigil
WorkingDirectory=/opt/sigil
EnvironmentFile=/opt/sigil/.env
ExecStart=/opt/sigil/.venv/bin/uvicorn sigil.scraper.api:app --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sigil-scheduler.service
sudo systemctl enable --now sigil-api.service     # optional
```

## 5. Verify

```bash
curl -s localhost:8002/healthz      # {"status":"ok"}
curl -s localhost:8002/status | jq  # live runs, items fetched, totals, spend
curl -s localhost:8001/health       # {"status":"ok"}  (if API enabled)
```

Logs are structured JSON on stdout, captured by journald:

```bash
journalctl -u sigil-scheduler -f
```

## Run order summary

1. `pip install .`
2. write `/opt/sigil/.env` and `/opt/sigil/campaigns.yaml`
3. `sigil-migrate`
4. start `sigil-scheduler` (and optionally `sigil-api`)

## Upgrades

```bash
sudo -u sigil /opt/sigil/.venv/bin/pip install --upgrade /path/to/sigil
sudo -u sigil bash -lc 'cd /opt/sigil && set -a && . ./.env && set +a && .venv/bin/sigil-migrate'
sudo systemctl restart sigil-scheduler sigil-api
```

## Operational notes

- **Budget guard**: the scheduler enforces `DAILY_BUDGET_USD` using
  `EST_COST_PER_RUN_USD`. `sigil scrape` bypasses this guard and is a manual tool.
- **Concurrency**: validation runs bounded-concurrent (`asyncio.Semaphore`), with
  the synchronous LLM calls offloaded to a thread pool so the event loop and DB
  work are never blocked.
- **Pooler compatibility**: use the Supabase *session pooler* URL. The engine and
  migration runner disable asyncpg prepared-statement caching for pgbouncer.
