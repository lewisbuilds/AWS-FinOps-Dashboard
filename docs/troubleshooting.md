# Troubleshooting

## Common Issues

### Authentication Problems

#### "AssumeRole pre-flight failed: no base credentials"
**Cause:** AWS_ROLE_ARN is set but no base credentials available

**Solutions:**
1. Set up AWS profile: `aws configure sso` then set `AWS_PROFILE=your-profile`
2. Use static keys (dev only): set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
3. Remove role assumption: unset `AWS_ROLE_ARN` to use direct credentials

#### "AccessDenied" on Cost Explorer APIs
**Cause:** Missing required permissions

**Solutions:**
1. Ensure Cost Explorer is enabled (AWS Console → Billing → Cost Explorer)
2. Wait 24 hours after enabling Cost Explorer for data availability
3. Verify IAM permissions include `ce:GetCostAndUsage`, `ce:GetAnomalies`
4. Check if using correct region (Cost Explorer is global but needs a region)

### Data Issues

#### "No cost data returned"
**Causes:**
- Cost Explorer not enabled
- No spending in the time period
- Data not yet available (24-48 hour delay)

**Solutions:**
1. Verify spending exists in AWS Billing console
2. Try a longer time range (last 30 days)
3. Check if using correct accounts/region

#### Tag compliance shows 0% or unexpected results
**Causes:**
- Resource Groups Tagging API doesn't cover all services
- Tags not applied to resources
- Required tag keys case-sensitive

**Solutions:**
1. Verify required tag keys match exactly (case-sensitive)
2. Check resources have tags in AWS Console
3. Some resources (like S3 buckets) may not appear in Resource Groups API

### Configuration Issues

#### Streamlit app won't start
**Common fixes:**
```bash
# Install dependencies
poetry install

# Check Python version (requires 3.11+)
python --version

# Run with debug info
poetry run streamlit run app/streamlit_app.py --logger.level=debug
```

#### Reports not generating
**Check these settings:**
```bash
# Verify output directory exists and is writable
ls -la reports/

# Check disk space
df -h

# Verify environment variables
env | grep -E "(AWS|REPORT)"
```

### Performance Issues

#### Slow dashboard loading
**Optimizations:**
1. Enable single account mode: `SINGLE_ACCOUNT_MODE=true`
2. Reduce lookback days: `LOOKBACK_DAYS=7`
3. Disable support probe: `SUPPORT_PROBE_ENABLED=false`

#### Large Excel files
**Solutions:**
1. Reduce row limit: `MAX_EXCEL_ROWS=100000`
2. Use shorter time periods
3. Switch to CSV format for large datasets

### Email Issues

#### SES emails not sending
**Check:**
1. SES sender email verified
2. If in sandbox, recipients must be verified
3. Correct SES region: `SES_REGION=us-east-1`
4. Email size under 10MB (automatic attachment filtering)

**Debug steps:**
```python
# Test SES configuration
from app.email import test_ses_config
test_ses_config()
```

### Permission Issues

#### Organizations access denied
**If single account only:**
```bash
SINGLE_ACCOUNT_MODE=true
```

**If multi-account setup:**
1. Verify Organizations permissions in central role
2. Check member account roles exist
3. Ensure trust relationships are correct

## Debug Mode

### Enable detailed logging
```bash
LOG_LEVEL=DEBUG
LOG_FORMAT=json
```

### Health check endpoint
Visit `/health` in the Streamlit app for:
- Credential strategy status
- AWS API connectivity
- Permission verification
- Configuration summary

### Manual verification

#### Test AWS connectivity
```bash
# Test credentials
aws sts get-caller-identity

# Test Cost Explorer
aws ce get-cost-and-usage --time-period Start=2025-01-01,End=2025-01-02 \
  --granularity DAILY --metrics UnblendedCost

# Test Resource Groups
aws resource-groups search-resources --resource-query Type=TAG_FILTERS_1_0
```

#### Test role assumption
```bash
aws sts assume-role \
  --role-arn arn:aws:iam::123456789:role/FinOpsRole \
  --role-session-name test
```

## Performance Monitoring

### Check API rate limits
The app includes automatic retry logic, but you can monitor:
- CloudTrail logs for API call patterns
- Cost Explorer API throttling
- Organizations API limits

### Memory usage
For large datasets:
```bash
# Monitor memory usage
docker stats finops-dashboard

# Or locally
htop
```

## Getting Help

### Log collection
When reporting issues, include:

1. **Environment info:**
   ```bash
   python --version
   poetry --version
   aws --version
   ```

2. **Configuration (remove sensitive data):**
   ```bash
   env | grep -E "(AWS_REGION|SINGLE_ACCOUNT|LOG_LEVEL)" 
   ```

3. **Error logs:**
   - Streamlit debug output
   - AWS API error responses
   - Python stack traces

### Issue templates
Please include:
- Expected behavior
- Actual behavior  
- Steps to reproduce
- Environment details
- Relevant log excerpts

### Community resources
- GitHub Issues for bug reports
- Discussions for questions
- Security issues: email security@yourcompany.com