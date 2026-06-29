# Northstar Analytics Revenue Operations Workspace

This folder contains synthetic Revenue Operations source extracts for a growth KPI review.
Use the prompt in `PROMPT.md` and the data under `sources/` to map business lineage,
identify gaps, and prepare leadership-ready findings with BrainDS.

## Visible sources

| Source | Business meaning |
|---|---|
| `crm_accounts.csv` | Account ownership, segment, region, and lifecycle stage |
| `marketing_campaigns.csv` | Campaign spend, leads, MQLs, and influenced pipeline |
| `billing_subscriptions.csv` | ARR, plan, renewal date, and subscription state |
| `product_usage.csv` | Active users, usage events, and health score |
| `support_tickets.csv` | Ticket volume, severity mix, and satisfaction signal |
| `finance_revenue.csv` | Recognized revenue, expansion, contraction, and churn |

Start by creating a graph for the sources, then document KPI assumptions and gaps.
