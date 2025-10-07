# AWS FinOps Dashboard

A **Streamlit-based dashboard** for AWS cost monitoring, tag compliance tracking, and financial operations management.

## What it does

- **Cost Analytics**: Real-time AWS spend by service, account, and time period
- **Tag Compliance**: Monitor required tags across your AWS resources  
- **Anomaly Detection**: Identify unusual spending patterns using Cost Explorer
- **Multi-Account Support**: Aggregate data across AWS Organizations (optional)
- **Automated Reporting**: Generate CSV/JSON/Excel reports with optional email delivery

## Quick Start

### 1. Install
```bash
git clone <repo-url>
cd AWS-FinOps-Dashboard
poetry install
```

### 2. Configure AWS
```bash
cp .env.example .env
# Edit .env with your AWS region and optional role
```

### 3. Run
```bash
poetry run streamlit run app/streamlit_app.py
```
Open http://localhost:8501

## Docker Alternative
```bash
docker build -t finops-dashboard .
docker run --env-file .env -p 8501:8501 finops-dashboard
```

## AWS Requirements

**Permissions needed:**
- `ce:GetCostAndUsage` - Cost data access
- `ce:GetAnomalies` - Anomaly detection  
- `resource-groups:SearchResources` - Tag compliance
- `organizations:ListAccounts` (optional) - Multi-account support

**Setup:**
1. Enable Cost Explorer in your AWS account
2. Create IAM role with above permissions
3. Set `AWS_ROLE_ARN` in `.env` (or use your existing AWS profile)

## Key Settings

Set these in `.env`:

```bash
AWS_REGION=us-east-1
AWS_ROLE_ARN=arn:aws:iam::123456789:role/FinOpsRole  # optional
REQUIRED_TAG_KEYS=Environment,Owner,Project,CostCenter
SINGLE_ACCOUNT_MODE=false  # true = skip Organizations calls
```

## Documentation

- [Detailed Configuration](docs/configuration.md)
- [Security & IAM Setup](docs/security.md)
- [API Usage](docs/api.md)
- [Troubleshooting](docs/troubleshooting.md)

## License

MIT - see [LICENSE](LICENSE)
