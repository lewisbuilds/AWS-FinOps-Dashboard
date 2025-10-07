# Configuration Guide

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AWS_REGION` | `us-east-1` | Primary AWS region |
| `AWS_ROLE_ARN` | - | IAM role to assume (optional) |
| `SINGLE_ACCOUNT_MODE` | `false` | Skip Organizations API calls |
| `REQUIRED_TAG_KEYS` | `Environment,Owner,Project,CostCenter` | Required tags for compliance |
| `REPORT_OUTPUT_DIR` | `reports` | Export directory |
| `REPORT_DEFAULT_FORMATS` | `csv,json,xlsx` | Export formats |
| `MAX_EXCEL_ROWS` | `1000000` | Excel row limit |
| `SES_ENABLED` | `false` | Enable email reports |
| `SES_SENDER_EMAIL` | - | Verified SES sender |
| `SES_RECIPIENT_EMAILS` | - | Comma-separated recipients |
| `SUPPORT_PROBE_ENABLED` | `false` | Check Support API permissions |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Scheduling & Automation

### Background Reports
```bash
REPORT_SCHEDULE_ENABLED=true
REPORT_SCHEDULE_CRON=0 2 * * *  # Daily at 2 AM UTC
REPORT_SCHEDULE_TIMEZONE=UTC
```

### Email Configuration
1. Verify sender in AWS SES
2. If in sandbox, verify recipients too
3. Set appropriate SES region

```bash
SES_ENABLED=true
SES_REGION=us-east-1
SES_SENDER_EMAIL=finops@yourcompany.com
SES_RECIPIENT_EMAILS=team@yourcompany.com,manager@yourcompany.com
```

## Advanced Settings

See `app/config.py` for additional configuration options:
- Anomaly detection thresholds
- Cache TTLs
- Rate limiting
- Cost thresholds for alerts

## Single Account vs Multi-Account

**Single Account Mode** (`SINGLE_ACCOUNT_MODE=true`):
- Reduces IAM permissions needed
- Skips Organizations API calls
- Only analyzes current account

**Multi-Account Mode** (`SINGLE_ACCOUNT_MODE=false`):
- Requires Organizations permissions
- Aggregates across all accounts
- Shows cross-account cost breakdowns