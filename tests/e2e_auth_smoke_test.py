"""E2E test for Supabase-style Auth wiring (Waled decisions #3 and #5).

Covers:
- 401 when no token is supplied on a protected endpoint
- 401 when token is expired
- 403 when role isn't authorized for the endpoint / specific rule override
- 201/200 happy paths with correctly-scoped tokens
- BR-06 override REQUIRES evidence_url (Waled decision #3) — rejected
  without it, accepted with it, and the resulting clearance shows
  overridden=True with the evidence recorded in the audit trail.
"""
import sys
import time
import requests

sys.path.insert(0, "backend")
from app.dev_tokens import mint_dev_token  # noqa: E402

BASE = "http://127.0.0.1:5055"

TOKENS = {
    "cso": mint_dev_token("u-cso"),
    "supervisor": mint_dev_token("u-sup1"),
    "officer": mint_dev_token("u-off1"),
    "guard": mint_dev_token("u-guard1"),
    "engineer": mint_dev_token("u-eng1"),
    "expired": mint_dev_token("u-sup1", ttl_seconds=-10),
}


def auth(who):
    return {"Authorization": f"Bearer {TOKENS[who]}"}


def p(title, resp):
    print(f"\n--- {title} [{resp.status_code}] ---")
    try:
        print(resp.json())
    except Exception:
        print(resp.text[:300])
    return resp


def create_ready_flight():
    """Create a flight and push it all the way to just-before-declaration,
    with an aircraft seal deliberately BROKEN so BR-06 blocks clearance —
    used to exercise the override + evidence_url requirement."""
    r = requests.post(f"{BASE}/flights", json={
        "airline_id": "AAW", "flight_number": "8U970", "aircraft_reg": "5A-ONC",
        "aircraft_type": "A330", "departure_airport": "MJI", "destination": "IST",
        "threat_level": "GREEN", "created_by": "u-sup1",
    })
    fid = r.json()["flight_id"]

    def do_checklist(code, results, signers):
        r = requests.post(f"{BASE}/flights/{fid}/checklists/{code}/start")
        iid = r.json()["instance_id"]
        requests.post(f"{BASE}/checklists/{iid}/submit", json={
            "results": results, "signatures": signers,
        })

    do_checklist("CL-01", {k: "PASS" for k in [
        "flight_deck", "fwd_entrance", "fwd_galley", "fwd_toilet", "main_cabin",
        "rear_galley_toilet", "avionics_bay", "cargo_holds", "gear_bays", "inlets_outlets"]},
        ["u-eng1", "u-off1", "u-guard1"])

    requests.post(f"{BASE}/flights/{fid}/baggage", json={
        "total_hold_bags": 50, "reconciled_bags": 50, "mismatch_count": 0,
        "screened_pct": 100, "recorded_by": "u-off1",
    })
    do_checklist("CL-02", {"count_match": "PASS", "no_show_removed": "PASS",
                           "unaccompanied_screened": "PASS", "crew_bags_matched": "PASS"}, ["u-off1"])

    requests.post(f"{BASE}/flights/{fid}/catering", json={
        "truck_id": "TRK-1", "seal_number": "SL-1", "seal_status": "INTACT",
        "manual_inspection_done": False, "checked_by": "u-off1",
    })
    do_checklist("CL-03", {"seal_match": "PASS", "seal_intact": "PASS",
                           "manual_inspection": "PASS", "receiver_signoff": "PASS"}, ["u-off1"])

    requests.post(f"{BASE}/flights/{fid}/cargo", json={
        "awb_number": "AWB-9", "consignor_status": "KNOWN", "screening_done": True,
        "accepted": True, "recorded_by": "u-off1",
    })
    do_checklist("CL-04", {"consignor_status": "PASS", "screening_if_unknown": "PASS",
                           "no_tamper_signs": "PASS"}, ["u-off1"])

    # Deliberately BROKEN seal -> BR-06 will block clearance.
    requests.post(f"{BASE}/flights/{fid}/seals", json={
        "aircraft_reg": "5A-ONC", "seal_number": "AS-BROKEN-1", "location_code": "825AR",
        "status": "BROKEN", "verified_by": "u-eng1",
    })
    do_checklist("CL-05", {"seal_numbers_match": "FAIL", "no_missing_broken": "FAIL"}, ["u-eng1"])

    return fid


def main():
    # --- 1. No token at all ---
    fid = create_ready_flight()
    r = p("Declaration with NO token (expect 401)",
          requests.post(f"{BASE}/flights/{fid}/declaration", json={}))
    assert r.status_code == 401

    # --- 2. Expired token ---
    r = p("Declaration with EXPIRED token (expect 401)",
          requests.post(f"{BASE}/flights/{fid}/declaration", json={}, headers=auth("expired")))
    assert r.status_code == 401

    # --- 3. Wrong role: guard cannot sign declaration ---
    r = p("Declaration signed by GUARD (expect 403 - role not authorized)",
          requests.post(f"{BASE}/flights/{fid}/declaration", json={}, headers=auth("guard")))
    assert r.status_code == 403

    # --- 4. Correct role but rules still block (BR-06 seal broken) ---
    r = p("Declaration signed by OFFICER (expect 409 - BR-06 blocks)",
          requests.post(f"{BASE}/flights/{fid}/declaration", json={}, headers=auth("officer")))
    assert r.status_code == 409
    br06 = [x for x in r.json()["results"] if x["rule_id"] == "BR-06"][0]
    assert br06["passed"] is False

    # --- 5. Guard attempts BR-06 override -> 403 (role not in overridable_roles) ---
    r = p("Override BR-06 by GUARD (expect 403)", requests.post(
        f"{BASE}/flights/{fid}/overrides", headers=auth("guard"),
        json={"rule_id": "BR-06", "reason": "trying anyway"}))
    assert r.status_code == 403

    # --- 6. Supervisor attempts BR-06 override WITHOUT evidence_url -> 400 ---
    r = p("Override BR-06 by SUPERVISOR, no evidence_url (expect 400)", requests.post(
        f"{BASE}/flights/{fid}/overrides", headers=auth("supervisor"),
        json={"rule_id": "BR-06", "reason": "AOG risk, seal re-verified visually, proceeding"}))
    assert r.status_code == 400
    assert "evidence_url" in r.json()["error"]

    # --- 7. Supervisor overrides BR-06 WITH evidence_url -> 201 ---
    r = p("Override BR-06 by SUPERVISOR WITH evidence_url (expect 201)", requests.post(
        f"{BASE}/flights/{fid}/overrides", headers=auth("supervisor"),
        json={"rule_id": "BR-06", "reason": "AOG risk mitigated, seal re-verified with photo evidence",
              "evidence_url": "https://storage.example/evidence/seal-AS-BROKEN-1.jpg"}))
    assert r.status_code == 201

    # --- 7b. The broken seal also auto-created a MAJOR security_incident
    # (BR-03) — separate from the BR-06 gate itself, matching AAWSM Ch.15
    # (Security Incident Review is its own stage). Overriding BR-06 does
    # NOT auto-resolve BR-03; the incident must be formally closed too. ---
    detail = requests.get(f"{BASE}/flights/{fid}").json()
    open_incidents = [i for i in detail["incidents"] if i["status"] != "CLOSED"]
    assert open_incidents, "expected an auto-created incident from the broken seal"
    inc_id = open_incidents[0]["incident_id"]
    r = p("Close the auto-created seal incident (SUPERVISOR)", requests.post(
        f"{BASE}/incidents/{inc_id}/close", headers=auth("supervisor"),
        json={"close_reason": "Reviewed alongside BR-06 override; seal replaced before departure"}))
    assert r.status_code == 200

    # --- 8. Clearance now shows BR-06 passed via override AND BR-03 clear ---
    r = p("Clearance check after override + incident close (expect fully clearable)",
          requests.get(f"{BASE}/flights/{fid}/clearance"))
    results_by_id = {x["rule_id"]: x for x in r.json()["results"]}
    assert results_by_id["BR-06"]["passed"] is True and results_by_id["BR-06"]["overridden"] is True
    assert results_by_id["BR-06"]["overridden_by"] == "u-sup1"
    assert results_by_id["BR-03"]["passed"] is True, "BR-03 should clear once the incident is closed"

    # --- 9. Now declaration should succeed with officer token ---
    r = p("Declaration signed by OFFICER after override (expect 200 CLEARED)",
          requests.post(f"{BASE}/flights/{fid}/declaration",
                        json={"declaration_text": "Cleared with BR-06 override on file"},
                        headers=auth("officer")))
    assert r.status_code == 200
    assert r.json()["security_status"] == "CLEARED"

    # --- 10. Emergency: guard can open, guard CANNOT close, supervisor can ---
    r = requests.post(f"{BASE}/flights", json={
        "airline_id": "AAW", "flight_number": "8U500", "aircraft_reg": "5A-ONX",
        "aircraft_type": "A319", "departure_airport": "MJI", "destination": "CAI",
        "threat_level": "RED", "created_by": "u-sup1",
    })
    fid2 = r.json()["flight_id"]

    r = p("Guard opens emergency (expect 201)", requests.post(
        f"{BASE}/flights/{fid2}/emergency", headers=auth("guard"),
        json={"event_type": "SUSPECT_ITEM", "notes": "found by guard"}))
    assert r.status_code == 201
    eid = r.json()["event_id"]

    r = p("Guard tries to close emergency (expect 403)",
          requests.post(f"{BASE}/emergency/{eid}/close", headers=auth("guard"), json={}))
    assert r.status_code == 403

    r = p("Supervisor closes emergency (expect 200)",
          requests.post(f"{BASE}/emergency/{eid}/close", headers=auth("supervisor"), json={}))
    assert r.status_code == 200

    print("\n=== ALL AUTH ASSERTIONS PASSED ===")


if __name__ == "__main__":
    main()
