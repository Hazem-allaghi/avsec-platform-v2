"""End-to-end smoke test for the AVSEC Platform MVP.
Run against a live server at BASE_URL.
"""
import sys
import requests

sys.path.insert(0, "backend")
from app.dev_tokens import mint_dev_token  # noqa: E402

BASE = "http://127.0.0.1:5055"
SUP_TOKEN = mint_dev_token("u-sup1")
OFF_TOKEN = mint_dev_token("u-off1")


def auth_sup():
    return {"Authorization": f"Bearer {SUP_TOKEN}"}


def auth_off():
    return {"Authorization": f"Bearer {OFF_TOKEN}"}


def p(title, resp):
    print(f"\n--- {title} [{resp.status_code}] ---")
    try:
        print(resp.json())
    except Exception:
        print(resp.text[:300])
    return resp


def main():
    # 1. Create flight
    r = p("Create flight", requests.post(f"{BASE}/flights", json={
        "airline_id": "AAW", "flight_number": "8U214", "aircraft_reg": "5A-ONA",
        "aircraft_type": "A320", "departure_airport": "MJI", "destination": "TUN",
        "threat_level": "AMBER", "created_by": "u-sup1",
    }))
    flight_id = r.json()["flight_id"]

    # 2. Early declaration must be blocked
    r = p("Early declaration (expect 409)", requests.post(
        f"{BASE}/flights/{flight_id}/declaration", json={}, headers=auth_off()))
    assert r.status_code == 409, "expected blocked declaration"

    # 3. CL-01 Aircraft search — PASS
    r = requests.post(f"{BASE}/flights/{flight_id}/checklists/CL-01/start")
    inst01 = r.json()["instance_id"]
    r = p("Submit CL-01 (PASS)", requests.post(f"{BASE}/checklists/{inst01}/submit", json={
        "results": {k: "PASS" for k in [
            "flight_deck", "fwd_entrance", "fwd_galley", "fwd_toilet", "main_cabin",
            "rear_galley_toilet", "avionics_bay", "cargo_holds", "gear_bays", "inlets_outlets"]},
        "signatures": ["u-eng1", "u-off1", "u-guard1"], "lat": 32.66, "lng": 13.16, "gps_accuracy_m": 5,
    }))
    assert r.json()["status"] == "PASSED"

    # 4. Baggage reconciliation with a MISMATCH first (must block clearance)
    p("Record baggage with mismatch=1", requests.post(f"{BASE}/flights/{flight_id}/baggage", json={
        "total_hold_bags": 80, "reconciled_bags": 79, "unaccompanied_bags": 0,
        "mismatch_count": 1, "screened_pct": 100, "recorded_by": "u-off1",
    }))
    r = requests.post(f"{BASE}/flights/{flight_id}/checklists/CL-02/start")
    inst02 = r.json()["instance_id"]
    p("Submit CL-02 (PASS attestation)", requests.post(f"{BASE}/checklists/{inst02}/submit", json={
        "results": {"count_match": "PASS", "no_show_removed": "PASS",
                    "unaccompanied_screened": "PASS", "crew_bags_matched": "PASS"},
        "signatures": ["u-off1"],
    }))

    r = p("Clearance check (expect BLOCKED on BR-02 mismatch)",
          requests.get(f"{BASE}/flights/{flight_id}/clearance"))
    br02 = [x for x in r.json()["results"] if x["rule_id"] == "BR-02"][0]
    assert br02["passed"] is False, "BR-02 should still be blocking"

    # 5. Correct the mismatch (new baggage record with mismatch=0)
    p("Record corrected baggage (mismatch=0)", requests.post(f"{BASE}/flights/{flight_id}/baggage", json={
        "total_hold_bags": 80, "reconciled_bags": 80, "unaccompanied_bags": 0,
        "mismatch_count": 0, "screened_pct": 100, "recorded_by": "u-off1",
    }))

    # 6. Catering — seal broken, no manual inspection yet (must block)
    p("Record catering seal BROKEN (no inspection)", requests.post(
        f"{BASE}/flights/{flight_id}/catering", json={
            "truck_id": "TRK-12", "seal_number": "SL-9001", "seal_status": "BROKEN",
            "manual_inspection_done": False, "checked_by": "u-off1",
        }))
    r = requests.post(f"{BASE}/flights/{flight_id}/checklists/CL-03/start")
    inst03 = r.json()["instance_id"]
    p("Submit CL-03", requests.post(f"{BASE}/checklists/{inst03}/submit", json={
        "results": {"seal_match": "PASS", "seal_intact": "FAIL",
                    "manual_inspection": "FAIL", "receiver_signoff": "PASS"},
        "signatures": ["u-off1"],
    }))
    r = p("Clearance check (expect BLOCKED on BR-04 catering seal)",
          requests.get(f"{BASE}/flights/{flight_id}/clearance"))
    br04 = [x for x in r.json()["results"] if x["rule_id"] == "BR-04"][0]
    assert br04["passed"] is False

    # 7. Redo catering after manual inspection completed
    p("Record catering after manual inspection DONE", requests.post(
        f"{BASE}/flights/{flight_id}/catering", json={
            "truck_id": "TRK-12", "seal_number": "SL-9001", "seal_status": "BROKEN",
            "manual_inspection_done": True, "checked_by": "u-off1",
        }))
    r = requests.post(f"{BASE}/flights/{flight_id}/checklists/CL-03/start")
    inst03b = r.json()["instance_id"]
    requests.post(f"{BASE}/checklists/{inst03b}/submit", json={
        "results": {"seal_match": "PASS", "seal_intact": "PASS",
                    "manual_inspection": "PASS", "receiver_signoff": "PASS"},
        "signatures": ["u-off1"],
    })

    # 8. Cargo — no cargo on this flight, mark accepted with KNOWN consignor
    p("Record cargo (KNOWN consignor)", requests.post(f"{BASE}/flights/{flight_id}/cargo", json={
        "awb_number": "AWB-001", "consignor_status": "KNOWN", "screening_done": True,
        "accepted": True, "recorded_by": "u-off1",
    }))
    r = requests.post(f"{BASE}/flights/{flight_id}/checklists/CL-04/start")
    inst04 = r.json()["instance_id"]
    requests.post(f"{BASE}/checklists/{inst04}/submit", json={
        "results": {"consignor_status": "PASS", "screening_if_unknown": "PASS", "no_tamper_signs": "PASS"},
        "signatures": ["u-off1"],
    })

    # 9. Aircraft seals — INTACT
    p("Record aircraft seal INTACT", requests.post(f"{BASE}/flights/{flight_id}/seals", json={
        "aircraft_reg": "5A-ONA", "seal_number": "AS-500", "location_code": "825AR",
        "status": "INTACT", "verified_by": "u-eng1",
    }))
    r = requests.post(f"{BASE}/flights/{flight_id}/checklists/CL-05/start")
    inst05 = r.json()["instance_id"]
    requests.post(f"{BASE}/checklists/{inst05}/submit", json={
        "results": {"seal_numbers_match": "PASS", "no_missing_broken": "PASS"},
        "signatures": ["u-eng1"],
    })

    # 10. Final clearance check — should now be clearable
    r = p("Final clearance check (expect clearable=True)",
          requests.get(f"{BASE}/flights/{flight_id}/clearance", params={"declaring_user_id": "u-sup1"}))
    assert r.json()["clearable"] is True, f"Should be clearable now: {r.json()}"

    # 11. Sign declaration -> flight CLEARED
    r = p("Sign declaration", requests.post(f"{BASE}/flights/{flight_id}/declaration", json={
        "declaration_text": "AAW security declaration — demo",
    }, headers=auth_sup()))
    assert r.status_code == 200
    assert r.json()["security_status"] == "CLEARED"

    # 12. Emergency scenario on a NEW flight — open + verify blocking, then close
    r = requests.post(f"{BASE}/flights", json={
        "airline_id": "AAW", "flight_number": "8U430", "aircraft_reg": "5A-ONB",
        "aircraft_type": "A319", "departure_airport": "MJI", "destination": "CAI",
        "threat_level": "RED", "created_by": "u-sup1",
    })
    flight2 = r.json()["flight_id"]
    r = p("Open EMERGENCY event", requests.post(f"{BASE}/flights/{flight2}/emergency", json={
        "event_type": "BOMB_THREAT", "notes": "Demo threat call received",
    }, headers=auth_sup()))
    ev_id = r.json()["event_id"]

    r = requests.post(f"{BASE}/flights/{flight2}/checklists/CL-01/start")
    assert r.status_code == 409, "checklist must be blocked while EMERGENCY open"
    print("\n--- Confirmed: checklist blocked during OPEN emergency ---")

    p("Close EMERGENCY (by supervisor)", requests.post(f"{BASE}/emergency/{ev_id}/close", json={},
      headers=auth_sup()))

    r = requests.post(f"{BASE}/flights/{flight2}/checklists/CL-01/start")
    assert r.status_code == 201, "checklist should now be startable"
    print("--- Confirmed: checklist startable after emergency closed ---")

    # 13. Audit trail sanity check
    r = p("Audit trail for flight 1 (tail)", requests.get(f"{BASE}/flights/{flight_id}/audit"))
    print(f"audit entries: {len(r.json())}")

    print("\n=== ALL ASSERTIONS PASSED ===")


if __name__ == "__main__":
    main()
