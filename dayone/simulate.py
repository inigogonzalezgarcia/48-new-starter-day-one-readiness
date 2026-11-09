"""Fictional demo: Northwind Traders, a made-up distribution and commodities trading company with four sites (Madrid head office with
the trading desk, Barcelona, the Valencia warehouse and Lisbon). The check runs on Monday 9 November 2026 at 08:30, before the weekly
joiners call, for the 25 people starting between Tuesday 10 and Monday 23 November; two more start later. Every person, account,
device, ticket and number is made up. The problems are placed on purpose among the joiners who are ready."""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ORG = "Northwind Traders"
SEED = 48
DOMAIN = "northwind.example"

SETTINGS = {
    "organisation": ORG,
    "as_of": "2026-11-09 08:30",
    "horizon_days": 10,
    "lead_time_days": 10,
    "urgent_days": 3,
    "holidays": ["2026-12-08", "2026-12-25"],
    "enable_on_start": False,
    "hybrid": False,
    "mfa_own_phone_allowed": True,
    "fix_days": {"account": 1, "licence": 1, "licence_purchase": 3, "groups": 1, "access_request": 3, "access_approval": 2,
                 "access_fulfil": 1, "device_build": 2, "device_order": 5, "phone": 2, "mfa": 0, "data": 0},
    "licence_available": {},
    "sku_names": {"SPE_E3": "Microsoft 365 E3", "SPE_E5": "Microsoft 365 E5", "SPE_F1": "Microsoft 365 F3"},
    "privileged_groups": ["Domain Admins", "Enterprise Admins"],
    "privileged_patterns": ["admins", "administrators", "privileged", "pim-"],
    "owners": {"hr": "HR onboarding (Patricia Lozano)", "identity": "Service desk (Rubén Iglesias)",
               "licensing": "Microsoft 365 licensing (Rubén Iglesias)", "workplace": "Workplace (Nadia Kovač)",
               "mobile": "Mobile devices (Nadia Kovač)", "access": "Application owner", "security": "IAM (Teresa Vidal)"},
    "next_call": "2026-11-16",
}

PROFILES = {
    "profiles": [
        {"name": "Trader", "job_titles": ["Trader"], "licence": "SPE_E5",
         "groups": ["SG-Trading-Desk", "SG-MarketData-Users", "SG-Site-{site}", "SG-All-Staff"], "distribution_lists": ["DL-Trading"],
         "apps": ["Bloomberg Terminal", "Trading Platform (OMS)"], "shared_mailboxes": ["trading-confirmations"], "phone_required": True},
        {"name": "Trading Assistant", "job_titles": ["Trading Assistant"], "licence": "SPE_E3",
         "groups": ["SG-Trading-Support", "SG-Site-{site}", "SG-All-Staff"], "distribution_lists": ["DL-Trading"],
         "apps": ["Trading Platform (OMS)"], "shared_mailboxes": ["trading-confirmations"]},
        {"name": "Financial Analyst", "job_titles": ["Financial Analyst"], "licence": "SPE_E3",
         "groups": ["SG-Finance", "SG-Finance-Reports", "SG-Site-{site}", "SG-All-Staff"], "distribution_lists": ["DL-Finance"],
         "apps": ["SAP S/4HANA Finance"]},
        {"name": "Account Manager", "job_titles": ["Account Manager"], "licence": "SPE_E3",
         "groups": ["SG-Sales", "SG-CRM-Users", "SG-Site-{site}", "SG-All-Staff"], "distribution_lists": ["DL-Sales-{site}"],
         "apps": ["Dynamics 365 Sales"], "phone_required": True},
        {"name": "Warehouse Operative", "job_titles": ["Warehouse Operative"], "licence": "SPE_F1",
         "groups": ["SG-Warehouse-{site}", "SG-Site-{site}"], "apps": ["Warehouse Management System"], "mfa_required": False},
        {"name": "Warehouse Supervisor", "job_titles": ["Warehouse Supervisor"], "licence": "SPE_E3",
         "groups": ["SG-Warehouse-{site}", "SG-Warehouse-Supervisors", "SG-Site-{site}", "SG-All-Staff"],
         "apps": ["Warehouse Management System"], "phone_required": True},
        {"name": "Marketing Specialist", "job_titles": ["Marketing Specialist"], "licence": "SPE_E3",
         "groups": ["SG-Marketing", "SG-Adobe-CC-Users", "SG-Site-{site}", "SG-All-Staff"], "apps": ["Adobe Creative Cloud"]},
        {"name": "Service Desk Analyst", "job_titles": ["Service Desk Analyst"], "licence": "SPE_E3",
         "groups": ["SG-IT-ServiceDesk", "SG-Site-{site}", "SG-All-Staff"], "apps": ["Jira Service Management"],
         "privileged_allowed": ["SG-PIM-Helpdesk-Administrators"]},
        {"name": "HR Advisor", "job_titles": ["HR Advisor"], "licence": "SPE_E3", "groups": ["SG-HR", "SG-Site-{site}", "SG-All-Staff"],
         "apps": ["Workday"], "shared_mailboxes": ["hr-team"]},
    ],
    "default": {"licence": "SPE_E3", "groups": ["SG-Site-{site}", "SG-All-Staff"]},
}

M = {"trading": "javier.ortega", "fin_mad": "isabel.prieto", "fin_bcn": "jordi.puig", "fin_lis": "marta.sousa", "sales_mad": "alberto.nieto",
     "sales_bcn": "nuria.font", "sales_lis": "ana.sousa", "wh": "pablo.navarro", "mkt": "carla.mir", "it": "ruben.iglesias", "hr": "patricia.lozano"}

# employee id, name, start, site, department, title, manager key, contract, device, phone, ticket, raised
JOINERS = [
    ("N-10401", "Iván Romero", "2026-11-10", "VLC", "Operations", "Warehouse Operative", "wh", "Temporary", "None", "No", "REQ-4521", "2026-11-06"),
    ("N-10402", "Elena Castro", "2026-11-10", "MAD", "Trading", "Trading Assistant", "trading", "Permanent", "Windows laptop", "No", "REQ-4410", "2026-10-15"),
    ("N-10403", "Rui Almeida", "2026-11-10", "LIS", "Sales", "Account Manager", "sales_lis", "Permanent", "Windows laptop", "Yes", "REQ-4428", "2026-10-20"),
    ("N-10404", "Marta Gil", "2026-11-11", "VLC", "Operations", "Warehouse Supervisor", "wh", "Permanent", "Windows laptop", "Yes", "REQ-4433", "2026-10-21"),
    ("N-10405", "Sergio Pastor", "2026-11-12", "BCN", "Finance", "Financial Analyst", "fin_bcn", "Permanent", "Windows laptop", "No", "REQ-4437", "2026-10-22"),
    ("N-10406", "Laia Vidal", "2026-11-13", "BCN", "Marketing", "Marketing Specialist", "mkt", "Permanent", "MacBook", "No", "REQ-4441", "2026-10-23"),
    ("N-10407", "Daniel Moreno", "2026-11-16", "MAD", "Trading", "Trader", "trading", "Permanent", "Windows laptop", "Yes", "REQ-4444", "2026-10-23"),
    ("N-10408", "Clara Benítez", "2026-11-16", "MAD", "Finance", "Financial Analyst", "fin_mad", "Permanent", "Windows laptop", "No", "REQ-4446", "2026-10-26"),
    ("N-10409", "Pau Serra", "2026-11-16", "BCN", "Finance", "Financial Analyst", "fin_bcn", "Permanent", "Windows laptop", "No", "REQ-4447", "2026-10-26"),
    ("N-10410", "Nuno Costa", "2026-11-16", "LIS", "HR", "HR Advisor", "hr", "Permanent", "Windows laptop", "No", "REQ-4449", "2026-10-27"),
    ("N-10411", "Andrea Molina", "2026-11-16", "MAD", "IT", "Service Desk Analyst", "it", "Permanent", "Windows laptop", "No", "REQ-4450", "2026-10-27"),
    ("N-10412", "Hugo Herrera", "2026-11-16", "VLC", "Operations", "Warehouse Operative", "wh", "Temporary", "None", "No", "REQ-4452", "2026-10-28"),
    ("N-10413", "Sara León", "2026-11-16", "MAD", "Sales", "Account Manager", "sales_mad", "Permanent", "Windows laptop", "Yes", "REQ-4453", "2026-10-28"),
    ("N-10414", "Joana Ferreira", "2026-11-17", "LIS", "Finance", "Financial Analyst", "fin_lis", "Permanent", "Windows laptop", "No", "REQ-4456", "2026-10-29"),
    ("N-10342", "Lucía Ferrer", "2026-11-18", "MAD", "Sales", "Account Manager", "sales_mad", "Permanent", "Windows laptop", "Yes", "REQ-4460", "2026-10-30"),
    ("N-10416", "Óscar Rubio", "2026-11-19", "BCN", "Sales", "Account Manager", "sales_bcn", "Permanent", "Windows laptop", "Yes", "REQ-4462", "2026-10-30"),
    ("N-10417", "Irene Campos", "2026-11-20", "MAD", "HR", "HR Advisor", "hr", "Fixed term", "Windows laptop", "No", "REQ-4465", "2026-11-02"),
    ("N-10418", "Tomás Delgado", "2026-11-23", "MAD", "Trading", "Trading Assistant", "trading", "Permanent", "Windows laptop", "No", "REQ-4468", "2026-11-03"),
    ("N-10419", "Beatriz Ortiz", "2026-11-23", "MAD", "Finance", "Financial Analyst", "fin_mad", "Permanent", "Windows laptop", "No", "REQ-4469", "2026-11-03"),
    ("N-10420", "Gonçalo Pires", "2026-11-23", "LIS", "Sales", "Account Manager", "sales_lis", "Permanent", "Windows laptop", "No", "REQ-4471", "2026-11-04"),
    ("N-10421", "Nerea Vega", "2026-11-23", "BCN", "Finance", "Financial Analyst", "fin_bcn", "Permanent", "Windows laptop", "No", "REQ-4472", "2026-11-04"),
    ("N-10422", "Raquel Soto", "2026-11-23", "VLC", "Operations", "Warehouse Operative", "wh", "Temporary", "None", "No", "REQ-4474", "2026-11-04"),
    ("N-10423", "Miguel Ángel Cano", "2026-11-23", "VLC", "Operations", "Warehouse Operative", "wh", "Temporary", "None", "No", "REQ-4475", "2026-11-04"),
    ("N-10424", "Carlos Ibarra", "2026-11-23", "MAD", "Trading", "Trader", "trading", "Permanent", "Windows laptop", "Yes", "REQ-4476", "2026-11-05"),
    ("N-10425", "Inês Matos", "2026-11-23", "LIS", "Finance", "Financial Analyst", "fin_lis", "Permanent", "Windows laptop", "No", "REQ-4478", "2026-11-05"),
    ("N-10426", "Alba Romero", "2026-11-24", "MAD", "Finance", "Financial Analyst", "fin_mad", "Permanent", "Windows laptop", "No", "REQ-4480", "2026-11-06"),
    ("N-10427", "David Ruiz", "2026-12-01", "BCN", "Sales", "Account Manager", "sales_bcn", "Permanent", "Windows laptop", "Yes", "REQ-4482", "2026-11-06"),
]
LOCATION = {"MAD": "ES", "BCN": "ES", "VLC": "ES", "LIS": "PT"}
NO_ACCOUNT_YET = {"N-10426", "N-10427"}
E3_PENDING = {"N-10418", "N-10419", "N-10420", "N-10421"}            # the E3 pool has 2 free for 5 joiners: short by 3
NO_DEVICE_YET = {"N-10418", "N-10419", "N-10406"}                   # Laia's MacBook: none in stock at Barcelona
AUTOPILOT_ONLY = {"N-10421"}                                         # registered for her, enrols on the first sign-in
STOCK = [
    ["MAD", "Windows laptop", "Dell Latitude 7450", 8, 2], ["MAD", "MacBook", "MacBook Air 13 M4", 2, 0], ["MAD", "Phone", "iPhone 16e", 4, 1],
    ["BCN", "Windows laptop", "Dell Latitude 7450", 3, 0], ["BCN", "MacBook", "MacBook Air 13 M4", 1, 1], ["BCN", "Phone", "iPhone 16e", 2, 0],
    ["VLC", "Windows laptop", "Dell Latitude 5550", 2, 0], ["VLC", "Phone", "Samsung Galaxy XCover7", 3, 0],
    ["LIS", "Windows laptop", "Dell Latitude 7450", 2, 0], ["LIS", "Phone", "iPhone 16e", 1, 0],
]
LICENCES = [["SPE_E3", "05e9a617-0261-4cee-bb44-138d3ef5d965", 420, 418], ["SPE_E5", "06ebc4ee-1bb5-47dd-8120-11324bc54e06", 60, 57],
            ["SPE_F1", "66b55226-6b4f-492c-910c-a3b7a3c9d993", 150, 142]]


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _upn(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    parts = s.split()
    return f"{parts[0]}.{parts[-1]}@{DOMAIN}"


def _profile(title: str) -> dict:
    return next(p for p in PROFILES["profiles"] if title in p["job_titles"])


def _sub(items: list, site: str) -> list:
    return [x.replace("{site}", site) for x in items]


def build(rnd: random.Random) -> dict:
    joiners, accounts, devices, autopilot, access = [], [], [], [], []
    n_dev = {"MAD": 405, "BCN": 212, "VLC": 118, "LIS": 87}
    for eid, name, start, site, dept, title, mk, contract, dev, phone, ticket, raised in JOINERS:
        mgr = f"{M[mk]}@{DOMAIN}"
        joiners.append([eid, name, start, site, dept, title, mgr, contract, dev, phone, ticket, raised])
        if eid in NO_ACCOUNT_YET:
            continue
        p = _profile(title)
        upn = _upn(name)
        if eid == "N-10342":
            upn = f"lucia.ferrer2@{DOMAIN}"
        created = datetime.strptime(raised, "%Y-%m-%d") + timedelta(days=rnd.randint(0, 2), hours=rnd.randint(9, 17), minutes=rnd.randint(0, 59))
        created = min(created, datetime(2026, 11, 6, 17, 40))
        lic = "" if eid in E3_PENDING else p["licence"]
        groups = _sub(p["groups"], site) + _sub(p.get("distribution_lists", []), site)
        loc = LOCATION[site]
        entra_mgr = mgr
        if eid == "N-10401":                                        # raised two working days before the start: groups not done yet
            groups = [g for g in groups if not g.startswith("SG-Warehouse")]
        if eid == "N-10404":                                        # HR changed the manager after the account was created
            entra_mgr = f"carmen.ruiz@{DOMAIN}"
        if eid == "N-10408":                                        # created by copying a model user who had moved from IT
            groups = groups + ["SG-IT-ServiceDesk", "SG-Role-Exchange-Administrators"]
        if eid == "N-10409":                                        # no usage location: the E3 assignment failed
            loc, lic = "", ""
        if eid == "N-10411":
            groups = groups + ["SG-PIM-Helpdesk-Administrators"]
        accounts.append([upn, name, eid, "True", created.strftime("%Y-%m-%dT%H:%M:%SZ"), dept, title, entra_mgr, loc, lic, ";".join(groups),
                         0, "", "False"])
        # devices
        if dev != "None" and eid not in NO_DEVICE_YET:
            serial = "".join(rnd.choice("0123456789BCDFGHJKLMNPQRSTVWXYZ") for _ in range(7))
            if eid in AUTOPILOT_ONLY:
                autopilot.append([serial, f"{site}-LAPTOP", upn, "notContacted", "Latitude 7450"])
            else:
                n_dev[site] += 1
                mac = dev == "MacBook"
                bad = eid == "N-10402"                              # enrolled, BitLocker still pending
                devices.append([f"{site}-{'M' if mac else 'L'}{n_dev[site]:04d}", serial, upn, "macOS" if mac else "Windows",
                                "MacBook Air 13 M4" if mac else ("Latitude 5550" if site == "VLC" else "Latitude 7450"),
                                "noncompliant" if bad else "compliant", "managed",
                                (datetime(2026, 11, 6, 8) + timedelta(hours=rnd.randint(0, 70))).strftime("%Y-%m-%dT%H:%M:%SZ"), "company",
                                "False" if bad else "True"])
        if phone == "Yes":
            serial = "".join(rnd.choice("0123456789BCDFGHJKLMNPQRSTVWXYZ") for _ in range(10))
            android = site == "VLC"
            devices.append([f"{site}-P{rnd.randint(100, 999)}", serial, upn, "Android" if android else "iOS",
                            "Galaxy XCover7" if android else "iPhone 16e", "compliant", "managed",
                            (datetime(2026, 11, 5, 9) + timedelta(hours=rnd.randint(0, 90))).strftime("%Y-%m-%dT%H:%M:%SZ"), "company", "True"])
        # access requests
        for item in p.get("apps", []):
            status, approver = "Fulfilled", f"{M[mk]}@{DOMAIN}"
            if eid == "N-10401":
                status = "Pending approval"
            if eid == "N-10407" and item == "Bloomberg Terminal":
                status, approver = "Pending approval", f"market-data@{DOMAIN}"
            if eid == "N-10418":
                status = "Approved"
            access.append([eid, upn, item, "Application", status, f"ACC-{7100 + len(access)}", approver])
        for item in p.get("shared_mailboxes", []):
            access.append([eid, upn, item, "Shared mailbox", "Fulfilled", f"ACC-{7100 + len(access)}", f"{M[mk]}@{DOMAIN}"])
    # the rehire: Lucía worked in Sales until 2024; her old account is disabled and has the same employeeId
    accounts.append([f"lucia.ferrer@{DOMAIN}", "Lucía Ferrer", "N-10342", "False", "2023-03-06T09:12:00Z", "Sales", "Sales Executive",
                     f"alberto.nieto@{DOMAIN}", "ES", "", "", 2, "", "False"])
    accounts.sort(key=lambda r: r[0])
    devices.sort(key=lambda r: r[0])
    return {"joiners": joiners, "accounts": accounts, "devices": devices, "autopilot": autopilot, "access": access}


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(SEED)
    b = build(rnd)
    _w(folder / "joiners.csv", ["EmployeeId", "Name", "StartDate", "Site", "Department", "JobTitle", "Manager", "ContractType", "DeviceType",
                                "Phone", "Ticket", "Raised"], b["joiners"])
    _w(folder / "accounts.csv", ["UserPrincipalName", "DisplayName", "EmployeeId", "AccountEnabled", "CreatedDateTime", "Department",
                                 "JobTitle", "Manager", "UsageLocation", "AssignedLicenses", "Groups", "MfaMethods", "TemporaryAccessPass",
                                 "OnPremisesSyncEnabled"], b["accounts"])
    _w(folder / "devices.csv", ["DeviceName", "SerialNumber", "UserPrincipalName", "OperatingSystem", "Model", "ComplianceState",
                                "ManagementState", "LastSyncDateTime", "ManagedDeviceOwnerType", "IsEncrypted"], b["devices"])
    _w(folder / "autopilot.csv", ["SerialNumber", "GroupTag", "UserPrincipalName", "EnrollmentState", "Model"], b["autopilot"])
    _w(folder / "licences.csv", ["SkuPartNumber", "SkuId", "Enabled", "ConsumedUnits"], LICENCES)
    _w(folder / "stock.csv", ["Site", "DeviceType", "Model", "InStock", "Reserved"], STOCK)
    _w(folder / "access_requests.csv", ["EmployeeId", "UserPrincipalName", "Item", "Kind", "Status", "Ticket", "Approver"], b["access"])
    (folder / "role_profiles.json").write_text(json.dumps(PROFILES, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder


__all__ = ["write", "ORG", "SETTINGS", "PROFILES"]
