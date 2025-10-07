# Security & IAM Setup

## IAM Policies

### Central Role (Multi-Account)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CostExplorer",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetAnomalies", 
        "ce:GetReservationPurchaseRecommendation",
        "ce:GetSavingsPlansPurchaseRecommendation"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Organizations",
      "Effect": "Allow",
      "Action": [
        "organizations:DescribeOrganization",
        "organizations:ListAccounts"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ResourceGroups",
      "Effect": "Allow", 
      "Action": [
        "resource-groups:ListGroups",
        "resource-groups:SearchResources"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AssumeRole",
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole",
        "sts:GetCallerIdentity"
      ],
      "Resource": "arn:aws:iam::*:role/FinOpsMemberReadOnly"
    }
  ]
}
```

### Member Account Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ce:GetCostAndUsage",
      "Resource": "*"
    }
  ]
}
```

### Single Account Mode
If using `SINGLE_ACCOUNT_MODE=true`, you only need:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetAnomalies",
        "resource-groups:SearchResources"
      ],
      "Resource": "*"
    }
  ]
}
```

## Security Features

### Data Protection
- Export sanitization prevents spreadsheet injection attacks
- Path traversal protection on file outputs
- Random filename suffixes prevent conflicts
- Excel row limits prevent memory exhaustion

### Credential Security
- No hardcoded credentials
- Supports AWS credential chain (profiles, roles, SSO)
- OIDC for GitHub Actions
- Least privilege IAM policies

### CI/CD Security
- Automated dependency scanning with `pip-audit`
- Security workflow fails on critical vulnerabilities
- No long-lived secrets in GitHub

## Setup Instructions

### 1. Create IAM Role
```bash
# Create role with trust policy for your user/service
aws iam create-role --role-name FinOpsDashboardRole \
  --assume-role-policy-document file://trust-policy.json

# Attach policy
aws iam attach-role-policy --role-name FinOpsDashboardRole \
  --policy-arn arn:aws:iam::ACCOUNT:policy/FinOpsPolicy
```

### 2. Enable Cost Explorer
1. Go to AWS Billing Console
2. Navigate to Cost Explorer  
3. Click "Enable Cost Explorer"
4. Wait 24 hours for initial data

### 3. Verify Permissions
```bash
# Test role assumption
aws sts assume-role --role-arn arn:aws:iam::ACCOUNT:role/FinOpsDashboardRole \
  --role-session-name test

# Test Cost Explorer access
aws ce get-cost-and-usage --time-period Start=2025-01-01,End=2025-01-02 \
  --granularity DAILY --metrics UnblendedCost
```

## GitHub Actions Setup

### 1. Configure OIDC Provider
```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --client-id-list sts.amazonaws.com
```

### 2. Create GitHub Actions Role
Trust policy for GitHub Actions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:your-org/AWS-FinOps-Dashboard:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

### 3. Add Repository Secret
- Go to repository Settings → Secrets and variables → Actions
- Add secret `AWS_ROLE_ARN` with your role ARN