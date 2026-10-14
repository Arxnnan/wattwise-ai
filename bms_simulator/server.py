"""Mock BMS web server + console.

Receives HTTP POST commands at /command, maintains in-memory per-facility state
(current demand, active overrides, command history), and serves a dark-themed
live dashboard at / that auto-refreshes every 2 seconds.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError as e:
    raise SystemExit(
        "Mock BMS requires fastapi + uvicorn. Install with:\n"
        "  pip install fastapi uvicorn\n"
        f"(original error: {e})"
    )

log = logging.getLogger("bms_simulator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

# ──────────────────── In-memory state ────────────────────

DEFAULT_BASELINES = {
    "office":     {"baseline_kw": 65.0, "label": "Office HQ"},
    "warehouse":  {"baseline_kw": 110.0, "label": "Warehouse"},
    "datacentre": {"baseline_kw": 90.0, "label": "Data Centre"},
}

@dataclass
class BuildingState:
    facility_id: str
    label: str
    baseline_kw: float
    current_kw: float
    threshold_kw: float = 150.0
    active_overrides: list[dict] = field(default_factory=list)   # [{load, action, applied_at, kw_reduction}]
    history: deque = field(default_factory=lambda: deque(maxlen=50))  # command log

    def apply_shed(self, loads: list[str], shed_kw: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for load in loads or ["unknown"]:
            self.active_overrides.append({
                "load": load,
                "action": "cycled off",
                "applied_at": now,
                "kw_reduction": round(shed_kw / max(len(loads), 1), 1),
            })
        self.current_kw = max(self.baseline_kw * 0.5, self.current_kw - shed_kw)

    def apply_schedule_shift(self, target_hours: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.active_overrides.append({
            "load": "scheduled loads",
            "action": f"shifted to {target_hours}",
            "applied_at": now,
            "kw_reduction": 0.0,
        })

    def apply_dispatch(self, note: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.active_overrides.append({
            "load": "technician dispatched",
            "action": note or "work order created",
            "applied_at": now,
            "kw_reduction": 0.0,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "facility_id": self.facility_id,
            "label": self.label,
            "current_kw": round(self.current_kw, 1),
            "baseline_kw": round(self.baseline_kw, 1),
            "threshold_kw": self.threshold_kw,
            "over_threshold": self.current_kw > self.threshold_kw,
            "active_overrides": list(self.active_overrides),
            "history": list(self.history),
            "last_command_at": self.history[0]["received_at"] if self.history else None,
        }


class BMSState:
    """Thread-safe in-memory state for all facilities."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._facilities: dict[str, BuildingState] = {}
        for fid, meta in DEFAULT_BASELINES.items():
            self._facilities[fid] = BuildingState(
                facility_id=fid, label=meta["label"],
                baseline_kw=meta["baseline_kw"],
                current_kw=meta["baseline_kw"] * 1.3,  # start slightly stressed for demo
            )

    def get(self, facility_id: str) -> BuildingState:
        with self._lock:
            if facility_id not in self._facilities:
                self._facilities[facility_id] = BuildingState(
                    facility_id=facility_id, label=facility_id.title(),
                    baseline_kw=50.0, current_kw=70.0,
                )
            return self._facilities[facility_id]

    def all(self) -> list[BuildingState]:
        with self._lock:
            return list(self._facilities.values())

    def receive_command(self, payload: dict) -> dict:
        """Apply a command from WattWise to a facility. Returns ack dict."""
        facility_id = str(payload.get("facility") or payload.get("facility_id") or "office")
        action_type = str(payload.get("action_type") or payload.get("action") or "unknown")
        now_iso = datetime.now(timezone.utc).isoformat()

        state = self.get(facility_id)
        with self._lock:
            entry = {
                "received_at": now_iso,
                "action_type": action_type,
                "facility_id": facility_id,
                "payload": payload,
            }
            state.history.appendleft(entry)

            if action_type == "shed_load":
                loads = payload.get("loads") or []
                shed_kw = float(payload.get("shed_kw") or payload.get("kw", 0) or 0)
                state.apply_shed(loads, shed_kw)
                summary = f"Shed {shed_kw:.1f} kW across {len(loads) or 1} loads"
            elif action_type == "shift_schedule":
                target = str(payload.get("target_hours") or payload.get("device_id") or "23:00-06:00")
                state.apply_schedule_shift(target)
                summary = f"Schedule shift to {target}"
            elif action_type == "dispatch_technician":
                state.apply_dispatch(str(payload.get("note", "work order queued")))
                summary = "Technician dispatched"
            else:
                summary = f"Logged ({action_type})"
            entry["summary"] = summary

        log.info("[BMS] facility=%s action=%s | %s", facility_id, action_type, summary)
        return {
            "status": "accepted",
            "facility_id": facility_id,
            "action_type": action_type,
            "summary": summary,
            "received_at": now_iso,
        }


STATE = BMSState()

# ──────────────────── FastAPI app ────────────────────

app = FastAPI(title="WattWise Mock BMS", version="1.0")


@app.post("/command")
async def receive_command(request: Request) -> JSONResponse:
    """Accept a command from WattWise action dispatcher.
    Expected payload (loose schema — we accept anything):
      { facility: str, action_type: str, loads: [str], shed_kw: float, ... }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    ack = STATE.receive_command(body if isinstance(body, dict) else {})
    return JSONResponse(ack)


@app.get("/api/state")
async def api_state() -> JSONResponse:
    return JSONResponse([s.to_dict() for s in STATE.all()])


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mock-bms", "version": "1.0"})


# ──────────────────── Dashboard HTML ────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>WattWise Mock BMS — Live Console</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fraunces:wght@400;500&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#0E0E10; --elev:#16171a; --border:rgba(255,255,255,0.08);
    --text:#ECECEE; --mute:#a1a1a7; --dim:#6b6b73;
    --teal:#28B3B4; --lime:#D6DF27; --rose:#e85d4f; --amber:#e0a93d;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}
  .wrap{max-width:1480px;margin:0 auto;padding:28px 32px 48px;}
  .header{display:flex;align-items:center;justify-content:space-between;padding-bottom:20px;border-bottom:1px solid var(--border);margin-bottom:28px;}
  .brand{display:flex;align-items:center;gap:12px;}
  .logo{width:38px;height:38px;background:var(--teal);color:var(--bg);display:flex;align-items:center;justify-content:center;border-radius:10px;font-weight:700;font-size:1.1rem;font-family:'Fraunces',serif;}
  .brand-text .n{font-weight:700;font-size:17px;letter-spacing:-0.3px;}
  .brand-text .s{color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;margin-top:2px;}
  .live{display:inline-flex;align-items:center;gap:7px;padding:5px 12px;background:rgba(214,223,39,0.08);border:1px solid rgba(214,223,39,0.25);border-radius:999px;color:var(--lime);font-size:12px;font-weight:600;}
  .live .dot{width:7px;height:7px;border-radius:50%;background:var(--lime);box-shadow:0 0 8px var(--lime);animation:pulse 2s infinite;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
  .page-title{font-family:'Fraunces',serif;font-size:28px;font-weight:400;letter-spacing:-0.5px;line-height:1.2;margin-bottom:6px;}
  .page-sub{color:var(--mute);font-size:14px;margin-bottom:28px;}
  .facilities{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:28px;}
  .card{background:var(--elev);border:1px solid var(--border);border-radius:12px;padding:22px;transition:border-color 0.3s;}
  .card.flash{border-color:var(--teal);box-shadow:0 0 0 2px rgba(40,179,180,0.3);}
  .card h3{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:14px;}
  .kw{font-family:'Fraunces',serif;font-size:48px;font-weight:400;letter-spacing:-1.2px;line-height:1;color:var(--text);font-variant-numeric:tabular-nums;}
  .kw.over{color:var(--rose);}
  .kw-unit{font-family:'Inter',sans-serif;font-size:16px;color:var(--mute);font-weight:500;margin-left:6px;}
  .meta{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:12px;border-top:1px solid var(--border);font-size:12px;color:var(--mute);}
  .meta strong{color:var(--text);}
  .bar{height:6px;background:rgba(255,255,255,0.05);border-radius:3px;margin-top:14px;position:relative;overflow:visible;}
  .bar .fill{height:100%;background:var(--teal);border-radius:3px;transition:width 0.6s cubic-bezier(0.23,1,0.32,1);}
  .bar .fill.over{background:var(--rose);}
  .bar .threshold{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--amber);}
  .threshold-lbl{font-size:10px;color:var(--amber);margin-top:4px;font-family:'JetBrains Mono',monospace;}
  .overrides{margin-top:18px;}
  .ov-lbl{font-size:10.5px;color:var(--mute);text-transform:uppercase;letter-spacing:0.08em;font-weight:600;margin-bottom:8px;}
  .ov-item{background:rgba(40,179,180,0.06);border-left:2px solid var(--teal);padding:7px 11px;border-radius:0 4px 4px 0;margin-bottom:5px;font-size:12.5px;}
  .ov-item .load{color:var(--text);font-weight:500;}
  .ov-item .act{color:var(--mute);font-size:11px;margin-top:1px;}
  .no-ov{color:var(--dim);font-size:12px;font-style:italic;padding:7px 0;}
  .feed-wrap{background:var(--elev);border:1px solid var(--border);border-radius:12px;overflow:hidden;}
  .feed-head{padding:16px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
  .feed-title{font-size:15px;font-weight:600;letter-spacing:-0.1px;}
  .feed-count{font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--mute);padding:3px 9px;background:rgba(255,255,255,0.04);border-radius:999px;}
  .feed-list{max-height:600px;overflow-y:auto;}
  .feed-row{padding:14px 22px;border-bottom:1px solid var(--border);display:grid;grid-template-columns:150px 130px 1fr;gap:16px;align-items:start;font-size:13px;}
  .feed-row:last-child{border-bottom:none;}
  .feed-row .ts{font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--dim);}
  .feed-row .act{color:var(--teal);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:0.08em;background:rgba(40,179,180,0.08);padding:3px 9px;border-radius:4px;border:1px solid rgba(40,179,180,0.25);justify-self:start;}
  .feed-row .sum{color:var(--text);line-height:1.5;}
  .feed-row .sum .fac{color:var(--mute);font-size:11.5px;margin-top:3px;}
  .empty{padding:48px 22px;text-align:center;color:var(--dim);font-size:13px;}
  .footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--border);display:flex;justify-content:space-between;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:0.08em;}
  .footer .r{font-family:'JetBrains Mono',monospace;text-transform:none;letter-spacing:0;}
  @media (max-width:1024px){.facilities{grid-template-columns:1fr;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="brand">
      <div class="logo">B</div>
      <div class="brand-text">
        <div class="n">Mock BMS Console</div>
        <div class="s">WattWise AI · command receiver</div>
      </div>
    </div>
    <div class="live"><span class="dot"></span>Receiving commands</div>
  </div>

  <h1 class="page-title">Live building state</h1>
  <p class="page-sub">Commands received from WattWise appear here in real time. Each facility reacts to shed / schedule-shift / dispatch events.</p>

  <div id="facilities" class="facilities"></div>

  <div class="feed-wrap">
    <div class="feed-head">
      <div class="feed-title">Command feed</div>
      <span class="feed-count" id="count">0 commands</span>
    </div>
    <div id="feed" class="feed-list"></div>
  </div>

  <div class="footer">
    <div>WattWise Mock BMS · Listening on :9100 · auto-refresh every 2s</div>
    <div class="r">v1.0</div>
  </div>
</div>

<script>
let lastCommandAt = null;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function timeOnly(iso) {
  if (!iso) return '--:--:--';
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2,'0');
  const mm = String(d.getUTCMinutes()).padStart(2,'0');
  const ss = String(d.getUTCSeconds()).padStart(2,'0');
  return `${hh}:${mm}:${ss} UTC`;
}

async function refresh() {
  try {
    const r = await fetch('/api/state');
    const facilities = await r.json();

    // ── Facility cards ──
    const facHtml = facilities.map(f => {
      const pct = Math.min(100, (f.current_kw / (f.threshold_kw * 1.3)) * 100);
      const thresholdPct = (f.threshold_kw / (f.threshold_kw * 1.3)) * 100;
      const over = f.over_threshold;
      const flash = (f.last_command_at && f.last_command_at !== lastCommandAt);
      const overrides = f.active_overrides.slice(-4).reverse();
      return `
        <div class="card ${flash ? 'flash' : ''}">
          <h3>${escapeHtml(f.label)}</h3>
          <div class="kw ${over ? 'over' : ''}">${f.current_kw}<span class="kw-unit">kW</span></div>
          <div class="bar">
            <div class="fill ${over ? 'over' : ''}" style="width:${pct}%"></div>
            <div class="threshold" style="left:${thresholdPct}%"></div>
          </div>
          <div class="threshold-lbl">▲ ${f.threshold_kw} kW demand-charge threshold</div>
          <div class="meta">
            <span>Baseline <strong>${f.baseline_kw} kW</strong></span>
            <span>${over ? '<strong style="color:#e85d4f">OVER LIMIT</strong>' : 'Within limit'}</span>
          </div>
          <div class="overrides">
            <div class="ov-lbl">Active overrides (${f.active_overrides.length})</div>
            ${overrides.length ? overrides.map(o => `
              <div class="ov-item">
                <div class="load">${escapeHtml(o.load)}</div>
                <div class="act">${escapeHtml(o.action)}${o.kw_reduction ? ' · ' + o.kw_reduction + ' kW saved' : ''} · ${timeOnly(o.applied_at)}</div>
              </div>`).join('') : '<div class="no-ov">No active overrides — building operating normally</div>'}
          </div>
        </div>`;
    }).join('');
    document.getElementById('facilities').innerHTML = facHtml;

    // ── Command feed (merge all facilities) ──
    const allHistory = [];
    facilities.forEach(f => f.history.forEach(h => allHistory.push({...h, _label: f.label})));
    allHistory.sort((a, b) => (b.received_at || '').localeCompare(a.received_at || ''));

    document.getElementById('count').textContent = `${allHistory.length} command${allHistory.length === 1 ? '' : 's'}`;
    const feedHtml = allHistory.length ? allHistory.slice(0, 50).map(h => `
      <div class="feed-row">
        <div class="ts">${timeOnly(h.received_at)}</div>
        <div class="act">${escapeHtml(h.action_type || '?')}</div>
        <div class="sum">
          ${escapeHtml(h.summary || '(no summary)')}
          <div class="fac">${escapeHtml(h._label)} · payload keys: ${Object.keys(h.payload || {}).join(', ') || '—'}</div>
        </div>
      </div>`).join('') : '<div class="empty">No commands received yet. Click Approve on a WattWise recommendation to see it appear here.</div>';
    document.getElementById('feed').innerHTML = feedHtml;

    // Track latest for flash animation
    const latest = facilities.map(f => f.last_command_at).filter(Boolean).sort().slice(-1)[0];
    if (latest) lastCommandAt = latest;
  } catch (e) {
    console.error('refresh failed', e);
  }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


# ──────────────────── Entrypoint ────────────────────

def main() -> None:
    log.info("Starting Mock BMS on http://localhost:9100")
    log.info("Point WattWise Alert Settings -> BMS_WEBHOOK_URL to http://localhost:9100/command")
    uvicorn.run(app, host="127.0.0.1", port=9100, log_level="warning")


if __name__ == "__main__":
    main()
