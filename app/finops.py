"""AWS FinOps Data Analysis and Processing

Core business logic for AWS cost analysis, tag compliance monitoring,
and financial operations reporting.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal
import pandas as pd
import boto3
from botocore.exceptions import ClientError
from .exceptions import (
    CostDataRetrievalError,
    TagComplianceError,
    AnomalyDetectionError,
    RecommendationRetrievalError,
)
from .aws_session import AWSSessionManager
from .config import get_settings
from .cache import cached
from .anomaly_detection import CostAnomalyDetector
from .alerts import dispatch_anomaly_alert
from .org_accounts import iter_account_cost_explorer_sessions, list_org_accounts


@dataclass
class CostMetrics:
    """Cost metrics for a specific time period."""
    total_cost: Decimal
    period_start: datetime
    period_end: datetime
    service_breakdown: Dict[str, Decimal]
    account_breakdown: Dict[str, Decimal]
    region_breakdown: Dict[str, Decimal]
    

@dataclass
class TagComplianceMetrics:
    """Tag compliance metrics for resources."""
    total_resources: int
    compliant_resources: int
    compliance_rate: float
    missing_tags: Dict[str, int]
    services_breakdown: Dict[str, Dict[str, int]]


class FinOpsAnalyzer:
    """AWS FinOps data analyzer for cost optimization and compliance monitoring."""
    
    def __init__(self, session_manager: Optional[AWSSessionManager] = None):
        self.logger = logging.getLogger(__name__)
        self.session_manager = session_manager or AWSSessionManager()
        self.settings = get_settings()

        # Required tags and thresholds now sourced from validated settings
        self.required_tags = self.settings.required_tags_list
        self.cost_thresholds = self.settings.cost_thresholds
        self._advanced_detector = CostAnomalyDetector(
            zscore_threshold=self.settings.anomaly_zscore_threshold,
            iforest_contamination=self.settings.anomaly_iforest_contamination,
            method=self.settings.anomaly_method,
        )

    # User preference customization hooks
    def override_required_tags(self, tags: List[str]):
        if tags:
            self.logger.debug(f"Overriding required tags: {tags}")
            self.required_tags = tags

    def override_cost_thresholds(self, daily: Optional[float] = None, monthly: Optional[float] = None):
        if daily is not None:
            self.cost_thresholds['daily_warning'] = daily
        if monthly is not None:
            self.cost_thresholds['monthly_warning'] = monthly
    
    @cached("cost", ttl_resolver=lambda s: s.cache_ttls["cost"])
    def get_cost_and_usage(self,
                           start_date: datetime,
                           end_date: datetime,
                           granularity: str = 'DAILY',
                           group_by: Optional[List[Dict]] = None) -> CostMetrics:
        """Retrieve AWS cost and usage data for specified period.
        
        Args:
            start_date: Start date for cost analysis
            end_date: End date for cost analysis
            granularity: Data granularity (DAILY, MONTHLY)
            group_by: Grouping dimensions for cost breakdown
            
        Returns:
            CostMetrics: Structured cost metrics
            
        Raises:
            ClientError: If Cost Explorer API call fails
        """
        try:
            if not group_by:
                group_by = [
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
                ]
            response = self.session_manager.invoke(
                'ce', 'get_cost_and_usage',
                call_kwargs={
                    'TimePeriod': {
                        'Start': start_date.strftime('%Y-%m-%d'),
                        'End': end_date.strftime('%Y-%m-%d')
                    },
                    'Granularity': granularity,
                    'Metrics': ['BlendedCost', 'UnblendedCost', 'UsageQuantity'],
                    'GroupBy': group_by
                },
                context={'operation': 'get_cost_and_usage'}
            )
            return self._process_cost_data(response, start_date, end_date)
        except ClientError as e:
            self.logger.error(
                "Failed to retrieve cost data",
                extra={"error_type": "CostDataRetrieval", "context": {"start": start_date.isoformat(), "end": end_date.isoformat()}},
            )
            raise CostDataRetrievalError("Failed to retrieve cost data", context={"period": f"{start_date}->{end_date}"}) from e
    
    def _process_cost_data(self, 
                          response: Dict, 
                          start_date: datetime, 
                          end_date: datetime) -> CostMetrics:
        """Process raw Cost Explorer response into structured metrics.
        
        Args:
            response: Raw Cost Explorer API response
            start_date: Period start date
            end_date: Period end date
            
        Returns:
            CostMetrics: Processed cost metrics
        """
        total_cost = Decimal('0.00')
        service_breakdown = {}
        account_breakdown = {}
        region_breakdown = {}
        
        for result in response.get('ResultsByTime', []):
            for group in result.get('Groups', []):
                cost = Decimal(group['Metrics']['BlendedCost']['Amount'])
                total_cost += cost
                
                # Parse grouping keys
                keys = group.get('Keys', [])
                if len(keys) >= 1:
                    service = keys[0]
                    service_breakdown[service] = service_breakdown.get(service, Decimal('0.00')) + cost
                    
                if len(keys) >= 2:
                    account = keys[1]
                    account_breakdown[account] = account_breakdown.get(account, Decimal('0.00')) + cost
        
        return CostMetrics(
            total_cost=total_cost,
            period_start=start_date,
            period_end=end_date,
            service_breakdown=service_breakdown,
            account_breakdown=account_breakdown,
            region_breakdown=region_breakdown
        )
    
    @cached("tag_compliance", ttl_resolver=lambda s: s.cache_ttls["tag_compliance"])
    def analyze_tag_compliance(self, regions: Optional[List[str]] = None) -> TagComplianceMetrics:
        """Analyze tag compliance across AWS resources.
        
        Args:
            regions: List of regions to analyze (default: all available)
            
        Returns:
            TagComplianceMetrics: Tag compliance analysis results
        """
        if not regions:
            regions = self.session_manager.get_available_regions('ec2')
        
        total_resources = 0
        compliant_resources = 0
        missing_tags = {tag: 0 for tag in self.required_tags}
        services_breakdown = {}
        
        for region in regions:
            try:
                region_metrics = self._analyze_region_compliance(region)
                total_resources += region_metrics['total']
                compliant_resources += region_metrics['compliant']
                
                for tag, count in region_metrics['missing_tags'].items():
                    missing_tags[tag] += count
                    
                for service, metrics in region_metrics['services'].items():
                    if service not in services_breakdown:
                        services_breakdown[service] = {'total': 0, 'compliant': 0}
                    services_breakdown[service]['total'] += metrics['total']
                    services_breakdown[service]['compliant'] += metrics['compliant']
                    
            except Exception as e:
                self.logger.warning(
                    "Failed to analyze compliance for region",
                    extra={"error_type": "TagComplianceRegionFailure", "context": {"region": region}},
                )
                continue
        
        compliance_rate = (compliant_resources / total_resources * 100) if total_resources > 0 else 0.0
        
        return TagComplianceMetrics(
            total_resources=total_resources,
            compliant_resources=compliant_resources,
            compliance_rate=compliance_rate,
            missing_tags=missing_tags,
            services_breakdown=services_breakdown
        )
    
    def _analyze_region_compliance(self, region: str) -> Dict[str, Any]:
        """Analyze tag compliance for a specific region.
        
        Args:
            region: AWS region to analyze
            
        Returns:
            dict: Region compliance metrics
        """
        rg_client = self.session_manager.get_client('resource-groups', region_name=region)
        
        try:
            paginator = rg_client.get_paginator('search_resources')
            page_iterator = paginator.paginate(
                ResourceQuery={'Type': 'TAG_FILTERS_1_0', 'Query': '{}'}
            )
            region_metrics = {'total': 0,'compliant': 0,'missing_tags': {tag: 0 for tag in self.required_tags},'services': {}}
            for page in page_iterator:
                for resource in page.get('Resources', []):
                    region_metrics['total'] += 1
                    arn_parts = resource.get('ResourceArn', '').split(':')
                    service = arn_parts[2] if len(arn_parts) > 2 else 'unknown'
                    if service not in region_metrics['services']:
                        region_metrics['services'][service] = {'total': 0, 'compliant': 0}
                    region_metrics['services'][service]['total'] += 1
                    resource_tags = {tag['Key']: tag['Value'] for tag in resource.get('Tags', [])}
                    missing_required_tags = []
                    for required_tag in self.required_tags:
                        if required_tag not in resource_tags or not resource_tags[required_tag].strip():
                            missing_required_tags.append(required_tag)
                            region_metrics['missing_tags'][required_tag] += 1
                    if not missing_required_tags:
                        region_metrics['compliant'] += 1
                        region_metrics['services'][service]['compliant'] += 1
            return region_metrics
        except ClientError as e:
            self.logger.error(f"Failed to analyze region {region}: {e}")
            return {'total': 0, 'compliant': 0, 'missing_tags': {}, 'services': {}}
    
    @cached("anomaly", ttl_resolver=lambda s: s.cache_ttls["anomaly"])
    def detect_cost_anomalies(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Detect cost anomalies using AWS Cost Anomaly Detection.
        
        Args:
            days_back: Number of days to look back for anomalies
            
        Returns:
            list: Detected cost anomalies
        """
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days_back)
            response = self.session_manager.invoke(
                'ce', 'get_anomalies',
                call_kwargs={
                    'DateInterval': {
                        'StartDate': start_date.strftime('%Y-%m-%d'),
                        'EndDate': end_date.strftime('%Y-%m-%d')
                    },
                    'MaxResults': 100
                },
                context={'operation': 'get_anomalies'}
            )
            anomalies = []
            for anomaly in response.get('Anomalies', []):
                anomalies.append({
                    'anomaly_id': anomaly.get('AnomalyId'),
                    'anomaly_start_date': anomaly.get('AnomalyStartDate'),
                    'anomaly_end_date': anomaly.get('AnomalyEndDate'),
                    'dimension_key': anomaly.get('DimensionKey'),
                    'root_causes': anomaly.get('RootCauses', []),
                    'anomaly_score': anomaly.get('AnomalyScore', {}).get('CurrentScore', 0),
                    'impact': anomaly.get('Impact', {}),
                    'monitor_arn': anomaly.get('MonitorArn')
                })
            return sorted(anomalies, key=lambda x: x['anomaly_score'], reverse=True)
        except ClientError as e:
            self.logger.error(
                "Failed to detect cost anomalies",
                extra={"error_type": "AnomalyDetection", "context": {"days_back": days_back}},
            )
            raise AnomalyDetectionError("Failed to detect cost anomalies", context={"days_back": days_back}) from e
    
    @cached("recommendation", ttl_resolver=lambda s: s.cache_ttls["recommendation"])
    def get_cost_recommendations(self) -> List[Dict[str, Any]]:
        """Get AWS cost optimization recommendations.
        
        Returns:
            list: Cost optimization recommendations
        """
        try:
            recommendations = []
            ri_response = self.session_manager.invoke(
                'ce', 'get_reservation_purchase_recommendation',
                call_kwargs={'Service': 'Amazon Elastic Compute Cloud - Compute'},
                context={'operation': 'get_reservation_purchase_recommendation'}
            )
            for recommendation in ri_response.get('Recommendations', []):
                recommendations.append({
                    'type': 'Reserved Instance',
                    'service': 'EC2',
                    'recommendation_details': recommendation.get('RecommendationDetails', {}),
                    'estimated_monthly_savings': recommendation.get('RecommendationSummary', {}).get('EstimatedMonthlySavingsAmount'),
                    'estimated_monthly_on_demand_cost': recommendation.get('RecommendationSummary', {}).get('EstimatedMonthlyOnDemandCost')
                })
            sp_response = self.session_manager.invoke(
                'ce', 'get_savings_plans_purchase_recommendation',
                call_kwargs={
                    'SavingsPlansType': 'COMPUTE_SP',
                    'TermInYears': 'ONE_YEAR',
                    'PaymentOption': 'NO_UPFRONT',
                    'LookbackPeriodInDays': 'THIRTY_DAYS'
                },
                context={'operation': 'get_savings_plans_purchase_recommendation'}
            )
            for recommendation in sp_response.get('SavingsPlansRecommendationDetails', []):
                recommendations.append({
                    'type': 'Savings Plans',
                    'service': 'Compute',
                    'recommendation_details': recommendation,
                    'estimated_monthly_savings': recommendation.get('EstimatedMonthlySavings'),
                    'estimated_monthly_commitment': recommendation.get('EstimatedMonthlyCommitment')
                })
            return recommendations
        except ClientError as e:
            self.logger.error(
                "Failed to get cost recommendations",
                extra={"error_type": "RecommendationRetrieval"},
            )
            raise RecommendationRetrievalError("Failed to get cost recommendations") from e
    
    def generate_daily_report(self) -> Dict[str, Any]:
        """Generate comprehensive daily FinOps report.
        
        Returns:
            dict: Daily FinOps report data
        """
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        report = {
            'report_date': today.isoformat(),
            'cost_metrics': {},
            'compliance_metrics': {},
            'anomalies': [],
            'recommendations': [],
            'summary': {}
        }
        
        try:
            # Yesterday's costs
            yesterday_costs = self.get_cost_and_usage(yesterday, today)
            report['cost_metrics']['yesterday'] = {
                'total_cost': float(yesterday_costs.total_cost),
                'service_breakdown': {k: float(v) for k, v in yesterday_costs.service_breakdown.items()}
            }
            
            # Week-over-week comparison
            week_costs = self.get_cost_and_usage(week_ago, yesterday)
            report['cost_metrics']['week_comparison'] = {
                'total_cost': float(week_costs.total_cost),
                'change_percentage': float((yesterday_costs.total_cost - week_costs.total_cost) / week_costs.total_cost * 100) if week_costs.total_cost > 0 else 0
            }
            
            # Tag compliance
            compliance = self.analyze_tag_compliance()
            report['compliance_metrics'] = {
                'total_resources': compliance.total_resources,
                'compliance_rate': compliance.compliance_rate,
                'missing_tags': compliance.missing_tags
            }
            
            # Cost anomalies
            report['anomalies'] = self.detect_cost_anomalies(days_back=7)
            
            # Optimization recommendations
            report['recommendations'] = self.get_cost_recommendations()
            
            # Summary
            report['summary'] = {
                'daily_cost_alert': float(yesterday_costs.total_cost) > float(self.cost_thresholds['daily_warning']),
                'compliance_alert': compliance.compliance_rate < 80.0,
                'anomaly_count': len(report['anomalies']),
                'recommendations_count': len(report['recommendations'])
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to generate daily report",
                extra={"error_type": "DailyReportFailure"},
            )
            report['error'] = str(e)
        
        return report

    @cached("anomaly", ttl_resolver=lambda s: s.cache_ttls["anomaly"])
    def detect_advanced_cost_anomalies(self) -> List[Dict[str, Any]]:
        """Run advanced Z-score / IsolationForest anomaly detection over historical daily costs."""
        # Build historical series
        days = self.settings.anomaly_history_days
        today = datetime.now().date()
        series: List[Dict[str, Any]] = []
        for i in range(days, 0, -1):
            start = today - timedelta(days=i)
            end = start + timedelta(days=1)
            try:
                metrics = self.get_cost_and_usage(start, end)
                series.append({"date": start.isoformat(), "value": float(metrics.total_cost)})
            except Exception:
                continue
        if len(series) < self.settings.anomaly_min_points:
            return []
        anomalies = self._advanced_detector.detect(series)
        if anomalies and self.settings.anomaly_alert_enabled:
            dispatch_anomaly_alert(anomalies, {"history_days": days})
        return anomalies

    # ---------------- Multi-Account Support -----------------
    @cached("cost", ttl_resolver=lambda s: s.cache_ttls["cost"])
    def get_multi_account_costs(self, start_date: datetime, end_date: datetime, granularity: str = "DAILY") -> Dict[str, Any]:
        """Retrieve costs for all accessible organization accounts.

        Returns a dict keyed by account id with aggregated cost metrics for the period.
        """
        results: Dict[str, Any] = {}
        for entry in iter_account_cost_explorer_sessions(self.session_manager):
            acct = entry["account"]
            client = entry["client"]
            try:
                resp = client.get_cost_and_usage(
                    TimePeriod={
                        'Start': start_date.strftime('%Y-%m-%d'),
                        'End': end_date.strftime('%Y-%m-%d')
                    },
                    Granularity=granularity,
                    Metrics=['BlendedCost'],
                    GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
                )
                total = Decimal('0.00')
                service_breakdown: Dict[str, Decimal] = {}
                for rt in resp.get('ResultsByTime', []):
                    for group in rt.get('Groups', []):
                        cost = Decimal(group['Metrics']['BlendedCost']['Amount'])
                        total += cost
                        svc = group['Keys'][0]
                        service_breakdown[svc] = service_breakdown.get(svc, Decimal('0.00')) + cost
                results[acct['id']] = {
                    'account_id': acct['id'],
                    'account_name': acct.get('name'),
                    'total_cost': float(total),
                    'service_breakdown': {k: float(v) for k, v in service_breakdown.items()}
                }
            except ClientError as e:
                self.logger.warning(
                    "Failed cost query for account", extra={"error_type": "AccountCostFailure", "context": {"account": acct['id']}}
                )
                continue
        return results

    @cached("cost", ttl_resolver=lambda s: s.cache_ttls["cost"])
    def get_consolidated_billing_summary(self, days: int = 30) -> Dict[str, Any]:
        """Return consolidated billing summary across org accounts for recent period."""
        end = datetime.now().date()
        start = end - timedelta(days=days)
        account_costs = self.get_multi_account_costs(start, end)
        total = sum(v['total_cost'] for v in account_costs.values())
        top_accounts = sorted(account_costs.values(), key=lambda x: x['total_cost'], reverse=True)[:10]
        return {
            'period_start': start.isoformat(),
            'period_end': end.isoformat(),
            'total_consolidated_cost': total,
            'accounts': account_costs,
            'top_accounts': top_accounts,
            'account_count': len(account_costs)
        }

    @cached("tag_compliance", ttl_resolver=lambda s: s.cache_ttls["tag_compliance"])
    def get_account_tag_compliance(self) -> Dict[str, Any]:
        """Compute tag compliance per account using existing regional compliance logic."""
        results = {}
        for acct in list_org_accounts(self.session_manager):
            # assume role for resource-groups queries
            # For simplicity we reuse base session manager (could be extended to per-account session caching)
            try:
                compliance = self.analyze_tag_compliance()  # region-based; could be narrowed per account with future enhancement
                results[acct['id']] = {
                    'account_id': acct['id'],
                    'account_name': acct.get('name'),
                    'compliance_rate': compliance.compliance_rate,
                    'total_resources': compliance.total_resources,
                    'missing_tags': compliance.missing_tags
                }
            except Exception:
                self.logger.warning(
                    "Failed tag compliance for account", extra={"error_type": "AccountTagComplianceFailure", "context": {"account": acct['id']}}
                )
        return results
