# API Usage

## Programmatic Report Generation

```python
from app.export import generate_report
from app.finops import FinOpsAnalyzer

# Initialize analyzer
analyzer = FinOpsAnalyzer()

# Generate reports for last 7 days
result = generate_report(
    analyzer=analyzer,
    formats=["csv", "json", "xlsx"],
    last_n_days=7,
    email=False
)

print("Generated files:", result["files"])
```

## Date Range Options

### Rolling Windows
```python
# Last N days
generate_report(analyzer, last_n_days=30)

# Specific date range
generate_report(analyzer, start_date="2025-01-01", end_date="2025-01-31")
```

### Preset Ranges
```python
# Month to date
generate_report(analyzer, preset="month_to_date")

# Previous full month
generate_report(analyzer, preset="previous_full_month")

# Quarter to date
generate_report(analyzer, preset="quarter_to_date")
```

## Email Reports

```python
# Enable email delivery
result = generate_report(
    analyzer=analyzer,
    formats=["csv", "json"],
    last_n_days=7,
    email=True
)

if result.get("email_sent"):
    print("Email sent successfully")
    print("Email body:", result["email_body"])
else:
    print("Email not sent:", result.get("email_error"))
```

## Scheduling

### Enable Background Scheduler
```python
from app.scheduler import init_scheduler, list_jobs, shutdown_scheduler

# Start scheduler (respects REPORT_SCHEDULE_ENABLED setting)
init_scheduler()

# List active jobs
jobs = list_jobs()
print(f"Active jobs: {len(jobs)}")

# Shutdown scheduler
shutdown_scheduler()
```

### Manual Job Trigger
```python
from app.finops import run_daily_job

# Run the same job that the scheduler executes
file_paths = run_daily_job()
print("Generated files:", file_paths)
```

## Core Analysis Functions

### Cost Analysis
```python
from app.finops import FinOpsAnalyzer

analyzer = FinOpsAnalyzer()

# Get cost data for top services
cost_data = analyzer.get_cost_and_usage(
    start_date="2025-01-01",
    end_date="2025-01-31", 
    granularity="DAILY",
    group_by="SERVICE"
)

# Get cost anomalies
anomalies = analyzer.get_cost_anomalies(
    start_date="2025-01-01",
    end_date="2025-01-31"
)
```

### Tag Compliance
```python
# Check tag compliance
compliance_data = analyzer.get_tag_compliance(
    required_tags=["Environment", "Owner", "Project"]
)

print(f"Compliance rate: {compliance_data['compliance_rate']:.1%}")
print(f"Non-compliant resources: {len(compliance_data['non_compliant'])}")
```

### Account Information
```python
# List organization accounts (if multi-account mode)
accounts = analyzer.list_accounts()

# Get current account info
current_account = analyzer.get_current_account()
```

## Configuration API

```python
from app.config import get_settings

# Access configuration
settings = get_settings()
print(f"Region: {settings.aws_region}")
print(f"Required tags: {settings.required_tag_keys}")
print(f"Single account mode: {settings.single_account_mode}")
```

## Error Handling

```python
try:
    result = generate_report(analyzer, last_n_days=7)
except Exception as e:
    print(f"Report generation failed: {e}")
    
    # Check AWS credentials
    from app.aws_session import AWSSessionManager
    session_mgr = AWSSessionManager()
    status = session_mgr.diagnose_credentials()
    print(f"Auth status: {status}")
```

## Custom Export Formats

```python
# CSV only
result = generate_report(analyzer, formats=["csv"], last_n_days=30)

# JSON with custom filename prefix
result = generate_report(
    analyzer,
    formats=["json"], 
    last_n_days=7,
    output_prefix="weekly_report"
)

# Excel with row limit
result = generate_report(
    analyzer,
    formats=["xlsx"],
    last_n_days=90,
    max_excel_rows=50000  # Override default limit
)
```

## Integration Examples

### Slack Notifications
```python
import requests

def send_slack_notification(webhook_url, report_files):
    message = {
        "text": f"FinOps report generated with {len(report_files)} files",
        "attachments": [
            {
                "color": "good",
                "fields": [
                    {"title": "Files", "value": "\n".join(report_files), "short": False}
                ]
            }
        ]
    }
    
    response = requests.post(webhook_url, json=message)
    return response.status_code == 200
```

### S3 Upload
```python
import boto3

def upload_to_s3(file_paths, bucket_name, prefix="finops-reports/"):
    s3 = boto3.client('s3')
    
    for file_path in file_paths:
        key = f"{prefix}{os.path.basename(file_path)}"
        s3.upload_file(file_path, bucket_name, key)
        print(f"Uploaded {file_path} to s3://{bucket_name}/{key}")
```