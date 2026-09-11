"""Generate the development fixture source rows for the satellite build.

The real store (data/state/) is git-ignored in federal-sales-os and invisible
here, so this script deterministically expands the one real checked-in row
(lila_fixtures/varonis_candidate_row.json) into a dev pool wide enough to
exercise every pipeline path: keeps, tier-3, rival awards, forecasts, closed
RFIs, ESI rows, and authentic-shaped near-misses with rejection reasons.

EVERY row is marked fixture: true. mint_link.py refuses to mint a real
executive link for any deck containing a fixture row unless --dev is passed.
In federal-sales-os, pool_build.py runs against the real store instead and
this file is unused.

Deterministic: same output bytes on every run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REAL_ROW = json.loads((ROOT / "lila_fixtures" / "varonis_candidate_row.json").read_text())

AGENCIES = [
    ("DEPT OF VETERANS AFFAIRS", "TECHNOLOGY ACQUISITION CENTER", "va"),
    ("DEPT OF THE ARMY", "ARMY CONTRACTING COMMAND", "army"),
    ("DEPT OF HOMELAND SECURITY", "OFFICE OF PROCUREMENT OPERATIONS", "dhs"),
    ("GENERAL SERVICES ADMINISTRATION", "FAS ITC", "gsa"),
    ("DEPT OF ENERGY", "OFFICE OF ACQUISITION MANAGEMENT", "doe"),
    ("SOCIAL SECURITY ADMINISTRATION", "OFFICE OF ACQUISITION AND GRANTS", "ssa"),
    ("DEPT OF THE TREASURY", "IRS PROCUREMENT", "treasury"),
    ("NATIONAL INSTITUTES OF HEALTH", "NITAAC", "nih"),
]

KEEP_TITLES = [
    ("Data Security Posture Management Platform", "The agency requires continuous discovery and classification of sensitive data across file shares and Microsoft 365.", 2),
    ("Insider Threat Data Analytics and Monitoring", "The Government seeks user behavior analytics over unstructured data repositories to detect insider threat activity.", 1),
    ("Unstructured Data Governance and Access Certification", "Contractor shall provide automated remediation of excessive permissions and stale access across enterprise file systems.", 1),
    ("Microsoft Purview Integration and Records Management Support", "The solution shall integrate with Microsoft Purview for records management and data lifecycle enforcement.", 2),
    ("Zero Trust Data Pillar Implementation Services", "This effort implements the data pillar of the zero trust architecture including data tagging and least privilege enforcement.", 1),
    ("Sensitive Data Discovery for CUI Compliance", "The Government requires discovery and labeling of controlled unclassified information across on-premises and cloud stores.", 2),
    ("Ransomware Detection and Recovery for File Services", "Offeror shall detect abnormal encryption behavior on file services and enable rapid recovery of affected data.", 2),
    ("SharePoint and OneDrive Permissions Audit", "The agency seeks an automated audit of SharePoint Online and OneDrive sharing links and permission inheritance.", 2),
    ("Data Access Governance Managed Service", "Contractor shall operate a managed data access governance capability including quarterly entitlement reviews.", 3),
    ("Cloud Data Loss Prevention Expansion", "The Government intends to expand data loss prevention coverage to sanctioned SaaS applications.", 3),
]

TIER3_TITLES = [
    ("Enterprise Backup Modernization with Data Classification", "The effort includes classification-aware backup tiering for unstructured data.", 3),
    ("SOC Enrichment with File Activity Telemetry", "The SOC requires file activity telemetry enrichment for its SIEM correlation rules.", 3),
    ("Records Management Program Support Services", "Support services for the records management program including retention schedule automation.", 3),
]

RIVAL_TITLES = [
    ("Data Governance Suite License Renewal", "Compass Data Systems", "The incumbent data governance suite license is renewed for the option year."),
    ("File Integrity and Audit Platform", "NorthPeak Security", "Award covers the file integrity and audit platform including maintenance."),
    ("Enterprise DLP Platform and Support", "Meridian InfoSec", "Enterprise data loss prevention platform with tier 2 support."),
    ("Cloud Access Security Broker Services", "Compass Data Systems", "CASB services covering sanctioned cloud applications."),
    ("Insider Risk Analytics Subscription", "NorthPeak Security", "Subscription award for insider risk analytics."),
]

FORECAST_TITLES = [
    ("FY27 Data Security Consolidation", "The agency forecasts a consolidation of data security tooling in FY27 second quarter."),
    ("Zero Trust Data Pillar Phase 2", "Forecasted phase 2 of the zero trust data pillar implementation."),
]

CLOSED_RFI_TITLES = [
    ("RFI: Unstructured Data Risk Assessment Tools", "Responses to this request for information regarding unstructured data risk assessment are closed."),
    ("Sources Sought: Data Classification at Scale", "This sources sought notice for data classification capabilities has closed."),
]

NEAR_MISS_ROWS = [
    ("Microsoft 365 License Reseller BPA", "Blanket purchase agreement for Microsoft 365 license resale and true-ups.", "vocab_hit_scope_unrelated", "vocabulary match on Microsoft 365; scope is license resale, not data security"),
    ("Records Storage Boxes and Shredding Services", "Physical records storage boxes, transport, and certified shredding services.", "vocab_hit_scope_unrelated", "vocabulary match on records management; scope is physical storage"),
    ("Data Center HVAC Preventive Maintenance", "Preventive maintenance for data center cooling and humidity control units.", "out_of_category_shared_terms", "shares the term data; facilities maintenance category"),
    ("SharePoint Intranet Redesign", "Redesign of the agency intranet landing pages in SharePoint Online.", "out_of_category_shared_terms", "shares SharePoint vocabulary; web design category"),
    ("Insider Threat Program Training Videos", "Production of awareness training videos for the insider threat program.", "out_of_category_shared_terms", "shares insider threat vocabulary; media production category"),
    ("Endpoint DLP Pilot (closed May 2026)", "Pilot of endpoint data loss prevention agents. Responses were due May 2026.", "expired", "real fit; response window closed before retrieval"),
    ("File Share Migration Support (closed)", "Migration of legacy file shares to cloud storage. This notice has closed.", "expired", "adjacent fit; clock already dead"),
    ("CUI Marking Handbook Printing", "Printing and distribution of the CUI marking handbook.", "vocab_hit_scope_unrelated", "vocabulary match on CUI; print services"),
]

ESI_TITLES = [
    ("ESI: Enterprise Data Security Agreement Refresh", "Enterprise software initiative refresh covering data security tooling."),
]


def _base(i: int, agency_i: int, kind: str) -> dict:
    agency, office, seal = AGENCIES[agency_i % len(AGENCIES)]
    return {
        "notice_id": f"fx{kind[:4]}{i:03d}" + "0" * 20,
        "sam_url": f"https://sam.gov/opp/fx{kind[:4]}{i:03d}/view",
        "agency": agency,
        "office": office,
        "seal_key": seal,
        "source": "lila_dev_fixture",
        "retrieved_at": "2026-08-18T15:31:03Z",
        "fixture": True,
    }


def build_rows() -> list[dict]:
    rows: list[dict] = []

    real = dict(REAL_ROW)
    real.update({
        "kind_hint": "notice",
        "description_sentence": "The Federal Retirement Thrift Investment Board seeks information on FOIA, eDiscovery, and matter management solutions integrating with Microsoft 365 and Microsoft Purview records management.",
        "contact_present": True,
        "vehicle": None,
        "dollars": None,
        "incumbent": None,
        "seal_key": "frtib",
        "fixture": True,
    })
    rows.append(real)

    for i, (title, sent, tier) in enumerate(KEEP_TITLES):
        r = _base(i, i, "notice")
        due_day = 22 + (i * 3) % 70
        r.update({
            "title": title, "notice_type": "Solicitation" if i % 3 else "Sources Sought",
            "set_aside": "No Set aside used" if i % 4 else "Total Small Business Set-Aside",
            "naics": "541519", "psc": "DA10",
            "posted": "2026-08-05", "response_due": f"2026-{9 if due_day > 31 else 8:02d}-{(due_day - 31) if due_day > 31 else due_day:02d}",
            "status": "open", "matched_term": "data security",
            "all_matched_terms": ["data security", "classification"],
            "tier": tier, "leverage_rank": (i % 5) + 1,
            "sol_number": f"FX-26-N{i:03d}", "kind_hint": "notice",
            "description_sentence": sent,
            "contact_present": i % 3 != 2, "vehicle": "GSA MAS" if i % 4 == 1 else None,
            "dollars": [None, 250000, 1200000, None, 3400000][i % 5],
            "incumbent": None,
        })
        rows.append(r)

    for i, (title, sent, tier) in enumerate(TIER3_TITLES):
        r = _base(i, i + 3, "tier3")
        r.update({
            "title": title, "notice_type": "Sources Sought", "set_aside": "No Set aside used",
            "naics": "541512", "psc": "DA01", "posted": "2026-08-10",
            "response_due": f"2026-09-{10 + i:02d}", "status": "open",
            "matched_term": "records management", "all_matched_terms": ["records management"],
            "tier": tier, "leverage_rank": i + 4, "sol_number": f"FX-26-T3{i:02d}",
            "kind_hint": "notice", "description_sentence": sent,
            "contact_present": i % 2 == 0, "vehicle": None, "dollars": None, "incumbent": None,
        })
        rows.append(r)

    for i, (title, rival, sent) in enumerate(RIVAL_TITLES):
        r = _base(i, i + 1, "rival_award")
        r.update({
            "title": title, "notice_type": "Award Notice", "set_aside": "No Set aside used",
            "naics": "511210", "psc": "7A21", "posted": "2025-09-15",
            "pop_end": f"2026-{10 + (i % 3):02d}-30", "status": "awarded",
            "matched_term": "data loss prevention", "all_matched_terms": ["data loss prevention"],
            "tier": 2, "leverage_rank": (i % 4) + 2, "sol_number": f"FX-25-RA{i:02d}",
            "kind_hint": "rival_award", "description_sentence": sent,
            "contact_present": False, "vehicle": "SEWP V" if i % 2 else None,
            "dollars": [890000, 2100000, 450000, 1600000, 720000][i], "incumbent": rival,
        })
        rows.append(r)

    for i, (title, sent) in enumerate(FORECAST_TITLES):
        r = _base(i, i + 5, "forecast")
        r.update({
            "title": title, "notice_type": "Forecast", "set_aside": "No Set aside used",
            "naics": "541519", "psc": "DA10", "posted": "2026-07-01",
            "forecast_quarter": "FY27 Q2", "status": "forecast",
            "matched_term": "data security", "all_matched_terms": ["data security"],
            "tier": 2, "leverage_rank": i + 2, "sol_number": f"FX-27-FC{i:02d}",
            "kind_hint": "forecast", "description_sentence": sent,
            "contact_present": False, "vehicle": None, "dollars": None, "incumbent": None,
        })
        rows.append(r)

    for i, (title, sent) in enumerate(CLOSED_RFI_TITLES):
        r = _base(i, i + 2, "closed_rfi")
        r.update({
            "title": title, "notice_type": "Sources Sought", "set_aside": "No Set aside used",
            "naics": "541519", "psc": "DA10", "posted": "2026-05-01",
            "response_due": "2026-06-01", "status": "closed",
            "matched_term": "data classification", "all_matched_terms": ["data classification"],
            "tier": 2, "leverage_rank": i + 3, "sol_number": f"FX-26-RFI{i:02d}",
            "kind_hint": "closed_rfi", "description_sentence": sent,
            "contact_present": True, "vehicle": None, "dollars": None, "incumbent": None,
        })
        rows.append(r)

    for i, (title, sent) in enumerate(ESI_TITLES):
        r = _base(i, i + 6, "rfq")
        r.update({
            "title": title, "notice_type": "RFQ", "set_aside": "No Set aside used",
            "naics": "511210", "psc": "7A21", "posted": "2026-08-12",
            "response_due": "2026-09-05", "status": "open",
            "matched_term": "data security", "all_matched_terms": ["data security"],
            "tier": 2, "leverage_rank": 2, "sol_number": f"FX-26-ESI{i:02d}",
            "kind_hint": "rfq", "description_sentence": sent,
            "contact_present": True, "vehicle": "ESI", "dollars": 5200000, "incumbent": None,
        })
        rows.append(r)

    for i, (title, sent, reason, rejection) in enumerate(NEAR_MISS_ROWS):
        r = _base(i, i, "near_miss")
        expired = reason == "expired"
        r.update({
            "title": title, "notice_type": "Solicitation", "set_aside": "No Set aside used",
            "naics": "561990", "psc": "R699", "posted": "2026-04-01",
            "response_due": "2026-05-15" if expired else "2026-09-10",
            "status": "closed" if expired else "open",
            "matched_term": "records management", "all_matched_terms": ["records management"],
            "tier": None, "leverage_rank": None, "sol_number": f"FX-26-NM{i:02d}",
            "kind_hint": "near_miss", "near_miss_reason": reason,
            "rejection_reason": rejection, "description_sentence": sent,
            "contact_present": i % 2 == 0, "vehicle": None, "dollars": None, "incumbent": None,
        })
        rows.append(r)

    return rows


def main() -> None:
    out = Path(__file__).parent / "fixture_source_rows.json"
    rows = build_rows()
    out.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind_hint"]] = kinds.get(r["kind_hint"], 0) + 1
    print(f"wrote {len(rows)} fixture source rows to {out}")
    for k, v in sorted(kinds.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
