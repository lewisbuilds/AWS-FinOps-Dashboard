## AWS FinOps Dashboard (Concise Overview)

Real‑time AWS cost visibility, tag compliance metrics, anomaly detection, multi‑account aggregation, and scheduled reporting (CSV / JSON / Excel + optional SES email) via Streamlit.

### Key Capabilities
Cost & usage breakdown • Multi‑account (Organizations or single account mode) • Tag compliance analysis • Cost anomaly detection (Cost Explorer + advanced models) • Export & scheduled reporting • Least‑privilege IAM patterns • Optional SES email dispatch.

---
### Quick Start
```bash
poetry install
cp .env.example .env  # edit for region / (optional) AWS_ROLE_ARN
poetry run streamlit run app/streamlit_app.py
```
Open http://localhost:8501

Docker:
```bash
docker build -t finops .
docker run --env-file .env -p 8501:8501 finops
```

---
### Minimal IAM (Central Role Example)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid":"CostExplorer","Effect":"Allow","Action":[
      "ce:GetCostAndUsage",
      "ce:GetAnomalies",
      "ce:GetReservationPurchaseRecommendation",
      "ce:GetSavingsPlansPurchaseRecommendation"
    ],"Resource":"*"},
    {"Sid":"OrganizationsOptional","Effect":"Allow","Action":[
      "organizations:DescribeOrganization","organizations:ListAccounts"
    ],"Resource":"*"},
    {"Sid":"ResourceGroups","Effect":"Allow","Action":["resource-groups:ListGroups","resource-groups:SearchResources"],"Resource":"*"},
    {"Sid":"AssumeMember","Effect":"Allow","Action":["sts:AssumeRole","sts:GetCallerIdentity"],"Resource":"arn:aws:iam::*:role/FinOpsMemberReadOnly"}
  ]
}
```
Member role (each account): allow only `ce:GetCostAndUsage`.

Set `SINGLE_ACCOUNT_MODE=true` to omit Organizations permissions entirely.

See `iam/central-role-policy.json` & `iam/member-role-policy.json` for full least‑privilege policies.

---
### Core Environment Variables
| Var | Default | Purpose |
|-----|---------|---------|
| `AWS_REGION` | `us-east-1` | Primary region |
| `AWS_ROLE_ARN` | – | Central / cross-account role (optional) |
| `SINGLE_ACCOUNT_MODE` | `false` | Skip Organizations enumeration (reduces IAM surface) |
| `REQUIRED_TAG_KEYS` | `Environment,Owner,Project,CostCenter` | Compliance tag keys |
| `REPORT_OUTPUT_DIR` | `reports` | Export directory (path traversal guarded) |
| `REPORT_DEFAULT_FORMATS` | `csv,json,xlsx` | Default export formats |
| `MAX_EXCEL_ROWS` | `1000000` | Excel sheet safety cap (extra rows truncated) |
| `SES_ENABLED` | `false` | Enable SES email send |
| `SES_SENDER_EMAIL` | – | Verified SES sender |
| `SES_RECIPIENT_EMAILS` | – | Comma list recipients |
| `SUPPORT_PROBE_ENABLED` | `false` | Probe Support API (permission optional) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `REPORT_SCHEDULE_ENABLED` | `false` | Enable background scheduler |
| `REPORT_SCHEDULE_CRON` | `0 2 * * *` | Cron (UTC) |
| `REPORT_SCHEDULE_TIMEZONE` | `UTC` | Scheduler timezone |

Additional tunables (see `app/config.py`): anomaly thresholds, cache TTLs, rate limiting, etc.

---
### Programmatic Report Generation
```python
from app.export import generate_report
from app.finops import FinOpsAnalyzer

res = generate_report(FinOpsAnalyzer(), formats=["csv","json"], last_n_days=7, email=False)
print(res["files"])  # written export paths
```

Enable scheduler: set `REPORT_SCHEDULE_ENABLED=true` and call `init_scheduler()` (see `app/scheduler.py`).

---
### Security / Hardening Highlights
- Single‑account mode to reduce IAM footprint
- Optional Support API probe disabled by default (`SUPPORT_PROBE_ENABLED`)
- JSON/CSV/XLSX export sanitization (neutralizes leading formula characters)
- Path traversal safeguards on report output directory
- Randomized report filenames & Excel row truncation summary sheet
- CI dependency scan with `pip-audit` (`.github/workflows/security-audit.yml`)

---
### Troubleshooting (Credentials)
| Issue | Likely Cause | Fix |
|-------|--------------|-----|
| AssumeRole pre-flight failed | No base creds for provided role | Set `AWS_PROFILE` & login (SSO) or remove role |
| AccessDenied Cost Explorer | Missing CE actions | Attach policy containing `ce:GetCostAndUsage` etc. |
| Organizations calls failing | In single account only | Set `SINGLE_ACCOUNT_MODE=true` |
| SES send fails | Unverified sender / sandbox | Verify identities, set `SES_REGION` |

Health tab (UI) shows `auth_strategy`, role, and remediation guidance.

---
### Testing & Dev
```bash
poetry run pytest
make lint
make format
```

---
### Changelog Snippets (Security Additions)
- Added least‑privilege policy files under `iam/`
- Added `SINGLE_ACCOUNT_MODE` & `SUPPORT_PROBE_ENABLED` toggles
- Added recursive JSON export sanitization
- Added security audit workflow (pip-audit) failing on critical CVEs

---
### License
MIT – see `LICENSE`.

---
Accessibility considered; please still validate with manual tooling (headings order, keyboard navigation, contrast).






## ✨ Core Features
| Category | Capabilities |
|----------|-------------|
| Cost Analytics | Real‑time spend, service & account breakdowns, trends, daily/monthly totals |
| Tag Compliance | Required tag enforcement, per‑service compliance, missing tag drilldown, score & alerts |
| Anomaly Detection | Cost anomaly discovery, root cause context, impact indicators (baseline models) |
| Optimization | (Pluggable) recommendations: RI / Savings Plan / right‑sizing (extensible interface) |
| Reporting & Export | CSV / JSON / Excel generation, scheduled jobs (cron), SES email delivery |
| Automation | GitHub Actions daily job (OIDC), artifact upload, optional Lambda/EventBridge path |
| UI | Streamlit dashboard (Plotly charts + data tables) |
| Security | OIDC role assumption, least privilege IAM, no static creds in CI |

---

## � Project Structure
```
AWS-FinOps-Dashboard/
├── app/
│   ├── __init__.py
│   ├── aws_session.py        # Session + role assumption helper
│   ├── finops.py             # Core cost + tagging logic
│   └── streamlit_app.py      # Streamlit UI
├── .github/workflows/daily.yml  # Daily CI reporting
├── tests/                    # Test suite
├── Dockerfile
├── Makefile
├── pyproject.toml            # Poetry config
├── requirements.txt          # Runtime deps (Docker/simple env)
├── .env.example              # Environment template
└── README.md
```

---

## ⚙️ Requirements
| Tool / Service | Needed For | Notes |
|----------------|-----------|-------|
| Python 3.11+ | Runtime | Use Poetry for local dev |
| AWS Account + Cost Explorer Enabled | Cost & anomaly APIs | Activation may take 24h initially |
| IAM Role (OIDC) | CI GitHub Action | Minimal read permissions (Cost Explorer, Tagging, STS) |
| SES (optional) | Email reports | Verify sender & (sandbox) recipients |

---

## 🔐 Minimal IAM Policy (Read Only Core)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": [
        "ce:GetCostAndUsage",
        "ce:GetAnomalies",
        "ce:GetSavingsPlansRecommendation",
        "ce:GetReservationPurchaseRecommendation"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["tag:GetResources"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["sts:AssumeRole"], "Resource": "*" }
  ]
}
```

---

## 🧪 Quick Start (Local)
```bash
poetry install
cp .env.example .env   # fill AWS region + (optionally) ASSUME_ROLE_ARN
poetry run streamlit run app/streamlit_app.py
```
Open http://localhost:8501

### Using Docker
```bash
docker build -t aws-finops-dashboard .
docker run --env-file .env -p 8501:8501 aws-finops-dashboard
```

### Make Targets (Convenience)
| Command | Purpose |
|---------|---------|
| `make install-dev` | Install dev dependencies |
| `make run` | Run Streamlit app (prod flags) |
| `make run-dev` | Run with reload / dev settings |
| `make test` | Run test suite |
| `make ci-test` | Full CI test (lint + tests) |
| `make format` | Apply formatting (Black, etc.) |
| `make lint` | Static analysis |
| `make security-scan` | Basic dependency / security scan |

---

## 🌐 Environment Variables
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Yes | `us-east-1` | Primary region for Cost Explorer |
| `ASSUME_ROLE_ARN` | Optional | - | Role to assume (OIDC / cross‑account) |
| `LOOKBACK_DAYS` | Optional | `30` | Default trailing days used for quick time‑series lookbacks (UI / CLI convenience) |
| `REQUIRED_TAG_KEYS` | Optional | `cost_center,env` | Comma list for compliance check |
| `REPORT_OUTPUT_DIR` | Optional | `reports` | Directory for generated reports |
| `REPORT_DEFAULT_FORMATS` | Optional | `csv,json,xlsx` | Default export formats |
| `REPORT_SCHEDULE_ENABLED` | Optional | `false` | Enable background scheduler |
| `REPORT_SCHEDULE_CRON` | Optional | `0 2 * * *` | Cron (UTC unless TZ specified) |
| `REPORT_SCHEDULE_TIMEZONE` | Optional | `UTC` | IANA timezone for scheduling |
| `SES_ENABLED` | Optional | `false` | Enable SES email sending |
| `SES_REGION` | Cond. | `us-east-1` | Region for SES if enabled |
| `SES_SENDER_EMAIL` | Cond. | - | Verified SES sender |
| `SES_RECIPIENT_EMAILS` | Cond. | - | Comma list of recipients |
| `MAX_EXCEL_ROWS` | Optional | `1000000` | Safety cap for Excel writer |
| `LOG_LEVEL` | Optional | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `LOG_FORMAT` | Optional | `text` | Log output format: text or json |

---

## 📊 Streamlit Dashboard Pages
| Page | Highlights |
|------|-----------|
| Overview | Key metrics, service breakdown pie, daily trend line, alerts |
| Cost Analysis | Service / account breakdown tables + charts |
| Tag Compliance | Compliance rate, missing tag histogram, per‑service compliance |
| Anomalies | Detected anomalies (score, date range, causes) |
| Recommendations | Placeholder extensible panel (future enhanced logic) |
| Reports | Multi-format export + email trigger |
| Health | Credential strategy & remediation diagnostics |

---

## 🤖 Automated Reporting & Scheduling
Multi‑format report generation (CSV / JSON / Excel) with optional cron scheduling (APScheduler) and SES delivery.

### Example Programmatic Use
```python
from app.export import generate_report
from app.finops import FinOpsAnalyzer

analyzer = FinOpsAnalyzer()
res = generate_report(analyzer, formats=["csv","json"], last_n_days=7, email=True)
print(res["files"])  # list of written paths
```

### Enabling the Scheduler
```python
from app.scheduler import init_scheduler
init_scheduler()  # starts job if REPORT_SCHEDULE_ENABLED=true
```

### Email Delivery
When `email=True` & SES variables configured (`SES_ENABLED=true` + verified sender), attachments are added until size guard (<10 MB raw MIME). Failures log warnings but do not block file generation.

### Tested Scenarios
| Area | Coverage |
|------|----------|
| Scheduling | Idempotent init, disabled mode |
| Export | Date presets, rolling windows, invalid input guards |
| Email | Disabled path, incomplete config, success (mock SES) |
| Excel | Row cap safety |

### Backlog (Reporting / Export)
* S3 archival / object lifecycle
* Parquet / PDF writers
* Compression for large bundles
* Signed URL email distribution

---

## 🔐 Authentication & Credentials
The dashboard relies on the standard AWS credential provider chain. When `AWS_ROLE_ARN` is set, the code must first obtain base credentials (SSO/profile, static keys, or an instance/container role) to perform `sts:AssumeRole`. If none are present you will see a pre‑flight error:

```
AssumeRole pre-flight failed: no base credentials
AWS initialization failed: No base credentials available to assume role
```

### Recommended (Profile First Approach)
You can supply credentials via any named profile (which itself may be SSO‑backed). Set `AWS_PROFILE` and (optionally) `AWS_ROLE_ARN` if you need cross‑account read access.

```powershell
$env:AWS_PROFILE = "finops"      # profile already configured via 'aws configure sso' or static creds
# Optional role assumption
$env:AWS_ROLE_ARN = "arn:aws:iam::123456789012:role/FinOpsDashboardReadOnly"
```

If the profile already grants Cost Explorer & Tagging permissions, omit `AWS_ROLE_ARN`.

### AWS SSO (Creating the Profile)
```powershell
aws configure sso
aws sso login --profile finops-sso
$env:AWS_PROFILE = "finops-sso"   # (Or add to your shell profile)
```
Then keep `AWS_ROLE_ARN` in `.env` if you need cross‑account access.

### Using a Static Shared Credentials Profile (Non‑SSO)
Define a profile in `~/.aws/credentials` then set `AWS_PROFILE`.

### Static Keys (Development Only)
Uncomment and populate in `.env`:
```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=... (never commit real keys)
```
Remove them before committing or use environment variables injected securely.

### Instance / Container Role
When running on EC2, ECS, or Lambda ensure the execution role has STS `AssumeRole` permission for the target `AWS_ROLE_ARN`.

### Disabling Role Assumption
If you do not need cross‑account data, unset `AWS_ROLE_ARN` and rely on the base credentials alone.

### Quick Verification
```powershell
aws sts get-caller-identity
```
If assuming a role:
```powershell
aws sts assume-role --role-arn $env:AWS_ROLE_ARN --role-session-name finops-test
```

### In‑App Diagnostics (Health Tab)
The **Health** page in the Streamlit sidebar surfaces real‑time credential state:

| Field | Meaning |
|-------|---------|
| `auth_strategy` | `assume_role`, `static_keys`, `default_chain`, or `none` |
| `role_arn` | Target role if set |
| `base_chain_has_credentials` | Provider chain resolved any credentials (profile/SSO/instance) |
| `has_static_keys` | Static keys present via env vars / settings |
| `remediation` | Actionable steps if strategy is unusable |

Programmatic access still available:
```python
from app.aws_session import AWSSessionManager
print(AWSSessionManager().diagnose_credentials())
```

#### Troubleshooting Matrix
| Symptom | Likely Cause | Remediation |
|---------|--------------|-------------|
| Pre-flight error: no base credentials | `AWS_ROLE_ARN` set but no profile / keys / instance role | Run `aws sso login` & set `AWS_PROFILE`, or add static keys (dev), or unset `AWS_ROLE_ARN` |
| `auth_strategy = none` | No creds & no role | Provide profile (`$env:AWS_PROFILE=...`) or static keys |
| AccessDenied on Cost Explorer | Missing `ce:GetCostAndUsage` | Attach `ce:*` read policy to base principal or assumed role |
| Support permission false | Basic support plan / unsupported API | Ignorable unless using Support data |
| Emails not sent | SES not verified / region mismatch | Verify sender & recipients (sandbox) and align `SES_REGION` |

#### Credential Flow Summary
1. Resolve base credentials (SSO/profile/keys/instance).
2. (Optional) Assume role if `AWS_ROLE_ARN` present.
3. Session validated via STS `GetCallerIdentity`.
4. Health tab displays status & remediation.

### Minimum IAM For Base Principal
The principal supplying base credentials must have `sts:AssumeRole` on the target role plus any read permissions needed if you skip role assumption.

---

## 🧱 Architecture (Conceptual)
Frontend (Streamlit) → FinOps Analyzer (cost + tag logic) → AWS APIs (Cost Explorer, Tagging, STS, Organizations optional). Optional background scheduler & SES email peripheral.

---

## 🔐 Security Notes
* **OIDC (GitHub Actions)** for ephemeral credentials
* **Least privilege** IAM role
* **No secrets committed** (`.env.example` only)
* **HTTPS** enforced by AWS SDK

---

## 🛠 Development Workflow
```bash
git checkout -b feature/my-change
# implement + add tests
git commit -m "feat: add X"
make ci-test
```
Open PR with description + test evidence.

### Testing
```bash
poetry run pytest
poetry run pytest --cov=app --cov-report=html
poetry run pytest tests/test_finops.py -v
```

---

## 📈 Observability (Planned / Partial)
| Aspect | Current | Planned |
|--------|---------|---------|
| Logging | Basic structured logs | Correlated request IDs |
| Metrics | Derived in-app | Push to CloudWatch / Prometheus bridge |
| Alerts | Threshold placeholders | Automated anomaly → issue / Slack |

---

## 🚀 Deployment Options
| Option | Command Summary |
|--------|-----------------|
| Local Dev | `poetry run streamlit run app/streamlit_app.py` |
| Docker | `docker build -t aws-finops-dashboard .` then `docker run --env-file .env -p 8501:8501 aws-finops-dashboard` |
| GitHub Action (daily) | See `.github/workflows/daily.yml` |
| (Optional) Lambda + EventBridge | Wrap `run_daily_job()` in handler (future) |

---

## 🤝 Contributing
1. Fork & branch
2. Implement + tests (>90% new code where practical)
3. Update docs if user-facing change
4. Run `make ci-test`
5. Open PR

Coding style: PEP 8 + type hints + self‑explanatory naming. Favor small, focused functions. Avoid premature optimization.

---

## 📄 License
MIT © Contributors – see [LICENSE](LICENSE)

---

## 🆘 Support & Community
| Channel | Purpose |
|---------|---------|
| Issues | Bugs / feature requests |
| Discussions | Design / Q&A |
| Slack (#finops-dashboard) | Real‑time collaboration (if enabled) |

When filing issues include: environment details, repro steps, expected vs actual, relevant logs.

---

## 🎯 Roadmap (Excerpt)
| Quarter | Focus Areas |
|---------|-------------|
| Q1 2024 | Multi-cloud, forecasting, custom dashboard builder, API rate limiting |
| Q2 2024 | ML anomaly detection, Jira/ServiceNow integrations, responsive UX, real‑time streaming |
| Q3 2024 | Multi-tenant, RBAC & SSO, custom alert rules, CI/CD integration |
| Q4 2024 | AI optimization recommender, advanced viz, BI export, security enhancements |

---

**Built with accessibility in mind** – please still run manual checks (headings order, contrast, keyboard navigation). Accessibility improvements welcome.







A comprehensive **AWS Financial Operations (FinOps) Dashboard** that provides real-time cost monitoring, tag compliance tracking, anomaly detection, and optimization recommendations. Built with Python, Streamlit, and AWS APIs for enterprise-grade financial operations management.aws-finops-dashboard — Build Instructions (for Copilot)



1) Repo layout:



## ✨ Features```bash



aws-finops-dashboard/



### 📊 **Cost Analytics**├─ app/



- **Real-time Cost Monitoring**: Track daily, weekly, and monthly AWS spending│  ├─ streamlit_app.py



- **Service Breakdown**: Detailed cost analysis by AWS service and account│  ├─ finops.py



- **Trend Analysis**: Historical cost trends with comparative analytics│  ├─ aws_session.py



- **Budget Tracking**: Monitor spending against predefined budgets│  └─ __init__.py



├─ output/                   # generated at runtime (gitignored)



### 🏷️ **Tag Compliance**├─ .env.example



- **Automated Compliance Monitoring**: Track tag compliance across all AWS resources├─ requirements.txt



- **Required Tag Enforcement**: Configurable required tags (Environment, Owner, Project, CostCenter)├─ Dockerfile



- **Service-Level Compliance**: Detailed compliance metrics by AWS service├─ README.md



- **Compliance Scoring**: Organization-wide tag compliance percentage├─ Makefile



└── .github/



### 🔍 **Anomaly Detection**   └─ workflows/



- **AI-Powered Anomaly Detection**: Automatic detection of unusual spending patterns      └─ daily.yml



- **Root Cause Analysis**: Detailed investigation of cost anomalies```



- **Alert Scoring**: Prioritized anomalies based on impact and confidence



- **Historical Anomaly Tracking**: Trend analysis of anomalous spending2) Minimal dependencies







### 💡 **Cost Optimization**`requirements.txt`



- **Reserved Instance Recommendations**: EC2 RI purchase recommendations```ini



- **Savings Plans Suggestions**: Compute Savings Plans opportunitiesboto3==1.35.0



- **Resource Right-sizing**: Identify over-provisioned resourcespandas==2.2.2



- **Cost Optimization Reports**: Actionable recommendations with estimated savingsstreamlit==1.37.0



plotly==5.23.0



### 🤖 **Automated Reporting**python-dotenv==1.0.1



- **Daily Reports**: Automated daily FinOps reports via GitHub Actions```



- **OIDC Authentication**: Secure AWS access using OpenID Connect



- **Slack/Teams Integration**: Automated notifications for alerts and reports3) Environment variables (no local AWS installs required)



- **GitHub Issues**: Automatic issue creation for critical alerts`.env.example`







## 🏗️ Architecture- keep creds inside Docker or GitHub Actions secrets



- Point your project at the profile (.env)



```mermaid```ini



graph TBAWS_REGION=us-west-2



    subgraph "Frontend"# Use one of the following auth methods:



        ST[Streamlit Dashboard]



        UI[Interactive UI Components]# (A) Direct creds (for local/dev only)



    end# AWS_ACCESS_KEY_ID=...



    # AWS_SECRET_ACCESS_KEY=...



    subgraph "Backend Services"



        FA[FinOps Analyzer]# (B) Assume role (recommended in CI): the GitHub Action will use OIDC + this role



        AS[AWS Session Manager]ASSUME_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/FinOpsDashboardReadOnly



        RM[Report Manager]



    end# Optional: CE lookback days & tag keys to enforce



    LOOKBACK_DAYS=30



    subgraph "AWS Services"REQUIRED_TAG_KEYS=cost_center,env



        CE[Cost Explorer API]```



        ORG[Organizations API]



        RG[Resource Groups API]When running in GitHub Actions, set AWS_REGION and (usually) just the role to assume via OIDC. No long-lived secrets needed.



        SP[Support API]



    end4) Session helper (supports local creds or role assumption)



    



    subgraph "Automation"`app/aws_session.py`



        GHA[GitHub Actions]```python



        OA[OIDC Authentication]import os



        NF[Notifications]import boto3



    endfrom botocore.config import Config



    



    ST --> FAdef _assume_role_session(role_arn: str, region: str):



    UI --> AS    sts = boto3.client("sts", region_name=region, config=Config(retries={"max_attempts": 5}))



    FA --> CE    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName="aws-finops-dashboard")



    FA --> ORG    creds = resp["Credentials"]



    FA --> RG    return boto3.Session(



    AS --> SP        aws_access_key_id=creds["AccessKeyId"],



    GHA --> AS        aws_secret_access_key=creds["SecretAccessKey"],



    GHA --> NF        aws_session_token=creds["SessionToken"],



    OA --> GHA        region_name=region,



```    )







## 🚀 Quick Startdef get_boto3_session():



    region = os.getenv("AWS_REGION", "us-east-1")



### Prerequisites    role_arn = os.getenv("ASSUME_ROLE_ARN")



    if role_arn:



- Python 3.11+        return _assume_role_session(role_arn, region)



- Poetry (for dependency management)    # fall back to default provider chain (env vars, shared config, SSO, etc.)



- AWS CLI configured with appropriate permissions    return boto3.Session(region_name=region)



- Docker (optional, for containerized deployment)```







### 1. Clone and Setup5) Core FinOps logic (Cost Explorer + Tagging compliance)







```bash`app/finops.py`



git clone <your-repo-url>



cd AWS-FinOps-Dashboard```python



import os



# Copy environment templateimport datetime as dt



cp .env.example .envfrom typing import List, Tuple



import pandas as pd



# Edit .env with your AWS configurationfrom .aws_session import get_boto3_session



# AWS_DEFAULT_REGION=us-east-1



# AWS_ROLE_ARN=arn:aws:iam::ACCOUNT:role/FinOpsRoledef _date_range_days(days: int) -> Tuple[str, str]:



```    end = dt.date.today()



    start = end - dt.timedelta(days=days)



### 2. Install Dependencies



Your AWS role/user needs the following permissions:    return start.isoformat(), end.isoformat()







```bashdef fetch_top5_services_spend(lookback_days: int = 30) -> pd.DataFrame:



# Install Poetry if not already installed    session = get_boto3_session()



ce = session.client("ce")



    start, end = _date_range_days(lookback_days)



# Install project dependencies



make install-dev    resp = ce.get_cost_and_usage(



        TimePeriod={"Start": start, "End": end},



# Or using Poetry directly        Granularity="DAILY",



poetry install        Metrics=["UnblendedCost"],



```        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],



    )



### 3. Configure AWS Permissions



- **Cost Explorer**: `ce:GetCostAndUsage`, `ce:GetAnomalies`, `ce:GetReservationPurchaseRecommendation`, `ce:GetSavingsPlansRecommendation`

- **Tagging**: `tag:GetResources`

- **STS**: `sts:AssumeRole` (for cross-account access)    # Flatten results



    rows = []



    for day in resp["ResultsByTime"]:



```json        for group in day.get("Groups", []):



{            service = group["Keys"][0]



  "Version": "2012-10-17",            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])



  "Statement": [            rows.append({"date": day["TimePeriod"]["Start"], "service": service, "cost": amount})



    {



      "Effect": "Allow",    df = pd.DataFrame(rows)



      "Action": [    if df.empty:



        "ce:GetCostAndUsage",        return df



        "ce:GetAnomalies",



        "ce:GetReservationPurchaseRecommendation",    # Sum across days, keep top 5 services by total



        "ce:GetSavingsPlansRecommendation",    totals = df.groupby("service", as_index=False)["cost"].sum().sort_values("cost", ascending=False)



        "organizations:DescribeOrganization",    top = totals.head(5)["service"].tolist()



        "organizations:ListAccounts",



        "resource-groups:SearchResources",    top_df = df[df["service"].isin(top)]



        "resource-groups:ListGroups",    return top_df  # daily costs for the top 5 services



        "support:DescribeServices",



        "sts:GetCallerIdentity"def check_tag_compliance(required_keys: List[str]) -> pd.DataFrame:



      ],    """List resources that are missing any required tag keys using Resource Groups Tagging API."""



      "Resource": "*"    session = get_boto3_session()



    tag = session.client("resourcegroupstaggingapi")



  ]    paginator = tag.get_paginator("get_resources")



```    missing_rows = []







### 4. Run the Dashboard    for page in paginator.paginate(ResourcesPerPage=100):



```bash            arn = res["ResourceARN"]



# Development mode with auto-reload            tags = {t["Key"]: t.get("Value", "") for t in res.get("Tags", [])}



make run-dev            missing = [k for k in required_keys if k not in tags or tags[k] == ""]



            if missing:



# Production mode                missing_rows.append({"resource_arn": arn, "missing_keys": ",".join(missing)})



make run



    return pd.DataFrame(missing_rows)



# Using Poetry directly



poetry run streamlit run app/streamlit_app.pydef run_daily_job():



```    lookback_days = int(os.getenv("LOOKBACK_DAYS", "30"))



    required_keys = [k.strip() for k in os.getenv("REQUIRED_TAG_KEYS", "cost_center,env").split(",")]



Open http://localhost:8501 in your browser.



    top_df = fetch_top5_services_spend(lookback_days)



## 🐳 Docker Deployment    noncompliant_df = check_tag_compliance(required_keys)







### Build and Run with Docker    # Write to output (artifact for CI or local reference)



    os.makedirs("output", exist_ok=True)



```bash    top_path = f"output/top5_services_{dt.date.today().isoformat()}.csv"



# Build production image    noncomp_path = f"output/tag_noncompliant_{dt.date.today().isoformat()}.csv"



make build



    top_df.to_csv(top_path, index=False)



# Run container    noncompliant_df.to_csv(noncomp_path, index=False)



make docker-run



    return top_path, noncomp_path



# View logs```



make logs



6) Tiny Streamlit dashboard (Plotly bar + noncompliant table)



# Stop container



make stop`app/streamlit_app.py`



```



```python



### Docker Compose (Optional)import os



import pandas as pd



```yamlimport plotly.express as px



version: '3.8'import streamlit as st



services:from finops import fetch_top5_services_spend, check_tag_compliance



  finops-dashboard:



    build: .st.set_page_config(page_title="AWS FinOps Dashboard", layout="wide")



    ports:st.title("AWS FinOps Dashboard")



      - "8501:8501"



    environment:lookback_days = st.sidebar.number_input("Lookback days", min_value=7, max_value=90, value=int(os.getenv("LOOKBACK_DAYS", "30")))



      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}required_keys = [k.strip() for k in os.getenv("REQUIRED_TAG_KEYS", "cost_center,env").split(",")]



      - AWS_ROLE_ARN=${AWS_ROLE_ARN}



    env_file:with st.spinner("Querying AWS Cost Explorer..."):



      - .env    df = fetch_top5_services_spend(lookback_days)



    restart: unless-stopped



    healthcheck:if df.empty:



      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]    st.info("No cost data returned. Check credentials/permissions and Cost Explorer activation.")



      interval: 30selse:



      timeout: 10s    totals = df.groupby("service", as_index=False)["cost"].sum().sort_values("cost", ascending=False)



      retries: 3    st.subheader("Top 5 services by total spend")



```    fig = px.bar(totals, x="service", y="cost")



    st.plotly_chart(fig, use_container_width=True)



## 🔧 Configuration



    st.subheader("Daily breakdown (top 5)")



### Environment Variables    st.dataframe(df.sort_values(["date","service"]).reset_index(drop=True), use_container_width=True)







| Variable | Description | Required | Default |st.divider()



|----------|-------------|----------|---------|st.subheader(f"Tag compliance (required: {', '.join(required_keys)})")



| `AWS_DEFAULT_REGION` | Primary AWS region | Yes | `us-east-1` |



| `AWS_ROLE_ARN` | IAM role ARN for OIDC | Optional | - |with st.spinner("Checking Resource Groups Tagging API..."):



| `AWS_ACCESS_KEY_ID` | AWS access key | Optional | - |    noncomp = check_tag_compliance(required_keys)



| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Optional | - |



if noncomp.empty:



### Required Tags Configuration    st.success("All scanned resources contain required tag keys ✅")



else:



Edit `app/finops.py` to customize required tags:    st.warning(f"{len(noncomp)} resources missing required tags")



    st.dataframe(noncomp, use_container_width=True)



```python```



self.required_tags = [8) Daily automation with GitHub Actions (serverless CI)



    'Environment',    # e.g., Production, Staging, Development



    'Owner',         # e.g., team-backend, john.doe@company.com`.github/workflows/daily.yml`



    'Project',       # e.g., web-app, data-pipeline



    'CostCenter'     # e.g., engineering, marketing```yaml



]name: Daily FinOps Report



```



on:



### Cost Thresholds  schedule:



    - cron: "0 9 * * *"   # daily at 09:00 UTC



Customize alert thresholds in `app/finops.py`:  workflow_dispatch: {}







```pythonpermissions:



self.cost_thresholds = {  id-token: write   # for OIDC



    'daily_warning': Decimal('1000.00'),    # $1,000/day  contents: read



    'monthly_warning': Decimal('10000.00'), # $10,000/month



    'anomaly_threshold': 0.20               # 20% increaseenv:



}  AWS_REGION: us-east-1



```  LOOKBACK_DAYS: "30"



  REQUIRED_TAG_KEYS: "cost_center,env"



## 🤖 Automated Reporting  ASSUME_ROLE_ARN: ${{ secrets.ASSUME_ROLE_ARN }}  # set in repo secrets







### GitHub Actions Setupjobs:



  run:



1. **Configure Repository Secrets:**    runs-on: ubuntu-latest



   ```bash    steps:



   # Required secrets      - uses: actions/checkout@v4



   AWS_ROLE_ARN=arn:aws:iam::ACCOUNT:role/FinOpsRole



         - name: Configure AWS credentials (OIDC)



   # Optional for notifications        uses: aws-actions/configure-aws-credentials@v4



   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...        with:



   ```          role-to-assume: ${{ env.ASSUME_ROLE_ARN }}



          aws-region: ${{ env.AWS_REGION }}



2. **Setup OIDC Provider:**



   ```bash      - name: Set up Python



   # Create OIDC provider in AWS IAM        uses: actions/setup-python@v5



   aws iam create-open-id-connect-provider \        with:



     --url https://token.actions.githubusercontent.com \          python-version: "3.11"



     --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \



     --client-id-list sts.amazonaws.com      - name: Install deps



   ```        run: |



          python -m pip install --upgrade pip



3. **Create IAM Role for GitHub Actions:**



   ```json



   {      - name: Run daily job (Cost + Tag compliance)



     "Version": "2012-10-17",        run: |



     "Statement": [          python -c "from app.finops import run_daily_job; print(run_daily_job())"



       {



         "Effect": "Allow",      - name: Upload artifacts



         "Principal": {        uses: actions/upload-artifact@v4



           "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com"        with:



         },          name: finops-output



         "Action": "sts:AssumeRoleWithWebIdentity",          path: output/*.csv



         "Condition": {```



           "StringEquals": {This uses OIDC to assume an AWS role. In your repo Secrets and variables → Actions → Secrets, set `ASSUME_ROLE_ARN`.



             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",



             "token.actions.githubusercontent.com:sub": "repo:your-org/AWS-FinOps-Dashboard:ref:refs/heads/main"9) IAM: minimal read-only permissions (attach to the assumed role)



           }



         }Example policy (attach to `FinOpsDashboardReadOnly` role)



       }



     ]```json



   }{



   ```  "Version": "2012-10-17",



  "Statement": [



4. **Daily Reports Run Automatically:**    { "Effect": "Allow", "Action": ["ce:GetCostAndUsage"], "Resource": "*" },



   - Scheduled daily at 8 AM UTC    { "Effect": "Allow", "Action": ["tag:GetResources"], "Resource": "*" },



   - Manual trigger available    { "Effect": "Allow", "Action": ["sts:AssumeRole"], "Resource": "*" }



   - Automatic GitHub issue creation for alerts  ]



   - Slack/Teams notifications}



```



## 📊 Dashboard Pages



You can further scope `sts:AssumeRole` as needed. Ensure Cost Explorer is enabled in the account.



### 1. Overview Dashboard10) README.md (concise, customer-friendly)



- Key metrics summary



- Cost trends visualizationREADME.md



- Alert status



- Quick access to critical information```markdown



# AWS FinOps Dashboard



### 2. Cost Analysis



- Detailed cost breakdowns by service, account, and region**Serverless FinOps dashboard pulling AWS Cost Explorer data to track spend and tag compliance. Demonstrates cloud cost visibility and governance automation.**



- Historical trend analysis



- Cost comparison tools## Features



- Top 5 AWS services by spend (last N days) via **Cost Explorer**



- **Tag compliance** check for required keys (default: `cost_center`, `env`)



### 3. Tag Compliance- **Streamlit** UI with Plotly charts



- Organization-wide compliance scoring- **Daily GitHub Action** runs headless and uploads CSVs as artifacts



- Missing tag analysis- Containerized (Docker) or local venv – no heavy local installs



- Service-level compliance breakdown



- Remediation recommendations## Quick start (Docker)



```bash



### 4. Anomaly Detectioncp .env.example .env     # fill AWS auth (or role), region, and options



- Real-time anomaly alertsmake run                 # open http://localhost:8501



- Root cause analysis```



- Historical anomaly trends



- Impact assessmentLocal venv







### 5. Recommendations```bash



- Reserved Instance opportunitiespython -m venv .venv && . .venv/bin/activate



- Savings Plans recommendationspip install -r requirements.txt



- Resource optimization suggestionscp .env.example .env



- Estimated savings calculationsstreamlit run app/streamlit_app.py



```



### 6. Reports & Export



- Generate custom reportsDaily reports in CI



- Export data in multiple formats



- Scheduled report managementConfigure repo secret: ASSUME_ROLE_ARN → Role with CE + Tagging read.



- Historical report access



CI generates CSVs under output/ and uploads as build artifacts.



## 🛠️ Development



Required AWS permissions



### Project Structure



ce:GetCostAndUsage



```



AWS-FinOps-Dashboard/tag:GetResources



├── app/                          # Main application package



│   ├── __init__.py              # Package initialization(CI) sts:AssumeRole for OIDC into the account



│   ├── aws_session.py           # AWS session management



│   ├── finops.py                # FinOps business logicNotes



│   └── streamlit_app.py         # Streamlit UI application



├── .github/Ensure Cost Explorer is enabled.



│   └── workflows/



│       └── daily.yml            # Automated daily reportingTag compliance uses Resource Groups Tagging API, which scans supported services. Some resource types may not appear if they do not support tagging APIs.



├── tests/                       # Test suite



├── Dockerfile                   # Container configuration```bash



├── Makefile                     # Development commands



├── pyproject.toml              # Poetry configuration---



├── requirements.txt            # Docker dependencies



├── .env.example               # Environment template## 11) (Optional) Lambda scheduler (if you prefer AWS over GH Actions)



└── README.md                  # This file



```- Package `app/finops.py` as handler `lambda_function.py` with a `handler(event, context)` that calls `run_daily_job()`.



- Create EventBridge rule (cron daily) → targets the Lambda.



### Development Commands- Use **Execution Role** with same read-only policy as above, plus S3 write if you want to store CSVs in a bucket instead of `output/`.







```bash*(Kept out of the main path to stay lean; GitHub Actions is simpler to hand off.)*



# Install development dependencies



make install-dev---







# Run tests## 12) Handoff checklist (low-maintenance)



make test



- [ ] Cost Explorer enabled



# Code formatting- [ ] `ASSUME_ROLE_ARN` secret set in GitHub



make format- [ ] Role has CE + Tagging read permissions



- [ ] `.env` committed as `.env.example` only (no secrets)



# Linting- [ ] Customer runs via Docker: `make run`



make lint- [ ] Daily artifacts visible in Actions → latest run → Artifacts







# Security scan---



make security-scan



### That’s it



# Run development serverYou get a tiny codebase, containerized runtime, no long-lived creds in CI (OIDC), and a daily automated report. If you want me to bundle this into a single downloadable README/ZIP or tweak the look of the Streamlit page, say the word and I’ll ship it.



make run-dev```



# Build Docker image

make build



# Full CI test suite

make ci-test

```



### Testing



```bash

# Run all tests

poetry run pytest



# Run with coverage

poetry run pytest --cov=app --cov-report=html



# Run specific test file

poetry run pytest tests/test_finops.py -v

```



### Adding New Features



1. **Create feature branch:**

   ```bash

   git checkout -b feature/new-dashboard-widget

   ```



2. **Implement changes:**

   - Add business logic to `app/finops.py`

   - Update UI in `app/streamlit_app.py`

   - Add tests in `tests/`



3. **Test thoroughly:**

   ```bash

   make ci-test

   ```



4. **Submit pull request** with:

   - Clear description of changes

   - Test coverage for new code

   - Documentation updates



## 🔐 Security Considerations



### Authentication

- **OIDC Integration**: Secure GitHub Actions authentication

- **IAM Role Assumption**: Temporary credentials only

- **Least Privilege**: Minimal required permissions

- **Credential Rotation**: Automatic temporary credential refresh



### Data Protection

- **Encryption in Transit**: HTTPS/TLS for all API calls

- **No Credential Storage**: Credentials never stored in code

- **Environment Isolation**: Separate environments for dev/prod

- **Audit Logging**: Comprehensive AWS API call logging



### Container Security

- **Non-root User**: Container runs as non-privileged user

- **Minimal Base Image**: Python slim image for reduced attack surface

- **Security Scanning**: Automated vulnerability scanning

- **Regular Updates**: Dependency updates via Dependabot



## 📈 Monitoring & Observability



### Application Metrics

- **Health Checks**: Streamlit health endpoint monitoring

- **Performance Tracking**: Response time and error rate monitoring

- **Resource Usage**: CPU, memory, and network utilization

- **User Analytics**: Dashboard usage patterns



### AWS API Monitoring

- **Rate Limiting**: Respect AWS API rate limits

- **Error Tracking**: AWS API error monitoring and alerting

- **Cost Tracking**: Monitor AWS API usage costs

- **Performance Optimization**: Cache frequently accessed data



### Alerting

- **Cost Thresholds**: Automated alerts for spending spikes

- **Compliance Violations**: Tag compliance degradation alerts

- **System Health**: Application and infrastructure monitoring

- **Anomaly Detection**: Unusual pattern detection and notification



## 🚀 Deployment Options



### 1. Local Development

```bash

poetry install

poetry run streamlit run app/streamlit_app.py

```



### 2. Docker Container

```bash

docker build -t aws-finops-dashboard .

docker run -p 8501:8501 --env-file .env aws-finops-dashboard

```



### 3. Cloud Deployment



#### AWS ECS/Fargate

```bash

# Build and push to ECR

aws ecr create-repository --repository-name aws-finops-dashboard

docker build -t aws-finops-dashboard .

docker tag aws-finops-dashboard:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/aws-finops-dashboard:latest

docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/aws-finops-dashboard:latest

```



#### Kubernetes

```yaml

apiVersion: apps/v1

kind: Deployment

metadata:

  name: finops-dashboard

spec:

  replicas: 2

  selector:

    matchLabels:

      app: finops-dashboard

  template:

    metadata:

      labels:

        app: finops-dashboard

    spec:

      containers:

      - name: dashboard

        image: aws-finops-dashboard:latest

        ports:

        - containerPort: 8501

        env:

        - name: AWS_DEFAULT_REGION

          value: "us-east-1"

        resources:

          requests:

            memory: "512Mi"

            cpu: "250m"

          limits:

            memory: "1Gi"

            cpu: "500m"

```



## 🤝 Contributing



We welcome contributions! Please follow these guidelines:



### Getting Started

1. Fork the repository

2. Create a feature branch

3. Make your changes

4. Add tests for new functionality

5. Ensure all tests pass

6. Submit a pull request



### Code Standards

- **Python Style**: Follow PEP 8 and use Black for formatting

- **Type Hints**: Use type hints for all function parameters and returns

- **Documentation**: Add docstrings for all public methods

- **Testing**: Maintain >90% test coverage



### Pull Request Process

1. Update documentation for any new features

2. Add tests for bug fixes and new features

3. Ensure CI/CD pipeline passes

4. Request review from maintainers



## 📄 License



This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.



## 🆘 Support



### Documentation

- **GitHub Issues**: Report bugs and request features

- **Discussions**: Ask questions and share ideas

- **Wiki**: Additional documentation and guides



### Getting Help

1. Check existing GitHub issues

2. Review documentation and README

3. Create detailed issue with:

   - Environment details

   - Reproduction steps

   - Expected vs actual behavior

   - Relevant logs



### Community

- **Slack Channel**: #finops-dashboard

- **Monthly Office Hours**: First Tuesday of each month

- **Contribution Guidelines**: See CONTRIBUTING.md



---



## 🎯 Roadmap



### Q1 2024

- [ ] Multi-cloud support (Azure, GCP)

- [ ] Advanced forecasting models

- [ ] Custom dashboard builder

- [ ] API rate limiting improvements



### Q2 2024

- [ ] Machine learning-based anomaly detection

- [ ] Integration with third-party tools (Jira, ServiceNow)

- [ ] Enhanced mobile responsive design

- [ ] Real-time cost streaming



### Q3 2024

- [ ] Multi-tenant support

- [ ] Advanced RBAC and SSO integration

- [ ] Custom alerting rules engine

- [ ] Integration with CI/CD pipelines



### Q4 2024

- [ ] AI-powered cost optimization recommendations

- [ ] Advanced data visualization options

- [ ] Export to business intelligence tools

- [ ] Enhanced security and compliance features



---



**Built with ❤️ by the FinOps Team**



For more information, visit our [documentation](https://github.com/your-org/AWS-FinOps-Dashboard/wiki) or join our [community discussions](https://github.com/your-org/AWS-FinOps-Dashboard/discussions).

## Automated Reporting & Scheduling

The dashboard now supports generating multi-format FinOps reports (CSV / JSON / Excel) with optional scheduled execution and SES email delivery.

### Key Capabilities
- Flexible date ranges: explicit start/end, presets (`month_to_date`, `previous_full_month`), or rolling `last_n_days`.
- Multi-format writers: CSV (per dataset), JSON (single payload), Excel (multiple sheets + summary) with row safety cap.
- APScheduler-based cron scheduling (background) — disabled by default.
- Optional SES email dispatch with attachment size guard (< 10 MB total raw message).

### Environment Variables
Add the following variables to `.env` (or your deployment secret store) as needed:

```dotenv
# Reporting
REPORT_OUTPUT_DIR=reports
REPORT_DEFAULT_FORMATS=csv,json,xlsx
# Enable and configure scheduling (5-field cron, timezone optional)
REPORT_SCHEDULE_ENABLED=false
REPORT_SCHEDULE_CRON=0 2 * * *
REPORT_SCHEDULE_TIMEZONE=UTC

# SES Email (set SES_ENABLED=true only after verifying sender identity in SES)
SES_ENABLED=false
SES_REGION=us-east-1
SES_SENDER_EMAIL=finops-reports@example.com
SES_RECIPIENT_EMAILS=owner@example.com,finops@example.com

# Optional Excel row cap (defaults to 1000000)
MAX_EXCEL_ROWS=1000000
```

### Programmatic Report Generation
```python
from app.export import generate_report
from app.finops import FinOpsAnalyzer

analyzer = FinOpsAnalyzer()
result = generate_report(analyzer, formats=["csv","json"], last_n_days=7, email=True)
print(result["files"], result.get("email_body"))
```

### Scheduling
Call this early in your app startup (e.g., Streamlit script or CLI bootstrap) if scheduling is desired:
```python
from app.scheduler import init_scheduler
init_scheduler()  # respects REPORT_SCHEDULE_ENABLED
```
List or stop jobs:
```python
from app.scheduler import list_jobs, shutdown_scheduler
print(list_jobs())
shutdown_scheduler()
```

### Email Sending Behavior
When `email=True` and SES is enabled & configured, attachments are added until the raw message size approaches the limit. Failures to send are logged and do not prevent file generation.

### Testing Overview
- Scheduler: cron job idempotence & disabled mode tested.
- Export edge cases: invalid date ranges, rolling window logic.
- SES: success, disabled, and incomplete configuration paths mocked.

### Future Enhancements (Backlog)
- S3 archival of generated reports
- Parquet / PDF formats
- Compressing large attachment sets
- UI trigger (Streamlit button) for ad-hoc generation

> NOTE: This section was added with accessibility in mind; review formatting & run manual accessibility checks (e.g., headings order, contrast in your published medium).

### Permissions Self-Check (CLI)
Run an automated probe of required AWS APIs (Cost Explorer, Organizations, Tagging, Support) and exit non-zero if critical cost permissions are missing. Useful for CI gating before deploying or starting scheduled jobs.

```bash
poetry run python scripts/permissions_check.py
# or
python scripts/permissions_check.py
```
Sample output:
```json
{
  "status": "ok",
  "critical_missing": [],
  "permissions": {
    "cost_explorer": true,
    "organizations": true,
    "support": false,
    "resource_groups": true
  },
  "region": "us-east-1",
  "auth_strategy": "profile"
}
```
If Cost Explorer permission is missing you will instead see:
```json
{
  "status": "incomplete",
  "critical_missing": ["cost_explorer"],
  ...
}
```
Exit codes: 0 = all good, 1 = critical missing, 2 = unexpected runtime/auth error.

### Minimal IAM Policy File
A curated starter policy (read-only) is available in `iam/finops-minimal-policy.json`. Attach it (or merge into an existing role) and ensure Cost Explorer is enabled in the AWS console. Add SES actions only if you enable email features. Tighten with resource scoping / condition keys per your governance.
## 🎨 User Customization (New)
The dashboard now supports per-user (per AWS principal ARN) preferences stored locally under `.finops_prefs/`:

| Feature | Description | How to Configure |
|---------|-------------|------------------|
| Overview Widgets | Choose which KPI widgets & charts appear | Sidebar → ⚙️ Customize Dashboard → Overview Widgets |
| Personalized Thresholds | Override daily / monthly cost alert triggers | Sidebar customization inputs (set 0 to inherit global) |
| Required Tag Keys | Override global required tag list for compliance view | Sidebar text input (comma list) |
| Theme Preference | Light / Dark (applies to Streamlit theme toggle) | Sidebar select (requires reload to fully apply) |
| Default Date Range | Auto-selected range on load | Sidebar select |
| Persistence | Preferences saved to hashed file per principal | Automatic on Save |

Preferences are hashed by principal ARN (first 16 hex chars of SHA-256) to avoid leaking full ARNs in filenames.

Example preference file path:
```
.finops_prefs/prefs-<hash>.json
```

To reset preferences, delete the corresponding file; defaults will be regenerated on next load.

Roadmap enhancements:
* Saved named filter sets
* Organization-wide enforced baseline vs. personal overrides
* Export/import preference bundles

---
