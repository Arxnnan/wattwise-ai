# dashboards/ — Monitoring Dashboards (Layer 5)

**Built in:** Weeks 6, 12, 15

Three surfaces, 5 views (RFP minimum is 4).

| # | View | Surface | Folder | Week |
|---|---|---|---|---|
| 1 | Real-Time Consumption | Grafana | `grafana/` | Wk 6 |
| 2 | Demand Pattern Analysis | Grafana | `grafana/` | Wk 6 |
| 3 | Cost Analysis | Power BI | `powerbi/` | Wk 12 |
| 4 | AI Optimization Intelligence | Streamlit + Power BI | `streamlit/` | Wk 12 |
| 5 | Cross-Facility Benchmarking *(bonus)* | Power BI | `powerbi/` | Wk 15 |

## Subfolders
- `grafana/provisioning/` — datasources (ClickHouse) + dashboard JSON, auto-loaded by the Grafana container
- `streamlit/` — `app.py` public demo dashboard (deployed to Streamlit Community Cloud)
- `powerbi/` — `.pbix` files (executive views)

## Notes
Grafana = real-time ops (energy-industry standard). Power BI = executive. Streamlit = public demo URL so reviewers click through without screen-share.
