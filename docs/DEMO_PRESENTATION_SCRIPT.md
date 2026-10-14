# WattWise AI — Live Demo Script

**Audience:** Psiog L&D review panel · pSiddhi 3.0 · S4-I-14
**Target length:** 15 minutes
**Voice:** Simple English. No jargon unless you explain it in the same sentence.

> **Golden rule:** Say *what* a page is for, *what you're seeing*, *why it saves money*, then move on. If someone asks a hard question — pause, answer, continue. Don't rush.

---

## 0 · Pre-flight checklist (15 min before the demo)

Open 3 browser tabs in this order so you can switch fast:

| Tab | URL | What should show |
|---|---|---|
| 1 | http://localhost:8501 | WattWise login page (dark, teal+lime) |
| 2 | http://localhost:9100 | Mock BMS console (dark dashboard, 3 facilities) |
| 3 | file:///C:/Users/arunn.thiayagarajan/sem%204/wattwise-ai/docs/ARCHITECTURE.html | Architecture page with clickable boxes |

Check these are **running** (one terminal each if needed):

```powershell
# Terminal 1 — Streamlit
.venv\Scripts\python.exe -m streamlit run dashboards/streamlit/app.py --server.port 8501

# Terminal 2 — Mock BMS
.venv\Scripts\python.exe -m bms_simulator.server
```

**Login creds** (write these on sticky note):
- `admin` / `wattwise2026` → full access
- `ops` / `ops` → operator (approves actions)
- `demo` / `demo` → read-only guest

**Quick smoke test:** Open AI Chat Agent, ask *"What is office energy usage this month?"* — must return a real paragraph with numbers. If it returns "LLM error" → see Backup Plans at the bottom.

---

## 1 · Opening (30 seconds)

> "Hi, I'm Arunn. This is **WattWise AI** — an energy management platform for commercial buildings that uses AI to find savings opportunities and lets a human approve them.
>
> The whole product follows one rule: **AI advises, human decides**. The AI never changes anything on its own. Every action — shedding load, firing alerts, dispatching technicians — needs a human click.
>
> I'll walk you through the system in about 15 minutes. If you have questions, interrupt anytime."

**→ Switch to Tab 1 (Streamlit), start logged out at the login page.**

---

## 2 · Login (1 minute)

**Click:** Log in as `admin` / `wattwise2026`

**Say:**
> "Login has three roles: Admin, Operator, Viewer. Admin sees everything including the audit log. Operator can approve actions. Viewer is read-only — for stakeholders like finance or ESG who should look but not touch.
>
> One small UX detail — the session survives a browser refresh. Normally Streamlit forgets you logged in. We added a signed token in the URL so you don't get kicked out mid-demo."

**→ The sidebar now shows 10 workspace pages.**

---

## 3 · Morning Briefing — the headline (2 minutes)

**Click:** Morning Briefing (first item in sidebar)

**Say:**
> "This is the page a facility manager would start their day on. The AI has already done the work — it ran four specialist agents in parallel at startup, each looked at the last 30 days of data, and the top 3 ranked recommendations are shown as cards.
>
> Every card has three sections — written in plain English:
> - **Problem** — what's happening, with real numbers
> - **Solution** — what to do and how much it saves
> - **Evidence** — 3-5 bullet points proving the AI's claim
>
> Three buttons on each card: **Approve**, **Snooze**, **Dismiss**.
>
> Watch what happens when I click Approve on this one."

**Click:** Approve on the top card

**Say:**
> "The card collapses to a one-line confirmation. The action was logged. If it was a load-shed action, the Mock BMS webhook was called — I'll show that live in a minute.
>
> This single page replaces about **two hours of spreadsheet work per day** for a facility manager."

---

## 4 · Real-Time Consumption (1.5 minutes)

**Click:** Real-Time Consumption

**Say:**
> "This is the live view — kWh per 15-minute window, split by the four real energy devices: main meter, sub-meter, HVAC, and lighting.
>
> You can see the daily rhythm — tall peaks during office hours, low valleys at night and weekends. HVAC is the biggest band at the bottom because that's where most of the power goes in a commercial building.
>
> The small AI line underneath the chart says what's actually happening in plain English — things like 'Office is running 15% above its usual Tuesday afternoon baseline.'"

**If anyone notices weather/occupancy are missing from the stack:**
> "We filtered out weather and occupancy because those are context sensors, not power loads. Including them on a kWh chart would be misleading. They're still stored in the database for Phase 2 features like weather-aware forecasting."

---

## 5 · Demand Pattern Analysis (2 minutes) — ⭐ money concept

**Click:** Demand Pattern Analysis

**Say:**
> "This view explains WHY energy bills in India have two parts.
>
> **Part one** is consumption — how many units you used, like water on a bill. That's your regular charges.
>
> **Part two** is **demand** — the highest power you ever pulled, even for one minute. The utility charges you ₹150 per kW per month for that peak. One spike can set your bill for the whole month.
>
> This blue line is the actual power draw. The red dashed line is the pain threshold. Every time the blue crosses above the red, that's an **exceedance** — a billing event.
>
> The three KPIs below tell the story:
> - **Peak Demand: 286 kW** — the single biggest spike. That alone adds ₹42,900 to this month's bill.
> - **Avg Demand: 34 kW** — the normal running power.
> - **Exceedances: 288** — how many 15-minute windows crossed the red line.
>
> The slider on the left lets you move the red line to your actual utility contract limit. Then the exceedance count becomes 'how many times you'd have been penalised.'
>
> The green banner at the top is the AI already doing the math — it says *'₹11,850 a month peak-shed opportunity, 85% confidence'*. The operator doesn't need to interpret the chart — the AI already told them what to do."

---

## 6 · Cost Analysis (1 minute)

**Click:** Cost Analysis

**Say:**
> "The money view. Simple line chart of rupees spent over time, with KPIs for total cost, average per 15-minute window, and peak-hour cost.
>
> The rate boxes at the bottom show the Indian Time-of-Use tariff: **₹12 per kWh during peak hours (9 AM to 6 PM), ₹5.5 during off-peak**. More than double the price for using the same unit at the wrong time.
>
> The CostAgent reads this and finds loads running during expensive peak hours that could be shifted to off-peak — recommendations show in the strip at the top."

---

## 7 · AI Optimization (3 tabs, 3 minutes) — ⭐ the brain

**Click:** AI Optimization — this view has 3 tabs across the top

### Tab 1 — Anomaly Detection

**Say:**
> "Three machine-learning models vote on every reading — IsolationForest, COPOD, ECOD. If they agree something is unusual, it gets flagged as a red X.
>
> In the last 30 days the AI found 81 anomalies — about 2.8% of all readings. The tall ones at 200+ kW are things like a stuck HVAC compressor or a scheduler left running overnight.
>
> Below the chart you see the top 5 anomalies sorted by severity — Critical, Major, Minor. Click **Investigate** on any one and the ForensicAgent writes a diagnostic card: why we flagged it, what we think caused it, what to do, and a draft work order ready to paste into ServiceNow or Jira."

**Click:** Investigate on the top anomaly → the drill-down modal opens.

**Say:**
> "This is the ForensicAgent reasoning in real time. The 'Dispatch technician' button at the bottom goes through the human-approval pipeline — it writes to the audit log and would open a ticket in production."

**Close the modal.**

### Tab 2 — Demand Forecast

**Click:** Demand Forecast tab

**Say:**
> "This uses Amazon's Chronos foundation model — a time-series AI trained on millions of patterns from different industries. It predicts the next 24 hours of demand without needing custom training per site.
>
> The solid line is actual history. The dashed line is the forecast. The purple shaded band is the confidence range — 'the real answer will be somewhere in here.'
>
> If tomorrow's predicted peak is above the contract limit, the operator can pre-cool the building — spend ₹500 to save ₹43,000."

**Honest footnote if asked about accuracy:**
> "The RFP target MAPE is 8%. The stock Chronos model needs some tuning on top of the raw forecast to hit that cleanly — the tuning work is in progress."

### Tab 3 — Peak Shaving

**Click:** Peak Shaving tab

**Say:**
> "When demand gets close to the pain line, this tab tells the operator **which specific loads to turn off**.
>
> It uses XGBoost — a decision-tree AI — ranked by how safe each load is to shed. Server rooms score zero — never shed. EV chargers and some lighting score high — safe to defer. The AI protects critical equipment automatically.
>
> If peak warning is on, the operator sees a sorted shortlist with the kW savings per load. One click to approve sends it to the Mock BMS."

---

## 8 · Cross-Facility Benchmark (1 minute)

**Click:** Cross-Facility Benchmark

**Say:**
> "The portfolio view — comparing all three facilities side-by-side on kWh per square foot, cost per square foot, average demand, peak demand.
>
> Behind the scenes, k-means clustering groups facilities by load shape. If one site is far from its cluster peers, that's a savings opportunity. Great for a multi-site operations director — tells them which facility to fix first."

---

## 9 · AI Chat Agent (1.5 minutes) — natural language

**Click:** AI Chat Agent

**Say:**
> "Free-form questions in plain English. The ChatAgent has 10 tools it can call — facility stats, anomalies, forecasts, cost, peak hours. It picks the right tools based on your question.
>
> Watch — I'll ask something real."

**Type:** `What is office energy usage this month?`

**Wait for the response.**

**Say:**
> "Behind the scenes it ran the ReAct loop — Observe, Think, Act. It called the cost analysis tool, read the result, and wrote the answer in plain English with real numbers. The system is open — any agent's reasoning can be inspected."

---

## 10 · Full Agent Sweep (1 minute)

**Click:** Full Agent Sweep

**Say:**
> "This runs all 4 specialist agents in parallel for a chosen facility — like a full physical. Each agent produces its own report and you see them side-by-side.
>
> If a specialist times out or fails, the other three still return. Fault-tolerant by design."

---

## 11 · Audit Log (1 minute) — ⭐ accountability

**Click:** Audit Log *(admin only — this is why we logged in as admin)*

**Say:**
> "Every AI suggestion. Every human decision. Every executed action. Append-only. Timestamped in UTC. Immutable.
>
> This is the accountability contract. If someone six months from now asks 'who approved this HVAC shed on October 10?' — the answer is one row away.
>
> It's also the proof that AI never acted on its own. Every state-changing action in this log has a `human_decided` row before an `action_executed` row — enforced in code."

---

## 12 · Side-by-side closed-loop proof (1.5 minutes) — ⭐ the magic moment

**Open Tab 2 (Mock BMS console) alongside Streamlit.**

**Say:**
> "This is the Mock Building Management System running on port 9100. It pretends to be the real BMS that would control HVAC, chillers, lighting in a facility.
>
> I'll show you the closed loop end-to-end."

**On Streamlit — switch to Morning Briefing, pick a shed-load card, click Approve.**

**Say:**
> "I just approved a load shed on Office HQ."

**On Mock BMS console — point to the Office HQ facility card.**

**Say:**
> "Watch — the current demand just dropped. A new override line appeared in the history. The HTTP POST happened, the Mock BMS acted, the building state changed. Full loop closed.
>
> In production, this exact code path writes BACnet commands to a real BMS. The protocol shape is identical — the Mock just makes the demo visible."

---

## 13 · Alert Settings (30 seconds — optional)

**Click:** Alert Settings

**Say:**
> "Admin configuration page. One place to set the LLM provider, email, SMS, and the BMS webhook URL. Changes save instantly — no restart.
>
> We're currently using Groq's Qwen model and Gmail SMTP for alerts. The email channel is live — one of the Morning Briefing approvals earlier actually sent an email."

---

## 14 · Closing (1 minute)

**Say:**
> "That's WattWise AI. Three things to remember:
>
> **One.** The product is an **AI advisor, never an auto-executor**. Every state change needs a human click. Every click is audited.
>
> **Two.** It's built for **non-technical facility managers**. The AI translates data into plain English — Problem, Solution, Evidence. No charts needed to make a decision.
>
> **Three.** The savings are **measurable in rupees**. A single facility typically saves ₹20,000–₹60,000 a month — one prevented demand spike, one load shifted, one anomaly caught before equipment breaks.
>
> On the engineering side: 690 unit tests, 55 integration tests, 100% backend coverage on core modules. Deployed to Azure Functions, backed by Azure Blob Storage. The architecture is a click-to-explore HTML page I can share after.
>
> Happy to take questions."

---

## 15 · Anticipated Q&A

### "Why not let the AI act on its own?"
> *"Trust and liability. If an AI shuts down a chiller and food spoils, who's responsible? With human-in-the-loop, the human is accountable and the AI is auditable. The audit log proves which human approved which action."*

### "What if the LLM is wrong?"
> *"Three safeguards. First, every claim is backed by real data from a tool call — not invented. Second, the human reviews before approving — the AI never acts alone. Third, if the LLM is unavailable, the system falls back to template-based recommendations so it never crashes."*

### "What's the architecture?"
> *"Five layers — IoT ingestion, analytics storage, AI/ML core, triggers, dashboards. I have a click-to-explore HTML page that explains every box in plain English — happy to share after."* **(Pull up Tab 3.)**

### "Which parts are deployed to Azure?"
> *"Two things are live in Azure right now — a Function App and Storage. Seven more services are provisioned-ready in our resource group — IoT Hub, VM, ACS, Application Insights, Key Vault — the RBAC roles are granted, we just haven't needed them for the demo yet."*

### "What's the business case?"
> *"₹20,000–₹60,000 per facility per month in savings. For a 3-facility customer that's ₹60,000–₹180,000/month. The system pays for itself in weeks."*

### "What ML models?"
> *"PyOD ensemble for anomaly detection — F1 of 0.927. Amazon Chronos for forecasting — tuning for the RFP's 8% MAPE target. XGBoost for load-shed ranking. k-means for cluster benchmarking. Evidently for drift monitoring."*

### "How do you handle data from real buildings?"
> *"Same message shape. The simulator publishes MQTT messages with the same schema real smart meters would use. Swap Mosquitto for Azure IoT Hub, swap the simulator for real meters — nothing downstream changes."*

### "What about BRSR / ESG reporting?"
> *"Dashboard-based ESG snapshot is live today. Formal BRSR export is on the roadmap — the data is all tracked, we just need the formatter."*

### "What's the one gap?"
> *"Chronos accuracy. The stock foundation model needs seasonal preprocessing to hit the 8% MAPE target cleanly. That tuning is in progress. Everything else — anomaly detection, cost engine, agent orchestration, the human-in-loop pipeline, the audit log — meets or exceeds the RFP."*

---

## 16 · Backup Plans (if things break mid-demo)

### If the LLM returns an error
- **Fall back to:** The AI caption engine's **template tier** will still produce text — just less fancy
- **Say:** *"The LLM provider is rate-limited right now — the template layer takes over. Same data, less wordy."*

### If Mock BMS doesn't respond
- **Fall back to:** The dispatch logs the command and returns `"status": "logged"` gracefully
- **Say:** *"The BMS endpoint is down — the system degraded to log-only mode without crashing. The audit log still has the full trail."*

### If Streamlit crashes
- **Fall back to:** Open the Architecture HTML (Tab 3) — walk through it visually
- **Say:** *"Let me walk you through the architecture while I restart the dashboard."*

### If a chart looks weird
- **Say:** *"That's synthetic simulator data — the production ingestion path uses real smart-meter readings. The shape is intentionally spiky so the anomaly detector has something to find."*

### If someone asks about Azure resources that don't exist
- **Fall back to:** Honesty — *"We provisioned Function App and Storage. The other blueprint resources — IoT Hub, VM, ACS — the RBAC is granted and providers are registered; we didn't provision them because the local substitutes made the demo closed-loop. Can create any of them in one az CLI command."*

### If someone catches a bug
- **Say:** *"Good catch — that's going on the issue list."* **Write it down. Move on.** Don't try to fix it live.

---

## Script-ready quick reference card (print this)

```
LOGIN            admin / wattwise2026       (full access)
                 ops   / ops                (operator)
                 demo  / demo               (viewer)

URLS             Streamlit    localhost:8501
                 Mock BMS     localhost:9100
                 Architecture docs/ARCHITECTURE.html

HEADLINE         "AI advises, human decides. Every action is approved. Every decision is audited."

NUMBERS          Peak demand charge: ₹150/kW/month
                 Peak-hour tariff:   ₹12/kWh
                 Off-peak tariff:    ₹5.5/kWh
                 Typical savings:    ₹20,000–₹60,000 per facility per month
                 Tests:              690 unit + 55 integration · 100% core coverage
                 Facilities:         3 (Office HQ, Warehouse, Data Centre)
                 Agents:             4 specialists + 3 meta-agents + ChatAgent

CLOSED LOOP      Streamlit Approve → ActionHandler → HTTP POST → Mock BMS state change
                 Open both tabs side-by-side when demoing this
```

---

**End of script.** Total walkthrough: ~15 minutes. Q&A as long as they want.
