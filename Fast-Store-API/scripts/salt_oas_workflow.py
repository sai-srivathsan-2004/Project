#!/usr/bin/env python3
"""
salt_oas_workflow.py
Usage:
  python3 scripts/salt_oas_workflow.py --oas openapi.json --salt-url https://api.salt... --salt-key <token> --company-id <companyId> --api-id <apiId>
"""
import argparse, requests, time, json, sys, os
import pandas as pd

def log(*a, **k):
    print(*a, **k); sys.stdout.flush()

parser = argparse.ArgumentParser()
parser.add_argument("--oas", required=True, help="Path to OAS file")
parser.add_argument("--salt-url", required=True, help="Base Salt API URL (e.g. https://api.salt-tenant.com)")
parser.add_argument("--salt-key", required=True, help="Salt API key (bearer token or header value)")
parser.add_argument("--company-id", required=False, help="companyId if required by your tenant")
parser.add_argument("--api-id", required=False, help="apiId (for drift analysis) - optional")
parser.add_argument("--poll-interval", type=int, default=8)
parser.add_argument("--poll-retries", type=int, default=40)
args = parser.parse_args()

SALT_URL = args.salt_url.rstrip("/")
HEADERS = {"Authorization": f"Bearer {args.salt_key}", "accept": "application/json"}

# 1) Upload OAS files: POST /v1/oas/files (multipart form) — provide 'name' and array of files
upload_url = f"{SALT_URL}/v1/oas/files"
log("Uploading OAS to", upload_url)
files = []
# Salt requires array — send repeated 'file' form parts
with open(args.oas, "rb") as fh:
    # Use field name 'file' multiple times (many implementations accept file[])
    files_payload = [("file", (os.path.basename(args.oas), fh.read(), "application/octet-stream"))]

# Build form params
data = {}
if args.company_id:
    data['companyId'] = args.company_id
# Include a name for the upload (optional)
data['name'] = f"ci-upload-{int(time.time())}"

# Because requests.File-objects must remain open, open again in correct format
multipart_files = []
fobj = open(args.oas, "rb")
multipart_files.append(("file", (os.path.basename(args.oas), fobj, "application/octet-stream")))

r = requests.post(upload_url, headers=HEADERS, files=multipart_files, data=data)
log("Upload HTTP", r.status_code)
try:
    resp = r.json()
except Exception:
    log("Non-JSON upload response:", r.text)
    raise SystemExit(1)

log("Upload response JSON:", json.dumps(resp)[:1000])

# Try to extract oas upload id
oas_id = resp.get("oasId") or resp.get("id") or resp.get("uploadId") or resp.get("data", {}).get("id")
if not oas_id:
    # maybe response is a list
    if isinstance(resp, list) and len(resp) > 0:
        first = resp[0]
        oas_id = first.get("oasId") or first.get("id") or first.get("uploadId")
if not oas_id:
    log("ERROR: Could not determine OAS upload id from response. Full response saved to salt_upload_full.json")
    with open("salt_upload_full.json", "w") as fh: fh.write(json.dumps(resp, indent=2))
    raise SystemExit(2)
log("Detected oas upload id:", oas_id)

# 2) Trigger Design Analysis: POST /v1/oas/analyses/design?oasId=<id> (from docs screenshots)
design_trigger_url = f"{SALT_URL}/v1/oas/analyses/design"
params = {"oasId": oas_id}
log("Triggering design analysis", design_trigger_url, params)
rd = requests.post(design_trigger_url, headers=HEADERS, params=params)
log("Design trigger status", rd.status_code)
try:
    rdj = rd.json()
except Exception:
    log("Design trigger non-json:", rd.text); rdj = {}
log("Design trigger response:", rdj)
design_analysis_id = rdj.get("analysisId") or rdj.get("id") or rdj.get("data", {}).get("analysisId")
if not design_analysis_id:
    # sometimes trigger returns object containing analysis id nested under data or other key
    design_analysis_id = rdj.get("data", {}).get("id")
if not design_analysis_id:
    log("WARNING: Could not extract design analysis id from trigger response. Saving response as design_trigger_full.json")
    with open("design_trigger_full.json", "w") as fh: fh.write(json.dumps(rdj, indent=2))

# 3) Trigger Drift Analysis if api-id provided: POST /v1/oas/analyses/drift?apid=<apiId>&oasId=<id>
drift_analysis_id = None
if args.api_id:
    drift_trigger_url = f"{SALT_URL}/v1/oas/analyses/drift"
    params2 = {"apId": args.api_id, "oasId": oas_id}
    log("Triggering drift analysis", drift_trigger_url, params2)
    rr = requests.post(drift_trigger_url, headers=HEADERS, params=params2)
    log("Drift trigger status", rr.status_code)
    try:
        rrj = rr.json()
    except Exception:
        log("Drift trigger non-json:", rr.text); rrj = {}
    log("Drift trigger response:", rrj)
    drift_analysis_id = rrj.get("analysisId") or rrj.get("id") or rrj.get("data", {}).get("analysisId")
    if not drift_analysis_id:
        drift_analysis_id = rrj.get("data", {}).get("id")
    if not drift_analysis_id:
        log("WARNING: Could not extract drift analysis id. Saving drift_trigger_full.json")
        with open("drift_trigger_full.json", "w") as fh: fh.write(json.dumps(rrj, indent=2))

# Poll helper
def poll_and_fetch(kind, analysis_id):
    if not analysis_id:
        log(f"No {kind} analysis id provided — skipping poll.")
        return None
    status_url = f"{SALT_URL}/v1/oas/analyses/{kind}/{analysis_id}"
    log("Polling", status_url)
    for i in range(args.poll_retries):
        r = requests.get(status_url, headers=HEADERS)
        if r.status_code >= 400:
            log(f"Polling HTTP {r.status_code}: {r.text}")
        try:
            j = r.json()
        except Exception:
            log("Non-JSON poll resp:", r.text); j = {}
        status = j.get("status") or j.get("state") or j.get("analysisStatus")
        log(f"Attempt {i+1}/{args.poll_retries} status={status}")
        if status and status.lower() in ("finished","completed","success"):
            log(f"{kind} analysis finished. Fetching full results.")
            # Now fetch full results endpoint if separate:
            fetch_url = f"{SALT_URL}/v1/oas/analyses/{kind}/{analysis_id}"
            fr = requests.get(fetch_url, headers=HEADERS)
            try:
                fj = fr.json()
            except Exception:
                log("Fetch non-json:", fr.text); fj = {}
            # save to file
            fname = f"salt_oas_{kind}_result.json"
            with open(fname, "w") as fh: fh.write(json.dumps(fj, indent=2))
            log("Saved", fname)
            return fj
        time.sleep(args.poll_interval)
    log(f"Timed out waiting for {kind} analysis {analysis_id}")
    return None

# Poll design & drift
design_result = None
drift_result = None

if design_analysis_id:
    design_result = poll_and_fetch("design", design_analysis_id)

if drift_analysis_id:
    drift_result = poll_and_fetch("drift", drift_analysis_id)

# Save whatever we have
if design_result:
    with open("salt_oas_design_result.json", "w") as fh: fh.write(json.dumps(design_result, indent=2))
if drift_result:
    with open("salt_oas_drift_result.json", "w") as fh: fh.write(json.dumps(drift_result, indent=2))

# Convert combined findings to CSV (best-effort): look for top-level arrays named 'violations', 'findings', 'items'
def extract_findings(obj):
    if not obj:
        return []
    if isinstance(obj, dict):
        # common places
        for key in ("violations","findings","items","results","issues"):
            if key in obj and isinstance(obj[key], list):
                return obj[key]
        # search nested
        for v in obj.values():
            if isinstance(v, list):
                return v
    if isinstance(obj, list):
        return obj
    return []

all_findings = []
all_findings += extract_findings(design_result) or []
all_findings += extract_findings(drift_result) or []

if all_findings:
    # normalize and save CSV
    df = pd.json_normalize(all_findings)
    csv_name = "salt_oas_result.csv"
    df.to_csv(csv_name, index=False)
    log("Wrote CSV:", csv_name)
else:
    log("No array-style findings found to convert to CSV. Saving raw JSONs for inspection.")
    # still write a small CSV with summary rows
    summary = []
    if design_result:
        summary.append({"analysis":"design","has_findings": bool(extract_findings(design_result))})
    if drift_result:
        summary.append({"analysis":"drift","has_findings": bool(extract_findings(drift_result))})
    if summary:
        pd.DataFrame(summary).to_csv("salt_oas_result.csv", index=False)
        log("Wrote summary CSV: salt_oas_result.csv")
    else:
        log("No results to write.")
