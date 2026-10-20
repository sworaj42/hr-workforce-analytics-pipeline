"""
HR dashboard on the gold KPI views.

Run from the project root: PYTHONPATH=. streamlit run dashboard/app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from pipeline.db import get_connection


@st.cache_data(ttl=600)
def load(view):
    conn = get_connection()
    try:
        return pd.read_sql(f"SELECT * FROM gold.{view}", conn)
    finally:
        conn.close()


def date_filter(key, first, last):
    return st.slider("Date range", min_value=first, max_value=last,
                     value=(first, last), format="YYYY-MM-DD", key=key)


CARDS_NOTE = "Cards cover the full data period and are not affected by the date range."

st.set_page_config(page_title="HR Workforce Dashboard", layout="wide")
st.title("HR Workforce Dashboard")

workforce_tab, hours_tab, attendance_tab = st.tabs(
    ["Workforce", "Working hours", "Attendance"]
)

with workforce_tab:
    headcount = load("kpi_active_headcount").sort_values("as_of_date")
    turnover = load("kpi_turnover_trend").sort_values("month")
    tenure = load("kpi_avg_tenure_by_department")
    attrition = load("kpi_early_attrition_rate")

    last_day = headcount["as_of_date"].iloc[-1]
    first_month = turnover["month"].iloc[0]
    last_month = turnover["month"].iloc[-1]
    # Weighted by employees, so big departments count more
    avg_tenure = (tenure["avg_tenure_years"] * tenure["employees"]).sum() / tenure["employees"].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"Headcount on {last_day:%d %b %Y}", headcount["active_count"].iloc[-1])
    col2.metric(f"Terminations ({first_month:%b %Y} – {last_month:%b %Y})",
                turnover["terminations"].sum())
    col3.metric("Average tenure, years (all employees on file)", f"{avg_tenure:.1f}")
    col4.metric("Early attrition, 90 days (all employees)",
                f"{attrition['early_attrition_rate_pct'].iloc[0]}%")
    st.caption(CARDS_NOTE)

    # A one-person department average is just that person's tenure
    shared = tenure[tenure["employees"] >= 2]
    st.plotly_chart(px.bar(
        shared.sort_values("avg_tenure_years"), x="avg_tenure_years",
        y="department_name", orientation="h", hover_data=["employees"],
        title="Average tenure by department (2 or more employees)",
        labels={"avg_tenure_years": "Years", "department_name": "Department",
                "employees": "Employees"},
    ))
    st.caption(f"Static snapshot on {last_day:%d %b %Y}, not affected by the "
               f"date range. Departments with one employee "
               f"({len(tenure) - len(shared)} of {len(tenure)}) are left out.")

    start, end = date_filter("workforce_dates", headcount["as_of_date"].iloc[0], last_day)
    st.plotly_chart(px.line(
        headcount[headcount["as_of_date"].between(start, end)],
        x="as_of_date", y="active_count", title="Active headcount over time",
        labels={"as_of_date": "Date", "active_count": "Active employees"},
    ))
    st.caption("Before Oct 2024, earlier leavers are missing from the file, "
               "so headcount is undercounted.")

    fig = px.bar(
        turnover[turnover["month"].between(start, end)],
        x="month", y=["voluntary", "involuntary"], title="Terminations by month",
        labels={"month": "Month", "value": "Terminations", "variable": "Type"},
    )
    fig.update_yaxes(dtick=1)
    # One tick per month, shown as month and year
    fig.update_xaxes(dtick="M1", tickformat="%b %Y", hoverformat="%b %Y")
    st.plotly_chart(fig)
    st.caption("Terminations are recorded from October 2024 onward; earlier "
               "leavers are missing from the source file.")

with hours_tab:
    hours = load("kpi_rolling_avg_working_hours").sort_values("work_date")
    per_employee = load("kpi_avg_working_hours")
    dept_hours = load("kpi_hours_by_department")

    first_day = hours["work_date"].iloc[0]
    last_day = hours["work_date"].iloc[-1]
    period = f"{first_day:%d %b} – {last_day:%d %b %Y}"
    total_hours = dept_hours["total_hours"].sum()
    employee_days = per_employee["days_worked"].sum()
    no_dept_hours = dept_hours.loc[
        dept_hours["department"] == "No department", "total_hours"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric(f"Avg hours per worked day ({period})",
                f"{total_hours / employee_days:.2f}")
    col2.metric(f"Employees with worked hours ({period})", f"{len(per_employee):,}")
    col3.metric(f"Total worked hours ({period})", f"{total_hours:,.0f}")
    st.caption(CARDS_NOTE)

    # Too big to compare with real departments
    with_dept = dept_hours[dept_hours["department"] != "No department"]
    st.plotly_chart(px.bar(
        with_dept.nlargest(15, "total_hours"), x="total_hours", y="department",
        orientation="h", title="Total hours by department (top 15)",
        labels={"total_hours": "Hours", "department": "Department"},
    ).update_yaxes(categoryorder="total ascending"))
    st.caption(f"Static total for {period}, not affected by the date range. "
               f"Excludes {no_dept_hours:,.0f} hours "
               f"({no_dept_hours / total_hours * 100:.1f}% of all worked hours) "
               "that have no department in the source data.")

    start, end = date_filter("hours_dates", first_day, last_day)
    fig = px.line(
        hours[hours["work_date"].between(start, end)],
        x="work_date", y="rolling_7d_avg_hours",
        title="Average working hours per employee (7-day rolling)",
        labels={"work_date": "Date", "rolling_7d_avg_hours": "Hours"},
    )
    # Start at 0 so small changes don't look like big drops
    fig.update_yaxes(rangemode="tozero")
    # Show the whole selected range, even days with no data
    fig.update_xaxes(range=[start, end])
    st.plotly_chart(fig)
    st.caption("Jul-mid-Sep 2025: low-volume data gap (days with no data "
               "appear as straight segments). The spike around 14 Sep is the "
               "switch to the new timekeeping system.")

with attendance_tab:
    late = load("kpi_late_arrivals")
    early = load("kpi_early_departures")
    overtime = load("kpi_overtime")
    long_shifts = load("kpi_long_shifts").sort_values("month")
    attendance = load("kpi_attendance_by_department")

    late_rate = late["late_arrivals"].sum() / late["scheduled_shifts"].sum() * 100
    double_share = long_shifts["double_shifts"].sum() / long_shifts["worked_shifts"].sum() * 100

    # Same timesheet period as the Working hours tab
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"Late arrival rate ({period})", f"{late_rate:.1f}%")
    col2.metric(f"Early departure days ({period})",
                f"{early['early_departure_days'].sum():,}")
    col3.metric(f"Overtime hours ({period})",
                f"{overtime['overtime_hours'].sum():,.0f}")
    col4.metric(f"Double shift share ({period})", f"{double_share:.2f}%")
    st.caption(CARDS_NOTE)

    start, end = date_filter("attendance_dates", long_shifts["month"].iloc[0],
                             long_shifts["month"].iloc[-1])
    fig = px.bar(
        long_shifts[long_shifts["month"].between(start, end)],
        x="month", y="double_shifts",
        title="Double shifts (over 16 hours) per month",
        labels={"month": "Month", "double_shifts": "Double shifts"},
    )
    # Whole numbers only
    fig.update_yaxes(tickformat="d")
    # One tick per month, shown as month and year
    fig.update_xaxes(dtick="M1", tickformat="%b %Y", hoverformat="%b %Y")
    st.plotly_chart(fig)
    st.caption("Jul-Sep 2025: low-volume data gap, so the drop is missing "
               "data, not fewer double shifts.")

    with_dept = attendance[attendance["department"] != "No department"]
    top = with_dept.nlargest(15, "scheduled_shifts")
    # Rates, so busy and quiet departments compare fairly
    for name, col in [("Late arrivals", "late_arrivals"),
                      ("Early departures", "early_departures"),
                      ("Overtime", "overtime_shifts")]:
        top[name] = (top[col] / top["scheduled_shifts"] * 100).round(1)
    st.plotly_chart(px.bar(
        top, x=["Late arrivals", "Early departures", "Overtime"], y="department",
        orientation="h", barmode="group", height=800,
        title="Late arrivals, early departures and overtime by department "
              "(% of scheduled shifts, top 15 by scheduled shifts)",
        labels={"department": "Department", "value": "% of scheduled shifts",
                "variable": "Measure"},
    ).update_yaxes(autorange="reversed"))
    st.caption("Full data period, not affected by the date range. Scheduled "
               "shifts only (~42% of punches). Shifts with no department are left out.")
