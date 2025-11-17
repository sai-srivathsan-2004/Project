#!/usr/bin/env python3
import os, requests, time, sys

SALT_API_URL = os.environ.get("SALT_API_URL")
SALT_API_TOKEN = os.environ.get("SALT_API_TOKEN")
OAS_PATH = os.environ.get("OAS_PATH","openapi.generated.json")

if not SALT_API_TOKEN or not SALT_API_URL:
    print("Missing SALT_API_URL or SALT_API_TOKEN", file=sys.stderr); sys.exit(1)

headers = {"Authorization": f"Bearer {SALT_API_TOKEN}"}
files = {"file": open(OAS_PATH, "rb")}

# Upload (placeholder endpoint - replace per Salt docs)
r = requests.post(f"{SALT_API_URL}/api/v1/oas/upload", headers=headers, files=files)
r.raise_for_status()
resp = r.json()
print("Upload response:", resp)

# Adjust how you extract job id depending on Salt's response payload:
job = resp.get("job_id") or resp.get("id") or resp.get("job") or None
if not job:
    print("Could not determine job id from response. Save response and inspect.", resp)
    sys.exit(1)

# Poll
for _ in range(60):
    st = requests.get(f"{SALT_API_URL}/api/v1/oas/jobs/{job}/status", headers=headers)
    st.raise_for_status()
    j = st.json()
    status = j.get("status") or j.get("state") or ""
    print("status:", status)
    if status in ("finished","completed","success"):
        print("job done, fetching csv...")
        out = requests.get(f"{SALT_API_URL}/api/v1/oas/jobs/{job}/export?format=csv", headers=headers)
        with open("salt_oas_result.csv","wb") as fh:
            fh.write(out.content)
        print("Downloaded salt_oas_result.csv")
        sys.exit(0)
    time.sleep(10)

print("Timed out waiting for job", job)
sys.exit(2)
