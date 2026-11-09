import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from dayone import cli
from dayone.checks import AT_RISK, BLOCKED, BLOCKER, INFO, READY, RISK, check_joiner, review, run_all, summary
from dayone.model import (Access, Account, Data, Device, Joiner, Profile, Stock, add_working, load, load_accounts, load_devices,
                          load_joiners, load_licences, settings_from_dict, working_days)

AS_OF = datetime(2026, 11, 9, 8, 30)       # a Monday


def write(path: Path, header: list[str], rows: list[list]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


PROFILE = Profile("Analyst", ["Analyst"], [], "SPE_E3", ["SG-Finance", "SG-Site-{site}"], ["DL-Finance"], ["SAP"], ["finance-team"])


def joiner(eid="E1", start=date(2026, 11, 23), title="Analyst", device="windows", phone=False, raised=date(2026, 10, 1), site="MAD",
           manager="boss@contoso.example", department="Finance", name="Ana Ruiz") -> Joiner:
    return Joiner(eid, name, start, site, department, title, manager, "Permanent", device, phone, "REQ-1", raised)


def account(eid="E1", upn="ana.ruiz@contoso.example", **kw) -> Account:
    base = dict(name="Ana Ruiz", employee_id=eid, enabled=True, created=datetime(2026, 11, 2, 10), department="Finance", title="Analyst",
                manager="boss@contoso.example", usage_location="ES", licences=["SPE_E3"], groups=["SG-Finance", "SG-Site-MAD", "DL-Finance"],
                mfa=0, tap=None, synced=None)
    base.update(kw)
    return Account(upn, **base)


def laptop(upn="ana.ruiz@contoso.example", **kw) -> Device:
    name = kw.pop("name", "MAD-L0001")
    base = dict(serial="S1", upn=upn, os="Windows", model="Latitude 7450", compliance="compliant", management="managed")
    base.update(kw)
    return Device(name, **base)


def access(eid="E1", **states) -> list[Access]:
    st = {"SAP": "Fulfilled", "finance-team": "Fulfilled", **states}
    return [Access(k, eid, "", "shared mailbox" if "team" in k else "app", v, f"ACC-{n}", "boss@contoso.example") for n, (k, v) in
            enumerate(st.items()) if v is not None]


def data(joiners=(), accounts=(), devices=(), stock=None, access_=None, profiles=(PROFILE,), default=None, **raw) -> Data:
    d = Data(settings_from_dict(raw), AS_OF, list(joiners) or [joiner()], list(profiles), default, list(accounts), list(devices), stock,
             access_)
    d.sources = {"joiners.csv": len(d.joiners), "accounts.csv": len(d.accounts)}
    return d


def one(d: Data, j: Joiner | None = None):
    from collections import Counter
    return check_joiner(d, j or d.joiners[0], {"lic": Counter(), "dev": Counter()})


def codes(r) -> dict:
    return {g.code: g.severity for g in r.gaps}


class TestLoading(unittest.TestCase):
    def test_hr_graph_and_jamf_columns(self):
        with tempfile.TemporaryDirectory() as t:
            jn = write(Path(t) / "j.csv", ["Employee ID", "Full name", "Start date", "Location", "Department", "Job title", "Line manager",
                                           "Laptop", "Mobile", "Request", "Requested on"],
                       [["E1", "Ana Ruiz", "23/11/2026", "mad", "Finance", "Analyst", "Boss@Contoso.example", "MacBook Pro", "Yes", "REQ-1",
                         "2026-10-01"], ["", "No id", "2026-11-23", "MAD", "", "", "", "", "", "", ""]])
            ac = write(Path(t) / "a.csv", ["UserPrincipalName", "EmployeeId", "AccountEnabled", "CreatedDateTime", "UsageLocation",
                                           "AssignedLicenses", "Groups", "MfaMethods", "TemporaryAccessPass", "OnPremisesSyncEnabled"],
                       [["Ana.Ruiz@contoso.example", "E1", "True", "2026-11-02T10:15:00Z", "es", "spe_e3;SPE_E5", "SG-A; SG-B", "2", "Yes", ""]])
            jf = write(Path(t) / "d.csv", ["Computer Name", "Serial Number", "Email Address", "Operating System", "Model", "Last Check-in"],
                       [["MAD-M001", "c02x1", "ana.ruiz@contoso.example", "macOS 15.6", "MacBook Air", "2026-11-06 10:00"]])
            lc = write(Path(t) / "l.csv", ["SkuPartNumber", "Enabled", "ConsumedUnits"], [["SPE_E3", "420", "418"]])
            js, acs, dev, lic = load_joiners(jn), load_accounts(ac), load_devices(jf, "Jamf"), load_licences(lc)
        self.assertEqual(len(js), 1)
        self.assertEqual((js[0].start, js[0].site, js[0].device, js[0].phone, js[0].manager),
                         (date(2026, 11, 23), "MAD", "mac", True, "boss@contoso.example"))
        a = acs[0]
        self.assertEqual((a.upn, a.usage_location, a.licences, a.groups, a.mfa, a.tap, a.synced),
                         ("ana.ruiz@contoso.example", "ES", ["SPE_E3", "SPE_E5"], ["SG-A", "SG-B"], 2, True, None))
        self.assertEqual(a.created, datetime(2026, 11, 2, 10, 15))
        self.assertEqual((dev[0].kind, dev[0].serial, dev[0].source, dev[0].enrolled), ("mac", "C02X1", "Jamf", True))
        self.assertEqual(lic, {"SPE_E3": 2})

    def test_working_days_countdown_and_holidays(self):
        hol = {date(2026, 11, 16)}
        self.assertEqual(working_days(date(2026, 11, 9), date(2026, 11, 10), set()), 1)      # starts tomorrow: today is left
        self.assertEqual(working_days(date(2026, 11, 9), date(2026, 11, 23), set()), 10)
        self.assertEqual(working_days(date(2026, 11, 9), date(2026, 11, 23), hol), 9)
        self.assertEqual(add_working(date(2026, 11, 23), -3, set()), date(2026, 11, 18))
        self.assertEqual(add_working(date(2026, 11, 17), -1, hol), date(2026, 11, 13))
        d = data(joiners=[joiner(start=date(2026, 11, 23)), joiner("E2", start=date(2026, 11, 24)), joiner("E3", start=date(2026, 11, 6))])
        rv = review(d)
        self.assertEqual([r.joiner.employee_id for r in rv["results"]], ["E1"])
        self.assertEqual(([j.employee_id for j in rv["later"]], [j.employee_id for j in rv["started"]]), (["E2"], ["E3"]))


class TestChecks(unittest.TestCase):
    def test_late_request_and_the_urgent_window(self):
        j = joiner(start=date(2026, 11, 11), raised=date(2026, 11, 6))      # 3 working days of lead time, starts in 2
        r = one(data(joiners=[j], accounts=[account(groups=["SG-Site-MAD", "DL-Finance"])], devices=[laptop()], access_=access()), j)
        self.assertEqual(codes(r)["REQ-LATE"], RISK)
        self.assertEqual(codes(r)["GRP-MISSING"], BLOCKER)                  # a 1-day fix, but inside the 3-day urgent window
        self.assertEqual(r.status, BLOCKED)
        far = joiner(start=date(2026, 11, 23))
        r = one(data(joiners=[far], accounts=[account(groups=["SG-Site-MAD", "DL-Finance"])], devices=[laptop()], access_=access()), far)
        self.assertEqual((codes(r), r.status), ({"GRP-MISSING": RISK}, AT_RISK))
        self.assertEqual(r.gaps[0].due, date(2026, 11, 20))

    def test_account_missing_disabled_and_matched_by_name(self):
        r = one(data())
        self.assertIn("ACC-MISSING", codes(r))
        self.assertIn("LIC-NONE", codes(r))
        r = one(data(accounts=[account(enabled=False)], devices=[laptop()]))
        self.assertIn("ACC-DISABLED", codes(r))
        r = one(data(accounts=[account(enabled=False)], devices=[laptop()], enable_on_start=True))
        self.assertNotIn("ACC-DISABLED", codes(r))
        r = one(data(accounts=[account(eid="")], devices=[laptop()]))
        self.assertEqual(r.account.upn, "ana.ruiz@contoso.example")
        self.assertEqual(codes(r), {"ACC-NOID": RISK})

    def test_rehire_reuses_the_disabled_account_and_flags_a_duplicate(self):
        old = account(upn="ana.ruiz@contoso.example", enabled=False, created=datetime(2023, 3, 6), licences=[], groups=[])
        r = one(data(accounts=[old]))
        self.assertIn("ACC-REHIRE", codes(r))
        self.assertNotIn("ACC-MISSING", codes(r))
        self.assertIn("Mar 2023", r.gaps[0].detail + "".join(g.detail for g in r.gaps))
        new = account(upn="ana.ruiz2@contoso.example")
        r = one(data(accounts=[old, new], devices=[laptop("ana.ruiz2@contoso.example")]))
        self.assertEqual(r.account.upn, "ana.ruiz2@contoso.example")
        self.assertEqual(codes(r), {"ACC-DUPLICATE": RISK})

    def test_department_manager_usage_location_and_cloud_only(self):
        a = account(department="Sales", manager="old.boss@contoso.example", usage_location="", licences=[], synced=False)
        r = one(data(accounts=[a], devices=[laptop()], hybrid=True))
        c = codes(r)
        for k in ("ACC-DEPT", "ACC-MANAGER", "ACC-USAGELOC", "ACC-CLOUDONLY", "LIC-NONE"):
            self.assertIn(k, c)
        self.assertIn("cannot be assigned", next(g.detail for g in r.gaps if g.code == "ACC-USAGELOC"))
        self.assertIn("no usage location", next(g.detail for g in r.gaps if g.code == "LIC-NONE"))

    def test_licence_wrong_extra_and_the_pool(self):
        r = one(data(accounts=[account(licences=["SPE_F1"])], devices=[laptop()]))
        self.assertEqual(codes(r), {"LIC-WRONG": RISK})
        r = one(data(accounts=[account(licences=["SPE_E3", "SPE_E5"])], devices=[laptop()]))
        self.assertEqual(codes(r), {"LIC-EXTRA": RISK})
        js = [joiner(f"E{i}", start=date(2026, 11, 16 + (i > 1) * 7), name=f"P{i}") for i in range(1, 5)]
        accs = [account(f"E{i}", f"p{i}@contoso.example", name=f"P{i}", licences=[]) for i in range(1, 5)]
        devs = [laptop(f"p{i}@contoso.example", name=f"L{i}") for i in range(1, 5)]
        d = data(joiners=js, accounts=accs, devices=devs, licence_available={"SPE_E3": 2})
        rv = review(d)
        pool = [r.joiner.employee_id for r in rv["results"] if "LIC-POOL" in codes(r)]
        self.assertEqual(pool, ["E3", "E4"])                                # the earliest starts get the free units
        lf = rv["licences"][0]
        self.assertEqual((lf["to_assign"], lf["available"], lf["short"]), (4, 2, 2))
        f = next(x for x in run_all(d, rv) if x.code == "LIC-POOL")
        self.assertIn("short by 2", f.detail)

    def test_groups_lists_and_privileged_groups_from_a_model_user(self):
        a = account(groups=["SG-Site-MAD", "SG-Role-Exchange-Administrators", "Domain Admins", "SG-PIM-Helpdesk-Administrators"])
        p = Profile("Analyst", ["Analyst"], [], "SPE_E3", ["SG-Finance", "SG-Site-{site}"], ["DL-Finance"],
                    privileged_allowed=["SG-PIM-Helpdesk-Administrators"])
        r = one(data(accounts=[a], devices=[laptop()], profiles=[p]))
        c = codes(r)
        self.assertEqual((c["GRP-MISSING"], c["GRP-DL"], c["GRP-PRIV"]), (RISK, RISK, BLOCKER))   # privileged is a blocker at any distance
        priv = next(g for g in r.gaps if g.code == "GRP-PRIV")
        self.assertIn("SG-Role-Exchange-Administrators, Domain Admins", priv.detail)
        self.assertNotIn("Helpdesk", priv.detail)
        self.assertEqual(r.status, BLOCKED)

    def test_access_requests_states(self):
        base = dict(accounts=[account()], devices=[laptop()])
        self.assertEqual(codes(one(data(access_=access(SAP=None), **base))), {"APP-NOREQ": RISK})
        self.assertEqual(codes(one(data(access_=access(SAP="Pending approval"), **base))), {"APP-PENDING": RISK})
        self.assertEqual(codes(one(data(access_=access(SAP="Approved"), **base))), {"APP-APPROVED": RISK})
        self.assertEqual(codes(one(data(access_=access(SAP="Rejected"), **base))), {"APP-REJECTED": RISK})
        self.assertEqual(codes(one(data(access_=access(**{"finance-team": "Requested"}), **base))), {"MBX-PENDING": RISK})
        self.assertEqual(codes(one(data(access_=access(), **base))), {})
        self.assertEqual(codes(one(data(**base))), {})                      # no access_requests.csv: not checked

    def test_devices_stock_platform_compliance_and_autopilot(self):
        stock = [Stock("MAD", "windows", "Latitude 7450", 3, 2), Stock("MAD", "mac", "MacBook Air", 0, 0), Stock("BCN", "mac", "MacBook Air", 2, 0)]
        r = one(data(accounts=[account()], stock=stock))
        self.assertEqual(codes(r), {"DEV-NONE": RISK})
        self.assertIn("1 free in stock at MAD", r.gaps[0].detail)
        mac = joiner(device="mac", start=date(2026, 11, 13))                # 4 working days left, an order takes 5
        r = one(data(joiners=[mac], accounts=[account()], stock=stock), mac)
        self.assertEqual(codes(r), {"DEV-NOSTOCK": BLOCKER})
        self.assertIn("free elsewhere: MacBook Air at BCN", r.gaps[0].detail)
        r = one(data(joiners=[mac], accounts=[account()], devices=[laptop()]), mac)
        self.assertEqual(codes(r), {"DEV-PLATFORM": RISK})
        r = one(data(accounts=[account()], devices=[laptop(compliance="noncompliant", encrypted=False)]))
        self.assertEqual(codes(r), {"DEV-NONCOMPLIANT": RISK})
        self.assertIn("not encrypted", r.gaps[0].detail)
        ap = Device("S9", "S9", "ana.ruiz@contoso.example", "Windows", "", "", "notContacted", source="Autopilot", enrolled=False)
        self.assertEqual(codes(one(data(accounts=[account()], devices=[ap]))), {})

    def test_phone_and_mfa_on_day_one(self):
        p = Profile("Sales", ["Analyst"], [], "SPE_E3", ["SG-Finance", "SG-Site-{site}"], ["DL-Finance"], phone_required=True)
        r = one(data(accounts=[account()], devices=[laptop()], profiles=[p]))
        self.assertEqual(codes(r), {"PHN-ROLE": RISK})
        soon = joiner(start=date(2026, 11, 10))
        r = one(data(joiners=[soon], accounts=[account()], devices=[laptop()]), soon)
        self.assertEqual(codes(r), {"MFA-TAP": INFO})
        self.assertEqual(r.status, READY)                                   # a step for the day itself, not a gap
        r = one(data(joiners=[soon], accounts=[account()], devices=[laptop()], mfa_own_phone_allowed=False), soon)
        self.assertEqual(codes(r), {"MFA-NODEVICE": BLOCKER})
        r = one(data(joiners=[soon], accounts=[account(tap=True)], devices=[laptop()], mfa_own_phone_allowed=False), soon)
        self.assertEqual(codes(r), {})

    def test_profile_matching_and_site_placeholders(self):
        dept = Profile("Finance", [], ["Finance"], "SPE_E3", ["SG-Finance-{site}"])
        default = Profile("Default", [], [], "SPE_F1", ["SG-All-Staff"])
        d = data(joiners=[joiner(title="Controller", site="BCN")], profiles=[PROFILE, dept], default=default)
        self.assertEqual(d.profile(d.joiners[0]).name, "Finance")
        self.assertEqual(dept.expand(dept.groups, d.joiners[0]), ["SG-Finance-BCN"])
        self.assertEqual(d.profile(joiner(title="Driver", department="Logistics")).name, "Default")
        self.assertEqual(d.profile(joiner()).name, "Analyst")


class TestEndToEnd(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            hashes = []
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                h = {n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS}
                h.update({n.name: hashlib.sha1(n.read_bytes()).hexdigest() for n in (Path(t) / f"data{k}").iterdir()})
                hashes.append(h)
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(json.loads((Path(t) / "data0" / "settings.json").read_text(encoding="utf-8"))["as_of"], "2026-11-09 08:30")
            self.assertLess(sum(p.stat().st_size for p in (Path(t) / "data0").iterdir()), 200_000)
            d = load(Path(t) / "data0")
        rv = review(d)
        by = {r.joiner.name: r for r in rv["results"]}
        self.assertEqual(len(rv["results"]), 25)
        planted = {"Iván Romero": "REQ-LATE", "Pau Serra": "ACC-USAGELOC", "Lucía Ferrer": "ACC-DUPLICATE", "Laia Vidal": "DEV-NOSTOCK",
                   "Elena Castro": "DEV-NONCOMPLIANT", "Daniel Moreno": "APP-PENDING", "Clara Benítez": "GRP-PRIV", "Marta Gil": "ACC-MANAGER",
                   "Tomás Delgado": "LIC-POOL"}
        for name, code in planted.items():
            self.assertIn(code, codes(by[name]), name)
        self.assertIn("Bloomberg Terminal", next(g.detail for g in by["Daniel Moreno"].gaps if g.code == "APP-PENDING"))
        e3 = next(x for x in rv["licences"] if x["sku"] == "SPE_E3")
        self.assertEqual(e3["short"], 3)
        sm = summary(d, rv, run_all(d, rv))
        self.assertEqual((sm["status"][READY], sm["status"][AT_RISK], sm["status"][BLOCKED]), (13, 8, 4))
        self.assertEqual(by["Nerea Vega"].devices[0].source, "Autopilot")

    def test_pack_and_csv_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["demo", "--data", str(Path(t) / "d"), "--out", str(Path(t) / "o")]), 0)
            o = Path(t) / "o"
            pack = (o / "day-one-pack.md").read_text(encoding="utf-8")
            html = (o / "report.html").read_text(encoding="utf-8")
            st, gaps, act, fd = rows(o / "joiner-status.csv"), rows(o / "gaps.csv"), rows(o / "actions.csv"), rows(o / "findings.csv")
            dev = rows(o / "device-forecast.csv")
        for h in ("## Agenda", "## Headlines", "## Fix first", "## Joiners by start date", "## Open gaps", "## Sites", "## Licences",
                  "## Devices", "## Scope and evidence", "## Sign-off"):
            self.assertIn(h, pack)
        self.assertIn("short by 3", pack)
        self.assertEqual(len(st), 25)
        self.assertEqual({r["status"] for r in st}, {READY, AT_RISK, BLOCKED})
        self.assertTrue(all(a["done"] == "" and a["owner"] and a["due"] for a in act))
        self.assertEqual(fd[0]["severity"], "blocker")
        self.assertTrue(any(r["site"] == "BCN" and r["type"] == "MacBook" and r["short"] == "1" for r in dev))
        self.assertTrue(any(g["code"] == "MFA-TAP" and g["severity"] == "info" for g in gaps))
        self.assertIn("Countdown", html)
        self.assertNotIn("\r", pack)

    def test_review_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            self.assertEqual(cli.main(["review", "--out", str(Path(t) / "o")]), 2)
            write(Path(t) / "joiners.csv", ["EmployeeId", "Name", "StartDate", "Site", "JobTitle"], [["E1", "Ana Ruiz", "2026-11-16", "MAD", "Analyst"]])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)          # no accounts.csv
            write(Path(t) / "accounts.csv", ["UserPrincipalName", "EmployeeId", "AccountEnabled"], [["ana@contoso.example", "E1", "True"]])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o"), "--as-of", "2026-11-09"]), 0)
            st = rows(Path(t) / "o" / "joiner-status.csv")
        self.assertEqual((st[0]["working_days_left"], st[0]["status"], st[0]["device_status"]), ("5", READY, "ok"))


if __name__ == "__main__":
    unittest.main()
