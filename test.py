"""
End-to-end test for AI Spend Guardrail.
Run: python3 test.py
"""
import json
import subprocess
import urllib.request
import urllib.error
from datetime import date

BASE = "http://localhost:8000"
ADMIN = "Bearer local-admin-secret"
DEV   = "Bearer dev"             # any token works when SUPABASE_JWT_SECRET is empty


def req(method, path, body=None, token=ADMIN, proxy_key=None):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if proxy_key:
        headers["x-api-key"] = proxy_key
    elif token:
        headers["Authorization"] = token
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}


def ok(label, condition, detail=""):
    icon = "✅" if condition else "❌"
    print(f"  {icon}  {label}" + (f"  →  {detail}" if detail else ""))
    return condition


def redis_set(key, value):
    subprocess.run(
        ["/usr/local/opt/redis/bin/redis-cli", "set", key, str(value)],
        capture_output=True,
    )


# ─────────────────────────────────────────────────────────────
print("\n── 1. Health check ─────────────────────────────────")
status, body = req("GET", "/health", token="")
ok("Backend is running", status == 200, body)

# ─────────────────────────────────────────────────────────────
print("\n── 2. Create project (via user API) ─────────────────")
# User API sets owner_id = dev-user so ownership checks pass later
status, project = req("POST", "/api/projects", {
    "name": "test-project",
    "budget_daily": 1.00,
    "enforcement_mode": "alert-only",
}, token=DEV)
ok("Project created", status == 201 and "id" in project, project.get("id", project))
project_id = project.get("id")

# ─────────────────────────────────────────────────────────────
print("\n── 3. List projects ─────────────────────────────────")
status, projects = req("GET", "/api/projects", token=DEV)
ok("Project appears in list", any(p["id"] == project_id for p in projects),
   f"{len(projects)} project(s)")

# ─────────────────────────────────────────────────────────────
print("\n── 4. Check spend (should be $0) ────────────────────")
status, spend = req("GET", f"/admin/projects/{project_id}/spend")
ok("Daily spend starts at 0", spend.get("daily_spend") == 0.0, str(spend))

# ─────────────────────────────────────────────────────────────
print("\n── 5. Generate proxy key ────────────────────────────")
print("  ⚠️  Using a FAKE Anthropic key — real API calls will fail until you swap it")
status, key_resp = req("POST", f"/api/projects/{project_id}/keys",
                       {"provider_key": "sk-ant-fake-key-for-testing"}, token=DEV)
ok("Proxy key generated", "proxy_key" in key_resp, key_resp.get("proxy_key", key_resp))
proxy_key = key_resp.get("proxy_key")

# ─────────────────────────────────────────────────────────────
print("\n── 6. Test alert-only (proxy passes request through) ─")
# With a fake key, Anthropic rejects with 401 — but the proxy itself
# should NOT block (alert-only mode, budget not exceeded).
# We verify the proxy forwards (returns Anthropic's error, not a proxy block).
status, resp = req("POST", "/v1/messages", {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 10,
    "messages": [{"role": "user", "content": "hi"}],
}, proxy_key=proxy_key)
proxy_blocked = isinstance(resp.get("detail"), dict) and \
    resp["detail"].get("error", {}).get("type") == "budget_exceeded"
ok("Alert-only mode lets request through (Anthropic rejects fake key, not proxy)",
   status == 401 and not proxy_blocked,
   f"HTTP {status} from Anthropic — proxy passed it through")

# ─────────────────────────────────────────────────────────────
print("\n── 7. Test hard-cap enforcement ─────────────────────")
# Switch to hard-cap and pre-load Redis spend > budget so next call is blocked
status, _ = req("PATCH", f"/api/projects/{project_id}", {
    "name": "test-project",
    "budget_daily": 1.00,
    "enforcement_mode": "hard-cap",
}, token=DEV)

today = date.today().isoformat()
redis_set(f"spend:{project_id}:daily:{today}", 999.0)   # simulate over-budget

status, blocked = req("POST", "/v1/messages", {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 10,
    "messages": [{"role": "user", "content": "hi"}],
}, proxy_key=proxy_key)

detail = blocked.get("detail", {})
block_type = detail.get("error", {}).get("type") if isinstance(detail, dict) else str(detail)
ok("Hard-cap blocks when budget exhausted", status == 429, block_type)

# ─────────────────────────────────────────────────────────────
print("\n── 8. Verify spend reflected in API ─────────────────")
status, spend = req("GET", f"/admin/projects/{project_id}/spend")
ok("Spend shows >0 after simulation", spend.get("daily_spend", 0) > 0, str(spend))

# ─────────────────────────────────────────────────────────────
print("\n── 9. Request log ───────────────────────────────────")
status, requests = req("GET", f"/api/projects/{project_id}/requests", token=DEV)
ok("Requests are logged", isinstance(requests, list),
   f"{len(requests)} request(s) logged")
if requests:
    r0 = requests[0]
    ok("Blocked request flagged correctly", r0.get("was_blocked") is True,
       str(r0))

# ─────────────────────────────────────────────────────────────
print("\n── 10. Coach insights ───────────────────────────────")
status, coach = req("GET", f"/api/projects/{project_id}/coach", token=DEV)
ok("Coach endpoint responds", status == 200 and "top_drivers" in coach)

# ─────────────────────────────────────────────────────────────
print("\n── 11. Auth guard ───────────────────────────────────")
status, _ = req("GET", "/admin/projects", token="Bearer wrong-secret")
ok("Wrong admin secret rejected", status == 403)

# ─────────────────────────────────────────────────────────────
# Reset Redis for clean state
redis_set(f"spend:{project_id}:daily:{today}", 0)

print("\n────────────────────────────────────────────────────")
print("All tests done.\n")
print("To test with a REAL Anthropic key:")
print("  1. Go to http://localhost:8000/docs")
print(f"  2. POST /api/projects/{project_id}/keys  with your real sk-ant-... key")
print("  3. Use the returned sk-guard-... key in your Python code:")
print()
print("     import anthropic")
print('     client = anthropic.Anthropic(api_key="sk-guard-...", base_url="http://localhost:8000")')
print('     r = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=50,')
print('                                messages=[{"role":"user","content":"say hi"}])')
print("     print(r.content)")
