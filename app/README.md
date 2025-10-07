# App Code Structure

## Core Modules

### `streamlit_app.py`
- Main Streamlit application entry point
- UI pages: Overview, Cost Analysis, Tag Compliance, Anomalies, Reports, Health
- User preference management and dashboard customization

### `finops.py` 
- Core business logic for financial operations
- AWS Cost Explorer API integration
- Tag compliance analysis
- Anomaly detection
- Multi-account data aggregation

### `aws_session.py`
- AWS credential management and session creation
- Role assumption logic
- Permission validation and diagnostics
- Credential strategy detection

### `config.py`
- Application configuration using Pydantic settings
- Environment variable validation
- Default values and constraints
- Settings for security, scheduling, and AWS integration

### `export.py`
- Multi-format report generation (CSV, JSON, Excel)
- Data sanitization for security
- File output management with path validation
- Email integration for report delivery

### `user_prefs.py`
- Per-user preference storage and management
- Dashboard customization (widgets, thresholds, tags)
- Secure preference file handling with principal hashing

### `scheduler.py` (if present)
- Background job scheduling using APScheduler
- Automated report generation
- Cron-based scheduling with timezone support

### `email.py` (if present)  
- SES email integration
- Attachment handling with size limits
- Email template management

## Key Design Patterns

### Configuration
- Centralized settings in `config.py`
- Environment variable overrides
- Validation at startup

### AWS Integration
- Session management with automatic retry/backoff
- Graceful error handling for API limits
- Support for both single and multi-account modes

### Security
- Input sanitization throughout data pipeline
- Path traversal protection
- Credential diagnostics without exposure

### Data Flow
```
streamlit_app.py → finops.py → aws_session.py → AWS APIs
                ↓
            export.py → File outputs + Email
```

## Development Guidelines

- Use type hints for all function parameters
- Handle AWS API errors gracefully
- Validate all user inputs
- Log security-relevant events
- Follow least privilege for AWS permissions
- Test with both single and multi-account configurations