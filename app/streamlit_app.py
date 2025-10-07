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

# Import handling: when executed via `streamlit run app/streamlit_app.py` the file is
# treated as a top-level script so relative imports (".") fail. Use absolute
# package imports instead so it works both as a module and as a script.
from app.aws_session import AWSSessionManager, AWSSessionError  # type: ignore
from app.finops import FinOpsAnalyzer  # type: ignore
from app.export import generate_report  # type: ignore


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


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_finops_data():
    """Load and cache FinOps data."""
    try:
        session_manager = AWSSessionManager()
        finops = FinOpsAnalyzer(session_manager)
        
        # Validate AWS permissions
        permissions = session_manager.validate_permissions()
        
        if not permissions['cost_explorer']:
            st.error("❌ AWS Cost Explorer access required. Please check your IAM permissions.")
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


def render_sidebar():
    """Render sidebar with navigation and filters."""
    st.sidebar.title("🏗️ AWS FinOps Dashboard")
    
    # Navigation
    page = st.sidebar.selectbox(
        "📊 Dashboard Pages",
        ["Overview", "Cost Analysis", "Tag Compliance", "Anomalies", "Recommendations", "Reports", "Health"]
    )
    
    st.sidebar.markdown("---")
    
    # Date range selector
    st.sidebar.subheader("📅 Time Period")
    
    date_range = st.sidebar.selectbox(
        "Select Range",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Custom"]
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
    
    # Service filter
    services = st.sidebar.multiselect(
        "AWS Services",
        ["Amazon EC2", "Amazon S3", "Amazon RDS", "AWS Lambda", "Amazon ECS", "All"],
        default=["All"]
    )
    
    # Account filter (if multi-account)
    accounts = st.sidebar.multiselect(
        "AWS Accounts",
        ["Production", "Staging", "Development", "All"],
        default=["All"]
    )
    
    return page, start_date, end_date, services, accounts


def render_overview_page(finops: FinOpsAnalyzer, start_date: datetime, end_date: datetime):
    """Render overview dashboard page."""
    st.title("📊 AWS FinOps Overview")
    
    # Get daily report data
    with st.spinner("Loading FinOps data..."):
        report = finops.generate_daily_report()
    
    if 'error' in report:
        st.error(f"❌ Failed to load data: {report['error']}")
        return
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        yesterday_cost = report['cost_metrics'].get('yesterday', {}).get('total_cost', 0)
        st.metric(
            "💸 Yesterday's Cost",
            f"${yesterday_cost:.2f}",
            delta=f"{report['cost_metrics'].get('week_comparison', {}).get('change_percentage', 0):.1f}%"
        )
    
    with col2:
        compliance_rate = report['compliance_metrics'].get('compliance_rate', 0)
        st.metric(
            "🏷️ Tag Compliance",
            f"{compliance_rate:.1f}%",
            delta=f"{100 - compliance_rate:.1f}% to target" if compliance_rate < 100 else "✅ Target met"
        )
    
    with col3:
        anomaly_count = report['summary'].get('anomaly_count', 0)
        st.metric(
            "🚨 Cost Anomalies",
            str(anomaly_count),
            delta="Detected this week"
        )
    
    with col4:
        rec_count = report['summary'].get('recommendations_count', 0)
        st.metric(
            "💡 Recommendations",
            str(rec_count),
            delta="Available"
        )
    
    # Charts row
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Cost Trend (Last 7 Days)")
        
        # Mock trend data for demonstration
        dates = [datetime.now().date() - timedelta(days=i) for i in range(7, 0, -1)]
        costs = [yesterday_cost * (0.8 + 0.4 * (i % 3) / 2) for i in range(7)]
        
        trend_df = pd.DataFrame({
            'Date': dates,
            'Cost': costs
        })
        
        fig = px.line(trend_df, x='Date', y='Cost', 
                     title="Daily AWS Costs",
                     line_shape='spline')
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("🎯 Service Cost Breakdown")
        
        service_data = report['cost_metrics'].get('yesterday', {}).get('service_breakdown', {})
        if service_data:
            services_df = pd.DataFrame([
                {'Service': k, 'Cost': v} for k, v in service_data.items()
            ]).sort_values('Cost', ascending=False).head(10)
            
            fig = px.pie(services_df, values='Cost', names='Service',
                        title="Top 10 Services by Cost")
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No service breakdown data available")
    
    # Alerts section
    st.subheader("🚨 Active Alerts")
    
    alerts = []
    if report['summary'].get('daily_cost_alert'):
        alerts.append({"type": "warning", "message": "Daily cost threshold exceeded"})
    if report['summary'].get('compliance_alert'):
        alerts.append({"type": "error", "message": "Tag compliance below 80%"})
    if anomaly_count > 0:
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
        strategy = diag.get("auth_strategy")
        color = {
            "assume_role": "green" if (diag.get("base_chain_has_credentials") or diag.get("has_static_keys")) else "red",
            "static_keys": "green" if diag.get("has_static_keys") else "red",
            "default_chain": "green" if diag.get("base_chain_has_credentials") else "red",
            "none": "red"
        }.get(strategy, "red")
        st.markdown(f"**Auth Strategy:** <span style='color:{color}'>{strategy}</span>", unsafe_allow_html=True)
        st.json({k: v for k, v in diag.items() if k != "remediation"})
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
    """Main Streamlit application."""
    # Initialize FinOps analyzer
    finops = load_finops_data()
    
    if finops is None:
        st.stop()
    
    # Render sidebar and get selections
    page, start_date, end_date, services, accounts = render_sidebar()
    
    # Convert dates to datetime objects
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.min.time())
    
    # Render selected page
    if page == "Overview":
        render_overview_page(finops, start_datetime, end_datetime)
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
        # Health page can show even if finops failed earlier, but here finops exists.
        render_health_page()
    
    # Footer
    st.markdown("---")
    st.markdown("**AWS FinOps Dashboard** - Built with ❤️ using Streamlit and AWS APIs")


if __name__ == "__main__":
    main()
