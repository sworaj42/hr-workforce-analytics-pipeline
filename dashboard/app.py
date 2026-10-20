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


st.set_page_config(page_title="HR Workforce Dashboard", layout="wide")
st.title("HR Workforce Dashboard")

headcount = load("kpi_active_headcount")
turnover = load("kpi_turnover_trend")
hours = load("kpi_rolling_avg_working_hours")
dept_hours = load("kpi_hours_by_department")
attendance = load("kpi_attendance_by_department")

# Applies to the time charts only
start, end = st.date_input(
    "Date range",
    value=(headcount["as_of_date"].min(), headcount["as_of_date"].max()),
)
headcount = headcount[headcount["as_of_date"].between(start, end)]
turnover = turnover[turnover["month"].between(start, end)]
hours = hours[hours["work_date"].between(start, end)]

# Too big to compare with real departments
dept_hours = dept_hours[dept_hours["department"] != "No department"]
attendance = attendance[attendance["department"] != "No department"]

workforce_tab, hours_tab, attendance_tab = st.tabs(
    ["Workforce", "Working hours", "Attendance"]
)

with workforce_tab:
    # Cards use the full data, not the date filter
    all_headcount = load("kpi_active_headcount").sort_values("as_of_date")
    all_turnover = load("kpi_turnover_trend")
    tenure = load("kpi_avg_tenure_by_department")
    attrition = load("kpi_early_attrition_rate")

    # Weighted by employees, so big departments count more
    avg_tenure = (tenure["avg_tenure_years"] * tenure["employees"]).sum() / tenure["employees"].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current headcount", all_headcount["active_count"].iloc[-1])
    col2.metric("Total terminations", all_turnover["terminations"].sum())
    col3.metric("Average tenure (years)", f"{avg_tenure:.1f}")
    col4.metric("Early attrition (90 days)",
                f"{attrition['early_attrition_rate_pct'].iloc[0]}%")

    st.plotly_chart(px.line(
        headcount, x="as_of_date", y="active_count",
        title="Active headcount over time",
        labels={"as_of_date": "Date", "active_count": "Active employees"},
    ))
    st.caption("Before Oct 2024, earlier leavers are missing from the file, "
               "so headcount is undercounted.")

    fig = px.bar(
        turnover, x="month", y=["voluntary", "involuntary"],
        title="Terminations by month",
        labels={"month": "Month", "value": "Terminations", "variable": "Type"},
    )
    fig.update_yaxes(dtick=1)
    st.plotly_chart(fig)

    st.plotly_chart(px.bar(
        tenure.sort_values("avg_tenure_years"), x="avg_tenure_years",
        y="department_name", orientation="h", hover_data=["employees"],
        height=800, title="Average tenure by department",
        labels={"avg_tenure_years": "Years", "department_name": "Department",
                "employees": "Employees"},
    ))
    st.caption("29 of 38 departments have one employee; "
               "read with the employee count.")

with hours_tab:
    st.plotly_chart(px.line(
        hours, x="work_date", y="rolling_7d_avg_hours",
        title="Average working hours per employee (7-day rolling)",
        labels={"work_date": "Date", "rolling_7d_avg_hours": "Hours"},
    ))
    st.plotly_chart(px.bar(
        dept_hours.nlargest(15, "total_hours"), x="total_hours", y="department",
        orientation="h", title="Total hours by department (top 15)",
        labels={"total_hours": "Hours", "department": "Department"},
    ).update_yaxes(categoryorder="total ascending"))
    st.caption("Jul-Sep 2025: low-volume data gap, not a real drop. "
               "Punches with no department are left out of the bar chart.")

with attendance_tab:
    top = attendance.nlargest(15, "scheduled_shifts")
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
    st.caption("Scheduled shifts only (~42% of punches). "
               "Shifts with no department are left out.")
