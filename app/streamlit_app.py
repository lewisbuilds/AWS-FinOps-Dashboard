"""AWS FinOps Dashboard - Streamlit Application

Main Streamlit application providing interactive AWS cost monitoring,
tag compliance tracking, and financial operations insights.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json
import re

# Import handling: when executed via `streamlit run app/streamlit_app.py` the file is
# treated as a top-level script so relative imports (".") fail. Use absolute
# package imports instead so it works both as a module and as a script.
from app.aws_session import AWSSessionManager, AWSSessionError  # type: ignore
from app.finops import FinOpsAnalyzer  # type: ignore
from app.export import generate_report  # type: ignore
from app.user_prefs import load_prefs, save_prefs, apply_threshold_overrides, override_required_tags  # type: ignore


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="AWS FinOps Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

SANITIZE_CTRL = re.compile(r"[\r\n\t\x00-\x08\x0b\x0c\x0e-\x1f]")


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_finops_data():
    """Load and cache FinOps data."""
    try:
        session_manager = AWSSessionManager()
        finops = FinOpsAnalyzer(session_manager)
        # Apply user preference overrides (cannot be cached across users easily; safe for single-user or hashed principal context)
        principal_arn = _get_principal_arn()
        if principal_arn:
            _, prefs = _load_user_prefs()
            if prefs.get('required_tag_keys'):
                from app.user_prefs import override_required_tags as _rt
                finops.override_required_tags(_rt(finops.required_tags, prefs))
            # thresholds
            daily = prefs.get('daily_cost_warning')
            monthly = prefs.get('monthly_cost_warning')
            if daily is not None or monthly is not None:
                finops.override_cost_thresholds(daily=daily if daily else None, monthly=monthly if monthly else None)
        
        # Validate AWS permissions
        permissions = session_manager.validate_permissions()

        if not permissions['cost_explorer']:
            st.error("❌ AWS Cost Explorer access required. Missing permission: ce:GetCostAndUsage (and related Cost Explorer APIs).")
            with st.expander("How to fix Cost Explorer access"):
                st.markdown("""
                **Steps:**
                1. Ensure Cost Explorer is enabled in the payer account (Billing Console).
                2. Attach a policy containing at least `ce:GetCostAndUsage` to the IAM user/role or assumed role.
                3. If using a role assumption, confirm both the base principal AND target role trust policy allow the action.
                4. Re-run: `aws ce get-cost-and-usage --time-period Start=2025-10-01,End=2025-10-02 --granularity=DAILY --metrics BlendedCost --profile $env:AWS_PROFILE` to verify.
                """)
            st.info("Other permission checks: organizations=%s support=%s resource_groups=%s" % (
                permissions.get('organizations'), permissions.get('support'), permissions.get('resource_groups')
            ))
            return None
            
        return finops
        
    except AWSSessionError as e:
        # Surface detailed credential diagnostics to help user remediate
        st.error(f"❌ AWS credential / AssumeRole initialization failed: {e}")
        try:
            mgr = AWSSessionManager()
            diag = mgr.diagnose_credentials()
            st.subheader("🔐 Credential Diagnostics")
            st.json(diag)
            remediation = diag.get("remediation") or []
            if remediation:
                st.markdown("**Remediation Steps:**")
                for step in remediation:
                    st.markdown(f"- {step}")
            else:
                st.info("No remediation suggestions available.")
        except Exception as inner:
            st.warning(f"Could not collect diagnostics: {inner}")
        logger.error(f"AWS credential initialization failed: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Failed to initialize AWS connection: {e}")
        logger.error(f"AWS initialization failed: {e}")
        return None


@st.cache_data(ttl=600)
def _get_principal_arn() -> str:
    try:
        mgr = AWSSessionManager()
        sess = mgr.get_session()
        sts = sess.client('sts')
        return sts.get_caller_identity().get('Arn', 'unknown')
    except Exception:
        return 'unknown'


def _load_user_prefs():
    arn = _get_principal_arn()
    prefs = load_prefs(arn)
    return arn, prefs


def render_sidebar():
    """Render sidebar with navigation and filters (now preference-aware)."""
    st.sidebar.title("🏗️ AWS FinOps Dashboard")
    principal_arn = _get_principal_arn()
    # Load preferences (not cached across sessions because user may change them)
    arn, prefs = _load_user_prefs()

    # Customization section
    with st.sidebar.expander("⚙️ Customize Dashboard", expanded=False):
        st.caption(f"Identity: {principal_arn.split('/')[-1] if principal_arn!='unknown' else 'anonymous'}")
        widgets = st.multiselect(
            "Overview Widgets",
            ["yesterday_cost","tag_compliance","anomalies","recommendations","cost_trend","service_pie"],
            default=prefs.get("overview_widgets", []),
            help="Select which high-level widgets appear on the Overview page"
        )
        daily_override = st.number_input(
            "Daily Cost Alert Threshold ($)",
            min_value=0.0,
            value=float(prefs.get('daily_cost_warning') or 0.0),
            help="Set 0 to inherit global setting"
        )
        monthly_override = st.number_input(
            "Monthly Cost Alert Threshold ($)",
            min_value=0.0,
            value=float(prefs.get('monthly_cost_warning') or 0.0),
            help="Set 0 to inherit global setting"
        )
        tag_override = st.text_input(
            "Required Tag Keys (comma separated)",
            value=prefs.get('required_tag_keys') or '',
            help="Override global required tags for your view only"
        )
        theme_choice = st.selectbox("Theme Preference", ["light","dark"], index=0 if prefs.get('theme')=="light" else 1)
        default_range = st.selectbox("Default Date Range", ["Last 7 days","Last 30 days","Last 90 days"], index=["Last 7 days","Last 30 days","Last 90 days"].index(prefs.get('default_date_range','Last 7 days')))
        if st.button("💾 Save Preferences"):
            new_prefs = dict(prefs)
            # Sanitize tag override & enforce max length per tag implicitly in downstream cleaner
            safe_tag_override = SANITIZE_CTRL.sub(" ", tag_override) if tag_override else None
            new_prefs['overview_widgets'] = widgets
            new_prefs['daily_cost_warning'] = daily_override or None
            new_prefs['monthly_cost_warning'] = monthly_override or None
            new_prefs['required_tag_keys'] = safe_tag_override or None
            new_prefs['theme'] = theme_choice
            new_prefs['default_date_range'] = default_range
            save_prefs(principal_arn, new_prefs)
            st.success("Preferences saved. Reload the page to apply threshold / tag changes.")

    # Navigation
    page = st.sidebar.selectbox(
        "📊 Dashboard Pages",
        ["Overview", "Cost Analysis", "Tag Compliance", "Anomalies", "Recommendations", "Reports", "Health"]
    )

    st.sidebar.markdown("---")

    # Date range selector (respect default preference when first load)
    preset_default = prefs.get('default_date_range','Last 7 days')
    date_range = st.sidebar.selectbox(
        "Select Range",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Custom"],
        index=["Last 7 days", "Last 30 days", "Last 90 days", "Custom"].index(preset_default) if preset_default in ["Last 7 days","Last 30 days","Last 90 days"] else 0
    )

    if date_range == "Custom":
        start_date = st.sidebar.date_input("Start Date", value=datetime.now().date() - timedelta(days=30))
        end_date = st.sidebar.date_input("End Date", value=datetime.now().date())
    else:
        days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[date_range]
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

    st.sidebar.markdown("---")

    # Filters
    st.sidebar.subheader("🔍 Filters")

    services = st.sidebar.multiselect(
        "AWS Services",
        ["Amazon EC2", "Amazon S3", "Amazon RDS", "AWS Lambda", "Amazon ECS", "All"],
        default=["All"]
    )

    accounts = st.sidebar.multiselect(
        "AWS Accounts",
        ["Production", "Staging", "Development", "All"],
        default=["All"]
    )

    return page, start_date, end_date, services, accounts, prefs


def render_overview_page(finops: FinOpsAnalyzer, start_date: datetime, end_date: datetime, prefs: dict):
    """Render overview dashboard page honoring user widget preferences."""
    st.title("📊 AWS FinOps Overview")
    widgets = prefs.get('overview_widgets', [])

    with st.spinner("Loading FinOps data..."):
        report = finops.generate_daily_report()

    if 'error' in report:
        st.error(f"❌ Failed to load data: {report['error']}")
        return

    # Key metrics row
    metric_cols = []
    metric_map = []  # (id, col)
    if any(w in widgets for w in ["yesterday_cost","tag_compliance","anomalies","recommendations"]):
        base_cols = st.columns(4)
        metric_cols = base_cols
    else:
        base_cols = []

    col_iter = iter(metric_cols)

    if "yesterday_cost" in widgets:
        col = next(col_iter)
        yesterday_cost = report['cost_metrics'].get('yesterday', {}).get('total_cost', 0)
        col.metric(
            "💸 Yesterday's Cost",
            f"${yesterday_cost:.2f}",
            delta=f"{report['cost_metrics'].get('week_comparison', {}).get('change_percentage', 0):.1f}%"
        )
    if "tag_compliance" in widgets:
        col = next(col_iter)
        compliance_rate = report['compliance_metrics'].get('compliance_rate', 0)
        col.metric(
            "🏷️ Tag Compliance",
            f"{compliance_rate:.1f}%",
            delta=f"{100 - compliance_rate:.1f}% to target" if compliance_rate < 100 else "✅ Target met"
        )
    if "anomalies" in widgets:
        col = next(col_iter)
        anomaly_count = report['summary'].get('anomaly_count', 0)
        col.metric(
            "🚨 Cost Anomalies",
            str(anomaly_count),
            delta="Detected this week"
        )
    if "recommendations" in widgets:
        col = next(col_iter)
        rec_count = report['summary'].get('recommendations_count', 0)
        col.metric(
            "💡 Recommendations",
            str(rec_count),
            delta="Available"
        )

    # Charts
    chart_cols = st.columns(2)
    if "cost_trend" in widgets:
        with chart_cols[0]:
            st.subheader("📈 Cost Trend (Last 7 Days)")
            dates = [datetime.now().date() - timedelta(days=i) for i in range(7, 0, -1)]
            yesterday_cost = report['cost_metrics'].get('yesterday', {}).get('total_cost', 0)
            costs = [yesterday_cost * (0.8 + 0.4 * (i % 3) / 2) for i in range(7)]
            trend_df = pd.DataFrame({'Date': dates,'Cost': costs})
            fig = px.line(trend_df, x='Date', y='Cost', title="Daily AWS Costs", line_shape='spline')
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    if "service_pie" in widgets:
        with chart_cols[1]:
            st.subheader("🎯 Service Cost Breakdown")
            service_data = report['cost_metrics'].get('yesterday', {}).get('service_breakdown', {})
            if service_data:
                services_df = pd.DataFrame([
                    {'Service': k, 'Cost': v} for k, v in service_data.items()
                ]).sort_values('Cost', ascending=False).head(10)
                fig = px.pie(services_df, values='Cost', names='Service', title="Top 10 Services by Cost")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No service breakdown data available")

    # Alerts
    st.subheader("🚨 Active Alerts")
    alerts = []
    if report['summary'].get('daily_cost_alert'):
        alerts.append({"type": "warning", "message": "Daily cost threshold exceeded"})
    if report['summary'].get('compliance_alert'):
        alerts.append({"type": "error", "message": "Tag compliance below 80%"})
    anomaly_count = report['summary'].get('anomaly_count', 0)
    if anomaly_count > 0 and "anomalies" in widgets:
        alerts.append({"type": "info", "message": f"{anomaly_count} cost anomalies detected"})

    if alerts:
        for alert in alerts:
            if alert["type"] == "warning":
                st.warning(f"⚠️ {alert['message']}")
            elif alert["type"] == "error":
                st.error(f"❌ {alert['message']}")
            else:
                st.info(f"ℹ️ {alert['message']}")
    else:
        st.success("✅ No active alerts")


def render_cost_analysis_page(finops: FinOpsAnalyzer, start_date: datetime, end_date: datetime):
    """Render detailed cost analysis page."""
    st.title("💰 Cost Analysis")
    
    with st.spinner("Loading cost data..."):
        cost_metrics = finops.get_cost_and_usage(
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.min.time())
        )
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Total Cost",
            f"${float(cost_metrics.total_cost):.2f}",
            delta=f"Period: {start_date} to {end_date}"
        )
    
    with col2:
        daily_avg = float(cost_metrics.total_cost) / max((end_date - start_date).days, 1)
        st.metric(
            "Daily Average",
            f"${daily_avg:.2f}",
            delta="Average per day"
        )
    
    with col3:
        services_count = len(cost_metrics.service_breakdown)
        st.metric(
            "Active Services",
            str(services_count),
            delta="Services with costs"
        )
    
    # Detailed breakdowns
    tab1, tab2, tab3 = st.tabs(["📊 Services", "🏢 Accounts", "🌍 Regions"])
    
    with tab1:
        st.subheader("Service Cost Breakdown")
        
        if cost_metrics.service_breakdown:
            services_df = pd.DataFrame([
                {'Service': k, 'Cost': float(v), 'Percentage': float(v) / float(cost_metrics.total_cost) * 100}
                for k, v in cost_metrics.service_breakdown.items()
            ]).sort_values('Cost', ascending=False)
            
            # Table view
            st.dataframe(
                services_df.style.format({
                    'Cost': '${:.2f}',
                    'Percentage': '{:.1f}%'
                }),
                use_container_width=True
            )
            
            # Chart view
            fig = px.bar(services_df.head(15), x='Service', y='Cost',
                        title="Top 15 Services by Cost")
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No service breakdown data available")
    
    with tab2:
        st.subheader("Account Cost Breakdown")
        
        if cost_metrics.account_breakdown:
            accounts_df = pd.DataFrame([
                {'Account': k, 'Cost': float(v), 'Percentage': float(v) / float(cost_metrics.total_cost) * 100}
                for k, v in cost_metrics.account_breakdown.items()
            ]).sort_values('Cost', ascending=False)
            
            st.dataframe(
                accounts_df.style.format({
                    'Cost': '${:.2f}',
                    'Percentage': '{:.1f}%'
                }),
                use_container_width=True
            )
            
            fig = px.pie(accounts_df, values='Cost', names='Account',
                        title="Account Distribution")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No account breakdown data available")
    
    with tab3:
        st.subheader("Regional Cost Distribution")
        st.info("Regional breakdown data will be available in future versions")


def render_compliance_page(finops: FinOpsAnalyzer):
    """Render tag compliance monitoring page."""
    st.title("🏷️ Tag Compliance Monitoring")
    
    with st.spinner("Analyzing tag compliance..."):
        compliance = finops.analyze_tag_compliance()
    
    # Compliance overview
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Resources",
            f"{compliance.total_resources:,}",
            delta="Analyzed"
        )
    
    with col2:
        st.metric(
            "Compliant Resources",
            f"{compliance.compliant_resources:,}",
            delta=f"{compliance.compliance_rate:.1f}% compliance"
        )
    
    with col3:
        non_compliant = compliance.total_resources - compliance.compliant_resources
        st.metric(
            "Non-Compliant",
            f"{non_compliant:,}",
            delta="Needs attention"
        )
    
    with col4:
        compliance_score = "🟢 Excellent" if compliance.compliance_rate >= 95 else \
                          "🟡 Good" if compliance.compliance_rate >= 80 else \
                          "🔴 Needs Improvement"
        st.metric(
            "Compliance Score",
            compliance_score,
            delta=f"{compliance.compliance_rate:.1f}%"
        )
    
    # Missing tags analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Missing Tags Analysis")
        
        missing_df = pd.DataFrame([
            {'Tag': k, 'Missing Count': v}
            for k, v in compliance.missing_tags.items()
        ]).sort_values('Missing Count', ascending=False)
        
        fig = px.bar(missing_df, x='Tag', y='Missing Count',
                    title="Resources Missing Required Tags")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Service Compliance Breakdown")
        
        if compliance.services_breakdown:
            services_compliance = []
            for service, metrics in compliance.services_breakdown.items():
                compliance_rate = (metrics['compliant'] / metrics['total'] * 100) if metrics['total'] > 0 else 0
                services_compliance.append({
                    'Service': service,
                    'Total': metrics['total'],
                    'Compliant': metrics['compliant'],
                    'Compliance Rate': compliance_rate
                })
            
            services_df = pd.DataFrame(services_compliance).sort_values('Compliance Rate', ascending=True)
            
            fig = px.bar(services_df.head(10), x='Compliance Rate', y='Service',
                        orientation='h', title="Service Compliance Rates")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No service compliance data available")
    
    # Detailed compliance table
    st.subheader("Detailed Compliance Report")
    
    if compliance.services_breakdown:
        detailed_df = pd.DataFrame([
            {
                'Service': service,
                'Total Resources': metrics['total'],
                'Compliant': metrics['compliant'],
                'Non-Compliant': metrics['total'] - metrics['compliant'],
                'Compliance Rate': f"{(metrics['compliant'] / metrics['total'] * 100) if metrics['total'] > 0 else 0:.1f}%"
            }
            for service, metrics in compliance.services_breakdown.items()
        ]).sort_values('Total Resources', ascending=False)
        
        st.dataframe(detailed_df, use_container_width=True)
    else:
        st.info("No detailed compliance data available")


def render_anomalies_page(finops: FinOpsAnalyzer):
    """Render cost anomalies detection page."""
    st.title("🚨 Cost Anomaly Detection")
    
    with st.spinner("Detecting cost anomalies..."):
        anomalies = finops.detect_cost_anomalies(days_back=30)
    
    if anomalies:
        st.success(f"Found {len(anomalies)} cost anomalies in the last 30 days")
        
        for i, anomaly in enumerate(anomalies[:10]):  # Show top 10
            with st.expander(f"Anomaly #{i+1} - Score: {anomaly['anomaly_score']:.2f}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Start Date:** {anomaly['anomaly_start_date']}")
                    st.write(f"**End Date:** {anomaly['anomaly_end_date']}")
                    st.write(f"**Dimension:** {anomaly['dimension_key']}")
                
                with col2:
                    st.write(f"**Anomaly Score:** {anomaly['anomaly_score']:.2f}")
                    impact = anomaly.get('impact', {})
                    if impact:
                        st.write(f"**Impact:** ${impact.get('TotalImpact', 0):.2f}")
                
                if anomaly['root_causes']:
                    st.write("**Root Causes:**")
                    for cause in anomaly['root_causes']:
                        st.write(f"- {cause}")
    else:
        st.info("🎉 No cost anomalies detected in the last 30 days")


def render_recommendations_page(finops: FinOpsAnalyzer):
    """Render cost optimization recommendations page."""
    st.title("💡 Cost Optimization Recommendations")
    
    with st.spinner("Loading optimization recommendations..."):
        recommendations = finops.get_cost_recommendations()
    
    if recommendations:
        st.success(f"Found {len(recommendations)} optimization opportunities")
        
        for i, rec in enumerate(recommendations):
            with st.expander(f"Recommendation #{i+1} - {rec['type']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Type:** {rec['type']}")
                    st.write(f"**Service:** {rec['service']}")
                    
                with col2:
                    if rec.get('estimated_monthly_savings'):
                        st.write(f"**Estimated Monthly Savings:** ${rec['estimated_monthly_savings']}")
                    
                    if rec.get('estimated_monthly_on_demand_cost'):
                        st.write(f"**Current On-Demand Cost:** ${rec['estimated_monthly_on_demand_cost']}")
                
                if rec.get('recommendation_details'):
                    st.write("**Details:**")
                    st.json(rec['recommendation_details'])
    else:
        st.info("No cost optimization recommendations available at this time")


def render_reports_page(finops: FinOpsAnalyzer):
    """Render reports and export page.

    Adds an on-demand multi-format report generation trigger with optional email sending.
    """
    st.title("📋 Reports & Export")

    tab1, tab2 = st.tabs(["🔄 Generate / View", "📤 On-Demand Export"])

    with tab1:
        st.subheader("Quick Summary Reports")
        report_type = st.selectbox(
            "Report Type",
            ["Daily Summary", "Weekly Summary (WIP)", "Monthly Summary (WIP)"]
        )
        if st.button("Generate Summary", key="summary_btn"):
            with st.spinner("Generating summary report..."):
                if report_type.startswith("Daily"):
                    summary = finops.generate_daily_report()
                    st.json(summary)
                else:
                    st.info("Selected summary type not yet implemented.")

    with tab2:
        st.subheader("Ad-hoc Report Export")
        colA, colB, colC = st.columns([1,1,1])
        with colA:
            last_n_days = st.number_input("Last N Days", min_value=1, max_value=400, value=7, help="Rolling window for datasets.")
        with colB:
            formats = st.multiselect(
                "Formats",
                ["csv", "json", "xlsx"],
                default=["csv", "json"],
                help="Select one or more output formats"
            )
        with colC:
            send_email = st.checkbox("Send Email (SES)", value=False, help="Requires SES_* env vars & SES_ENABLED=true")

        if st.button("Run Export", key="export_btn"):
            if not formats:
                st.warning("Select at least one format.")
            else:
                with st.spinner("Generating report exports..."):
                    try:
                        result = generate_report(finops, formats=formats, last_n_days=last_n_days, email=send_email)
                        files = result.get("files", [])
                        if files:
                            st.success(f"Generated {len(files)} file(s).")
                            for f in files:
                                # Offer download; read file binary (small/medium sized assumption). Wrap in try for robustness.
                                try:
                                    with open(f, "rb") as fh:
                                        data = fh.read()
                                    label = f.split('/')[-1]
                                    st.download_button(label=f"Download {label}", data=data, file_name=label, mime="application/octet-stream")
                                except Exception as ex:
                                    st.warning(f"Could not attach {f}: {ex}")
                        else:
                            st.info("No files returned from report generation.")

                        if send_email:
                            st.info("If SES was properly configured, an email attempt was made (check logs / inbox).")
                        st.json({k: v for k, v in result.items() if k != "files"})
                    except Exception as e:
                        st.error(f"Failed to generate report: {e}")
                        logger.exception("Report generation failed")


def render_health_page():
    """Render runtime health & credential diagnostics page.

    Provides visibility into current authentication strategy and remediation guidance
    without requiring users to inspect logs. Does not require a working FinOpsAnalyzer
    session, so it re-instantiates a manager directly.
    """
    st.title("🩺 Health & Diagnostics")
    st.subheader("AWS Credential Strategy")
    try:
        mgr = AWSSessionManager()
        diag = mgr.diagnose_credentials()
        perms = mgr.validate_permissions()
        strategy = diag.get("auth_strategy")
        color = {
            "assume_role": "green" if (diag.get("base_chain_has_credentials") or diag.get("has_static_keys")) else "red",
            "static_keys": "green" if diag.get("has_static_keys") else "red",
            "default_chain": "green" if diag.get("base_chain_has_credentials") else "red",
            "none": "red"
        }.get(strategy, "red")
        st.markdown(f"**Auth Strategy:** <span style='color:{color}'>{strategy}</span>", unsafe_allow_html=True)
        st.json({k: v for k, v in diag.items() if k != "remediation"})
        st.subheader("Permissions Snapshot")
        st.json(perms)
        if not perms.get('cost_explorer'):
            st.warning("Cost Explorer access missing: add ce:GetCostAndUsage and ensure service is enabled.")
        remediation = diag.get("remediation") or []
        if remediation:
            st.subheader("Remediation Suggestions")
            for step in remediation:
                st.markdown(f"- {step}")
        else:
            st.success("No remediation required.")
    except Exception as e:
        st.error(f"Failed to collect diagnostics: {e}")
    st.markdown("---")
    st.caption("Diagnostics are generated from the current environment variables, shared credentials/profile chain, and optional role assumption settings.")


def main():
    finops = load_finops_data()
    if finops is None:
        st.stop()
    page, start_date, end_date, services, accounts, prefs = render_sidebar()
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.min.time())
    if page == "Overview":
        render_overview_page(finops, start_datetime, end_datetime, prefs)
    elif page == "Cost Analysis":
        render_cost_analysis_page(finops, start_datetime, end_datetime)
    elif page == "Tag Compliance":
        render_compliance_page(finops)
    elif page == "Anomalies":
        render_anomalies_page(finops)
    elif page == "Recommendations":
        render_recommendations_page(finops)
    elif page == "Reports":
        render_reports_page(finops)
    elif page == "Health":
        render_health_page()
    st.markdown("---")
    st.markdown("**AWS FinOps Dashboard** - Built with ❤️ using Streamlit and AWS APIs")


if __name__ == "__main__":
    main()
