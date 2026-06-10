# XAU/USD Bot — Migration & Portability Guide

> **Audience:** Server administrators and bot operators migrating the XAU/USD Price Action Bot between VPS instances, or recovering from a disaster.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Backup Procedure](#3-backup-procedure)
4. [Export Procedure](#4-export-procedure)
5. [Transfer to New VPS](#5-transfer-to-new-vps)
6. [Fresh Install on New VPS](#6-fresh-install-on-new-vps)
7. [Restore Procedure](#7-restore-procedure)
8. [Validation Procedure](#8-validation-procedure)
9. [Rollback Procedure](#9-rollback-procedure)
10. [Docker Migration](#10-docker-migration)
11. [Disaster Recovery](#11-disaster-recovery)
12. [High Availability Recommendations](#12-high-availability-recommendations)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Overview

The migration system consists of four shell scripts that together provide a complete lifecycle:

| Script | Purpose |
|---|---|
| `scripts/backup.sh` | Creates a timestamped compressed snapshot of `data/`, `logs/`, `reports/`, `config.yaml`, `.env` |
| `scripts/export.sh` | Wraps `backup.sh` output into a self-contained migration bundle with restore instructions |
| `scripts/restore.sh` | Extracts a migration bundle and restores all state to a target system |
| `scripts/validate.sh` | Runs a structured PASS/FAIL/WARN health check after install or restore |
| `scripts/install.sh` | Full Ubuntu 24.04 VPS setup: system packages, Wine, Python venv, systemd service, firewall |

All scripts source `.env` automatically, so environment-specific paths and ports are never hardcoded.

---

## 2. Prerequisites

### Source VPS (old server)
- Bot installed and running at `/home/botuser/xau_bot`
- SSH access
- At least 500 MB free disk space for the export bundle

### Destination VPS (new server)
- Ubuntu 24.04 LTS (fresh install recommended)
- Minimum 2 GB RAM, 20 GB SSD
- `sudo` or `root` access
- Domain DNS already pointing to the new VPS IP (for SSL)
- Cloud firewall / security group allowing inbound: **22, 8443, 8502, 6080**

### Local Machine
- `ssh` and `scp` (or `rsync`) installed
- SSH key access to both VPS instances

---

## 3. Backup Procedure

### Scheduled Backups (recommended)

Add a cron job to run daily backups at 03:00 UTC:

```bash
# Edit crontab for botuser
crontab -e

# Add this line:
0 3 * * * /bin/bash /home/botuser/xau_bot/scripts/backup.sh >> /home/botuser/xau_bot/logs/backup_cron.log 2>&1
```

Backups older than `BACKUP_RETENTION_DAYS` (default 30) are automatically deleted.

### Manual Backup

```bash
# Basic — output to default backups/ directory
bash /home/botuser/xau_bot/scripts/backup.sh

# Custom output directory
bash /home/botuser/xau_bot/scripts/backup.sh /mnt/external-storage/xaubot-backups

# Output:
#   backups/xaubot_backup_20250610_030000.tar.gz
#   backups/xaubot_backup_20250610_030000.manifest.json
#   backups/xaubot_backup_20250610_030000.sha256
```

The script prints the full path to the created archive on its last line, which makes it easy to capture in other scripts:

```bash
LATEST_BACKUP="$(bash scripts/backup.sh 2>/dev/null | tail -1)"
echo "Backup at: ${LATEST_BACKUP}"
```

### What is backed up

| Item | Purpose |
|---|---|
| `data/` | SQLite learning DB, account snapshots, open trades JSON |
| `logs/` | Bot logs, API logs, MT5 logs |
| `reports/` | Backtest reports and metrics |
| `config.yaml` | Bot configuration (with env var placeholders) |
| `.env` | Environment-specific values (ports, paths, secrets) |

---

## 4. Export Procedure

The export script creates a single self-contained `.tar.gz` bundle containing the backup plus restore instructions and metadata. Use this when migrating to a new server.

```bash
# Export to the default backups/ directory
bash /home/botuser/xau_bot/scripts/export.sh

# Export to a custom directory
bash /home/botuser/xau_bot/scripts/export.sh /tmp/migration-export

# Output:
#   backups/xaubot_migration_20250610_030000.tar.gz
#   backups/xaubot_migration_20250610_030000.sha256
#
# The script also prints:
#   <sha256hash>  /path/to/xaubot_migration_20250610_030000.tar.gz
```

### Bundle contents

```
xaubot_migration_20250610_030000.tar.gz
├── xaubot_backup_20250610_030000.tar.gz      ← inner backup (data/logs/etc.)
├── xaubot_backup_20250610_030000.manifest.json
├── xaubot_backup_20250610_030000.sha256
├── RESTORE_INSTRUCTIONS.txt                  ← step-by-step guide
└── migration_meta.json                       ← source server info + feature flags
```

---

## 5. Transfer to New VPS

### Option A — SCP (simple)

```bash
# On your local machine:
BUNDLE="xaubot_migration_20250610_030000.tar.gz"
NEW_VPS_IP="1.2.3.4"

scp /home/botuser/xau_bot/backups/${BUNDLE} \
    botuser@${NEW_VPS_IP}:/tmp/

# Copy the .sha256 file too for integrity verification
scp /home/botuser/xau_bot/backups/${BUNDLE%.tar.gz}.sha256 \
    botuser@${NEW_VPS_IP}:/tmp/
```

### Option B — rsync (resumable, better for large bundles)

```bash
rsync -avz --progress \
    /home/botuser/xau_bot/backups/xaubot_migration_*.tar.gz \
    botuser@${NEW_VPS_IP}:/tmp/
```

### Verify transfer integrity

```bash
# On new VPS:
sha256sum /tmp/xaubot_migration_*.tar.gz

# Compare with the .sha256 file:
cat /tmp/xaubot_migration_*.sha256
```

---

## 6. Fresh Install on New VPS

Run `install.sh` on the new VPS. It will:
- Install all system packages (Python 3.12, Wine, Xvfb, noVNC, certbot, UFW)
- Clone the repository
- Set up the Python virtual environment
- Create data directories
- Install and enable the `xaubot` systemd service

```bash
# SSH into new VPS
ssh botuser@${NEW_VPS_IP}

# Option A — combined install + restore (recommended)
# Downloads install.sh from GitHub then immediately restores your data
curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/XAU_Bot/claude/xauusd-price-action-bot-T80IJ/scripts/install.sh \
     -o /tmp/install.sh

sudo bash /tmp/install.sh --restore /tmp/xaubot_migration_*.tar.gz

# Option B — install only (restore separately)
sudo bash /tmp/install.sh
```

### After install — configure environment

```bash
nano /home/botuser/xau_bot/.env
```

Key values to update for the new server:
```
VPS_HOST=<new VPS IP>
SSL_DOMAIN=<your domain>
SSL_CERT_DIR=/etc/letsencrypt/live/<your domain>
```

### Obtain SSL certificate (if not carried over)

```bash
sudo certbot certonly --standalone \
    --agree-tos \
    --non-interactive \
    --email admin@yourdomain.com \
    -d xaubot.yourdomain.com
```

---

## 7. Restore Procedure

### Automated restore from migration bundle

```bash
bash /home/botuser/xau_bot/scripts/restore.sh /tmp/xaubot_migration_*.tar.gz
```

### Dry-run preview (no changes made)

```bash
bash /home/botuser/xau_bot/scripts/restore.sh --dry-run /tmp/xaubot_migration_*.tar.gz
```

The dry-run shows exactly what would be restored without touching any files.

### What the restore script does

1. **Verifies SHA-256** of the bundle (if a `.sha256` file is present)
2. **Creates a safety backup** of the current state (`backups/pre_restore_<timestamp>.tar.gz`)
3. **Extracts** the bundle into a temporary work directory
4. **Detects bundle type** (migration bundle vs direct backup archive)
5. **Restores** `data/`, `logs/`, `reports/`, `config.yaml`, `.env` to `BOT_ROOT`
6. **Runs `validate.sh`** for a post-restore health check

### Restore from a direct backup archive

`restore.sh` also accepts raw backup archives (not just migration bundles):

```bash
bash scripts/restore.sh backups/xaubot_backup_20250610_030000.tar.gz
```

---

## 8. Validation Procedure

Run after any install or restore to confirm the system is healthy:

```bash
bash /home/botuser/xau_bot/scripts/validate.sh
```

### Sample output

```
======================================================================
  XAU/USD Bot — Validation Report
  2025-06-10 10:30:00 UTC
  Host: xaubot-vps2
======================================================================

  STATUS  CHECK                                       DETAIL
  ──────  ──────────────────────────────────────────  ────────────────
  PASS    Python executable                           Python 3.12.3 → /app/.venv/bin/python
  PASS    Python packages                             yaml, pandas, numpy, requests all importable
  PASS    Bot module (xau_bot)                        importable
  PASS    config.yaml                                 Valid YAML, all required keys present
  PASS    Directory: data/                            exists, 3 file(s)
  PASS    Directory: logs/                            exists, 5 file(s)
  PASS    Directory: reports/                         exists, 1 file(s)
  WARN    XAU_Accounts.json (DWX bridge)              Not found — MT5 + XAU_Bridge EA may not be running
  WARN    Bot process                                 Not running (start with: sudo systemctl start xaubot)
  WARN    API endpoint (https://localhost:8443/health) Not reachable (may be starting up)
  WARN    UI endpoint (http://localhost:8502)         Not reachable (may be starting up)
  PASS    Learning DB                                 learning.enabled=false — skipped
  PASS    Log directory writable                      /app/logs
  PASS    Disk space                                  12847 MB free on /dev/sda1

======================================================================
  Results: 8 PASS  |  4 WARN  |  0 FAIL
======================================================================
```

Exit code is `0` if no FAIL items, `1` if any FAIL.

---

## 9. Rollback Procedure

The restore script always creates a safety backup before overwriting data:

```
backups/pre_restore_20250610_103000.tar.gz
```

To roll back to the state before the restore:

```bash
# List available pre-restore backups
ls -lt /home/botuser/xau_bot/backups/pre_restore_*.tar.gz

# Roll back to a specific backup
bash /home/botuser/xau_bot/scripts/restore.sh \
     /home/botuser/xau_bot/backups/pre_restore_20250610_103000.tar.gz

# Restart the bot
sudo systemctl restart xaubot
```

### Emergency rollback (manual)

If `restore.sh` itself is broken, restore manually:

```bash
# Stop the bot
sudo systemctl stop xaubot

# Extract the safety backup
cd /home/botuser/xau_bot
tar -xzf backups/pre_restore_20250610_103000.tar.gz

# Restart
sudo systemctl start xaubot
```

---

## 10. Docker Migration

### Build and run with Docker

```bash
# Copy .env
cp .env.example .env
nano .env

# Build the image
docker build -t xaubot:latest .

# Run with docker compose
docker compose up -d

# Check status
docker compose ps
docker compose logs -f
```

### Docker backup

```bash
# Run backup.sh inside the running container
docker exec xaubot bash /app/scripts/backup.sh

# Copy the backup out of the container
docker cp xaubot:/app/backups/xaubot_backup_latest.tar.gz ./
```

### Docker export for migration

```bash
# Export from inside container
docker exec xaubot bash /app/scripts/export.sh /app/backups

# Copy the bundle out
BUNDLE="$(docker exec xaubot ls /app/backups/xaubot_migration_*.tar.gz | tail -1)"
docker cp "xaubot:${BUNDLE}" ./
```

### Migrate Docker volumes to new host

```bash
# On old host — export data volumes
docker run --rm \
    -v xaubot_data:/data \
    -v $(pwd):/backup \
    alpine tar czf /backup/xaubot_volumes.tar.gz /data

# Transfer to new host
scp xaubot_volumes.tar.gz botuser@${NEW_VPS_IP}:/tmp/

# On new host — import volumes
docker run --rm \
    -v xaubot_data:/data \
    -v /tmp:/backup \
    alpine tar xzf /backup/xaubot_volumes.tar.gz

# Start on new host
docker compose up -d
```

---

## 11. Disaster Recovery

### Scenario: VPS completely lost (no SSH access)

**Objective:** Restore from the most recent backup to a new VPS in under 30 minutes.

**Prerequisites:** Regular backups stored off-VPS (S3, Backblaze B2, or local machine).

#### Step 1 — Provision new VPS

Provision a fresh Ubuntu 24.04 VPS and note its IP address.

#### Step 2 — Transfer backup from off-site storage

```bash
# Example: retrieve from S3
aws s3 cp s3://your-bucket/xaubot-backups/xaubot_migration_latest.tar.gz /tmp/

# Or from local machine
scp xaubot_migration_latest.tar.gz botuser@${NEW_VPS_IP}:/tmp/
```

#### Step 3 — Full install + restore

```bash
ssh botuser@${NEW_VPS_IP}

curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/XAU_Bot/claude/xauusd-price-action-bot-T80IJ/scripts/install.sh \
     -o /tmp/install.sh

sudo bash /tmp/install.sh --restore /tmp/xaubot_migration_latest.tar.gz
```

#### Step 4 — Update DNS

Update your domain's A record to point to the new VPS IP. Propagation typically takes 5–30 minutes.

#### Step 5 — Re-issue SSL certificate

```bash
sudo certbot certonly --standalone -d xaubot.yourdomain.com
```

Update `SSL_CERT_DIR` in `.env` if the path changed.

#### Step 6 — Reinstall MT5 under Wine

```bash
bash /home/botuser/xau_bot/scripts/install_mt4_wine.sh
```

Attach the **XAU_Bridge EA** to the XAUUSD chart in MT5 and log in to your broker account.

#### Step 7 — Validate and start

```bash
bash /home/botuser/xau_bot/scripts/validate.sh
sudo systemctl start xaubot
```

### Off-site backup automation

Add this to cron for automatic S3/B2 sync after local backup:

```bash
# /etc/cron.d/xaubot-backup
# Run at 03:05 UTC daily (5 min after local backup at 03:00)
5 3 * * * botuser \
    LATEST="$(ls -t /home/botuser/xau_bot/backups/xaubot_backup_*.tar.gz 2>/dev/null | head -1)" && \
    [ -n "${LATEST}" ] && \
    aws s3 cp "${LATEST}" s3://your-bucket/xaubot-backups/ --quiet
```

---

## 12. High Availability Recommendations

### Warm standby VPS

Keep a second VPS with the bot installed but in `paper` mode. Point it at the same domain via DNS failover.

```bash
# .env on standby VPS
BOT_MODE=paper
```

On failover:
```bash
# On standby VPS — switch to live mode
sed -i 's/^BOT_MODE=.*/BOT_MODE=live/' .env
sudo systemctl restart xaubot
```

### Automated health monitoring

Use a simple cron check to restart the bot if it crashes:

```bash
# /etc/cron.d/xaubot-watchdog
*/5 * * * * root \
    systemctl is-active --quiet xaubot || \
    systemctl restart xaubot
```

Or use the systemd `Restart=on-failure` + `RestartSec=30` settings already in the service file.

### External uptime monitoring

Use [UptimeRobot](https://uptimerobot.com) or [Freshping](https://freshping.io) to monitor:
- `https://xaubot.yourdomain.com:8443/health` — API
- `http://xaubot.yourdomain.com:8502` — UI

Configure alerts to page you on HTTPS status != 200.

### Database replication

For the learning database (`data/learning.db`), schedule hourly rsync to a backup location:

```bash
# /etc/cron.d/xaubot-db-sync
*/30 * * * * botuser \
    rsync -az /home/botuser/xau_bot/data/learning.db \
    user@backup-host:/backups/xaubot/learning.db
```

---

## 13. Troubleshooting

### Bot fails to start after restore

```bash
# Check service logs
sudo journalctl -u xaubot -n 50

# Run validation
bash /home/botuser/xau_bot/scripts/validate.sh

# Check .env was restored correctly
cat /home/botuser/xau_bot/.env | grep -v "password\|secret\|key"
```

### API returns 502 / not reachable

```bash
# Check if API process is running
pgrep -fa uvicorn

# Check API log
tail -50 /home/botuser/xau_bot/logs/api.log

# Check SSL cert paths
ls -la "${SSL_CERT_DIR}"

# Test without TLS
curl -v http://localhost:${API_PORT}/health
```

### MT5 / DWX bridge not working

```bash
# Check if Xvfb is running
pgrep Xvfb && echo "Xvfb running" || echo "Xvfb not running"

# Check if Wine / MT5 is running
pgrep -f terminal64.exe && echo "MT5 running" || echo "MT5 not running"

# Restart all services manually
bash /home/botuser/xau_bot/scripts/start_all.sh

# Check MT5 log
tail -50 /home/botuser/xau_bot/logs/mt5.log

# Verify DWX bridge files path
ls "${MT5_FILES_PATH}"
```

### config.yaml has wrong values after restore

The `.env` file takes precedence over hardcoded values in `config.yaml` via `${VAR_NAME:-default}` substitution. Check:

```bash
# View resolved config (with env vars substituted)
python3 -c "
import os, re, yaml
with open('/home/botuser/xau_bot/config.yaml') as f:
    raw = f.read()
def subst(m):
    var, _, default = m.group(1).partition(':-')
    return os.environ.get(var, default)
resolved = re.sub(r'\$\{([^}]+)\}', subst, raw)
cfg = yaml.safe_load(resolved)
print(yaml.dump(cfg, default_flow_style=False))
" 
```

### Permissions error on data directory

```bash
# Fix ownership
sudo chown -R botuser:botuser /home/botuser/xau_bot/data
sudo chown -R botuser:botuser /home/botuser/xau_bot/logs
sudo chown -R botuser:botuser /home/botuser/xau_bot/reports
sudo chown -R botuser:botuser /home/botuser/xau_bot/backups

# Fix permissions
find /home/botuser/xau_bot/data -type f -exec chmod 644 {} \;
find /home/botuser/xau_bot/data -type d -exec chmod 755 {} \;
```

### Disk full

```bash
# Check disk usage
df -h /home/botuser/xau_bot

# Find largest files
du -sh /home/botuser/xau_bot/*/ | sort -rh | head -10

# Clean old logs (keep last 7 days)
find /home/botuser/xau_bot/logs -name "*.log" -mtime +7 -delete

# Clean old backups (keep last 7)
ls -t /home/botuser/xau_bot/backups/xaubot_backup_*.tar.gz | tail -n +8 | xargs rm -f

# Run manual backup with retention
BACKUP_RETENTION_DAYS=7 bash /home/botuser/xau_bot/scripts/backup.sh
```

### Restoring specific files only

If you only need to restore a specific file from a backup:

```bash
# List files in a backup archive
tar -tzf backups/xaubot_backup_20250610_030000.tar.gz

# Extract only the learning database
tar -xzf backups/xaubot_backup_20250610_030000.tar.gz \
    -C /home/botuser/xau_bot \
    data/learning.db

# Extract only config.yaml
tar -xzf backups/xaubot_backup_20250610_030000.tar.gz \
    -C /home/botuser/xau_bot \
    config.yaml
```
