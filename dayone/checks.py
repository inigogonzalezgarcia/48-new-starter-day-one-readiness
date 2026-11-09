"""The day-one readiness checks for everyone starting in the next working days: request lead time; the account (missing, disabled, a
rehire with an old account, a duplicate, no employeeId, department or manager different from HR, no usage location, cloud-only in a
hybrid directory); the licence (none, the wrong SKU, an extra SKU, the pool short); groups and access (role groups and distribution
lists missing, privileged groups from a copied model user, apps and shared mailboxes not requested, waiting for approval or rejected);
the device (none assigned, no stock at the site, the wrong platform, enrolled but not compliant); the phone and how the joiner will
register MFA on day one. Every gap has an owner, the working days its fix needs and a due date; a gap that blocks day one becomes a
blocker when its fix no longer fits before the start date, or the start is within the urgent window. Each joiner is READY, AT RISK
or BLOCKED."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .model import TYPE_LABEL, Account, Data, Device, Joiner, Profile, _norm, add_working, working_days

READY, AT_RISK, BLOCKED = "READY", "AT RISK", "BLOCKED"
STATUS_ORDER = {BLOCKED: 0, AT_RISK: 1, READY: 2}
BLOCKER, RISK, INFO = "blocker", "risk", "info"
SEV_ORDER = {BLOCKER: 0, RISK: 1, INFO: 2}
AREAS = ["request", "account", "licence", "groups", "access", "device", "phone", "mfa"]
AREA_LABEL = {"request": "Request", "account": "Account", "licence": "Licence", "groups": "Groups", "access": "Access",
              "device": "Device", "phone": "Phone", "mfa": "MFA"}
# code: area, title, owner area, fix kind, blocks day one
CHECKS = {
    "REQ-LATE": ("request", "Request raised late", "hr", "data", False),
    "ACC-MISSING": ("account", "No account", "identity", "account", True),
    "ACC-REHIRE": ("account", "Rehire with a disabled account", "identity", "account", True),
    "ACC-DUPLICATE": ("account", "Duplicate account for a rehire", "identity", "account", True),
    "ACC-DISABLED": ("account", "Account disabled", "identity", "account", True),
    "ACC-NOID": ("account", "No employeeId on the account", "identity", "data", False),
    "ACC-DEPT": ("account", "Department differs from HR", "identity", "data", False),
    "ACC-MANAGER": ("account", "Manager differs from HR", "identity", "data", False),
    "ACC-USAGELOC": ("account", "No usage location", "identity", "account", True),
    "ACC-CLOUDONLY": ("account", "Cloud-only account in a hybrid directory", "identity", "account", False),
    "LIC-NONE": ("licence", "No licence", "licensing", "licence", True),
    "LIC-WRONG": ("licence", "Wrong licence", "licensing", "licence", True),
    "LIC-EXTRA": ("licence", "Extra licence", "licensing", "data", False),
    "LIC-POOL": ("licence", "Licence pool short", "licensing", "licence_purchase", True),
    "GRP-MISSING": ("groups", "Role groups missing", "identity", "groups", True),
    "GRP-DL": ("groups", "Distribution lists missing", "identity", "groups", False),
    "GRP-PRIV": ("groups", "Privileged group not in the role", "security", "data", True),
    "APP-NOREQ": ("access", "App access not requested", "manager", "access_request", True),
    "APP-PENDING": ("access", "App access waiting for approval", "access", "access_approval", True),
    "APP-APPROVED": ("access", "App access approved, not provisioned", "access", "access_fulfil", True),
    "APP-REJECTED": ("access", "App access rejected", "manager", "access_request", True),
    "MBX-NOREQ": ("access", "Shared mailbox not requested", "manager", "access_request", False),
    "MBX-PENDING": ("access", "Shared mailbox access not provisioned", "identity", "access_fulfil", False),
    "DEV-NONE": ("device", "No device assigned", "workplace", "device_build", True),
    "DEV-NOSTOCK": ("device", "No stock at the site", "workplace", "device_order", True),
    "DEV-PLATFORM": ("device", "Wrong platform", "workplace", "device_build", True),
    "DEV-NONCOMPLIANT": ("device", "Device not compliant", "workplace", "device_build", True),
    "PHN-NONE": ("phone", "No phone assigned", "mobile", "phone", False),
    "PHN-ROLE": ("phone", "Role needs a phone, none ordered", "manager", "device_order", True),
    "MFA-NODEVICE": ("mfa", "No way to register MFA on day one", "identity", "mfa", True),
    "MFA-TAP": ("mfa", "Plan the first sign-in", "identity", "mfa", False),
}
ALWAYS_BLOCKER = {"GRP-PRIV"}


@dataclass
class Gap:
    code: str
    joiner: Joiner
    detail: str
    fix: str
    owner: str
    fix_days: int
    days_left: int
    severity: str = RISK
    due: date | None = None
    item: str = ""

    @property
    def area(self) -> str:
        return CHECKS[self.code][0]

    @property
    def title(self) -> str:
        return CHECKS[self.code][1]


@dataclass
class Result:
    joiner: Joiner
    days_left: int
    profile: Profile | None
    account: Account | None
    devices: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    status: str = READY
    areas: dict = field(default_factory=dict)

    @property
    def blockers(self) -> list:
        return [g for g in self.gaps if g.severity == BLOCKER]

    @property
    def risks(self) -> list:
        return [g for g in self.gaps if g.severity == RISK]


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def countdown(days: int) -> str:
    if days <= 0:
        return "starts today"
    return f"{_n(days, 'working day')} to go"


# ---------------------------------------------------------------- matching

def match_account(d: Data, j: Joiner) -> tuple[Account | None, list[Account], str]:
    """The account for the joiner (employeeId first, then the planned UPN, then the display name), the other accounts with the same
    employeeId, and how it was matched."""
    same = [a for a in d.accounts if a.employee_id and a.employee_id == j.employee_id]
    # an account is this joiner's when it is enabled, or disabled but created for this start (from 60 days before the request);
    # an older disabled account with the same employeeId belongs to an earlier employment: a rehire
    since = (j.raised or j.start) - timedelta(days=60)
    current = sorted([a for a in same if a.enabled is not False or (a.created and a.created.date() >= since)],
                     key=lambda a: (a.enabled is not False, a.created or datetime.min, a.upn), reverse=True)
    if current:
        return current[0], [a for a in same if a is not current[0]], "employeeId"
    if same:
        return None, same, "employeeId"
    if j.upn:
        a = next((a for a in d.accounts if a.upn == j.upn), None)
        if a:
            return a, [], "UPN"
    n = _norm(j.name)
    by_name = [a for a in d.accounts if n and _norm(a.name) == n and not a.employee_id]
    if len(by_name) == 1:
        return by_name[0], [], "name"
    return None, [], ""


def _privileged(d: Data, g: str) -> bool:
    s = d.settings
    n = g.lower()
    return any(n == p.lower() for p in s.privileged_groups) or any(p.lower() in n for p in s.privileged_patterns)


# ---------------------------------------------------------------- one joiner

def check_joiner(d: Data, j: Joiner, alloc: dict) -> Result:
    s = d.settings
    hol = s.holiday_set
    left = working_days(d.today, j.start, hol)
    p = d.profile(j)
    acc, others, how = match_account(d, j)
    r = Result(j, left, p, acc)
    gaps = r.gaps

    def gap(code: str, detail: str, fix: str, owner: str = "", item: str = "", kind: str = "") -> None:
        _, _, area_owner, default_kind, _ = CHECKS[code]
        own = owner or (j.manager if area_owner == "manager" and j.manager else s.owner(area_owner))
        gaps.append(Gap(code, j, detail, fix, own, s.fix(kind or default_kind), left, item=item))

    # request lead time
    if j.raised:
        lead = working_days(j.raised, j.start, hol)
        if lead < s.lead_time_days:
            ref = f" {j.ticket}" if j.ticket else ""
            gap("REQ-LATE", f"request{ref} raised on {j.raised:%a %d %b}, {_n(lead, 'working day')} before the start "
                            f"(the target is {s.lead_time_days})",
                "Agree with HR and the hiring manager what can be ready on day one and what follows; remind managers of the lead time.")
    # account
    upn = acc.upn if acc else j.upn
    if acc is None and others:
        old = sorted(others, key=lambda a: a.upn)[0]
        gap("ACC-REHIRE", f"rehire: {old.upn} with employeeId {j.employee_id} is disabled"
                          + (f" (created {old.created:%b %Y})" if old.created else ""),
            "Re-enable and restore the existing account (reset the password, check groups and licences) instead of creating a new one.")
        upn = old.upn
    elif acc is None:
        gap("ACC-MISSING", "no account in Entra ID with this employeeId, planned UPN or name"
                           + ("; in a hybrid directory create it in AD and let Entra Connect sync it" if s.hybrid else ""),
            "Create the account from the role profile" + (" in AD" if s.hybrid else "") + " with employeeId, department, manager and "
            "usage location set.")
    else:
        if others:
            old = sorted(others, key=lambda a: a.upn)[0]
            gap("ACC-DUPLICATE", f"rehire: a new account {acc.upn} was created while {old.upn} (disabled"
                                 + (f", created {old.created:%b %Y}" if old.created else "") + ") has the same employeeId",
                "Decide which account to keep before day one: usually the original (mailbox, history, OneDrive); remove the duplicate "
                "and its licence.")
        if acc.enabled is False and not s.enable_on_start:
            gap("ACC-DISABLED", f"{acc.upn} is disabled", "Enable the account before the start date (or set enable_on_start if your "
                                                          "process enables accounts on the morning of day one).")
        if how == "name":
            gap("ACC-NOID", f"{acc.upn} matched by name only: employeeId is empty", "Set employeeId on the account so that HR and IT "
                                                                                  "records match (and leaver processes find it).")
        if j.department and acc.department and _norm(j.department) != _norm(acc.department):
            gap("ACC-DEPT", f"Entra ID says {acc.department}, HR says {j.department}", "Correct the department (dynamic groups and "
                                                                                    "reports depend on it).")
        if j.manager and acc.manager and j.manager != acc.manager:
            gap("ACC-MANAGER", f"Entra ID manager {acc.manager}, HR manager {j.manager}", "Set the manager from HR (approvals and "
                                                                                       "access reviews go to the manager).")
        elif j.manager and not acc.manager:
            gap("ACC-MANAGER", f"no manager on the account, HR manager {j.manager}", "Set the manager from HR.")
        if s.hybrid and acc.synced is False:
            gap("ACC-CLOUDONLY", f"{acc.upn} is cloud-only while the directory is hybrid",
                "Create the account in AD and match it, or confirm the joiner needs no on-premises resources.")
    # licence
    need = p.licence if p else ""
    held = set(acc.licences) if acc else set()
    lic_gap = ""
    if need and need not in held:
        lic_gap = need
    if acc and need:
        known = set(s.sku_names)
        other = sorted((held & known) - {need})
        if not acc.usage_location:
            gap("ACC-USAGELOC", f"{acc.upn} has no usage location" + (f": {s.sku_name(need)} cannot be assigned" if lic_gap else ""),
                "Set usageLocation (the country where the joiner works) before assigning the licence.")
        if lic_gap and other:
            gap("LIC-WRONG", f"has {', '.join(s.sku_name(x) for x in other)}, the role needs {s.sku_name(need)}",
                f"Assign {s.sku_name(need)} and remove {', '.join(s.sku_name(x) for x in other)}.", item=need)
        elif not lic_gap and other:
            gap("LIC-EXTRA", f"has {', '.join(s.sku_name(x) for x in other)} as well as {s.sku_name(need)}",
                f"Remove {', '.join(s.sku_name(x) for x in other)} (licence cost).")
    if lic_gap and not any(g.code == "LIC-WRONG" for g in gaps):
        pool = s.licence_available.get(need)
        if pool is not None:
            alloc["lic"][need] += 1
        if pool is not None and alloc["lic"][need] > pool:
            gap("LIC-POOL", f"{s.sku_name(need)}: no free licence left for this joiner ({pool} free, this is joiner "
                            f"{alloc['lic'][need]} needing one)", f"Buy more {s.sku_name(need)} or free unused ones (leavers, "
                                                                  "disabled accounts) before the start date.", item=need)
        else:
            why = "no account yet" if acc is None and not others else ("no usage location" if acc and not acc.usage_location else "")
            gap("LIC-NONE", f"{s.sku_name(need)} not assigned" + (f" ({why})" if why else ""),
                f"Assign {s.sku_name(need)} (directly or through the licensing group of the role).", item=need)
    # groups
    if acc and p:
        groups = {g.lower() for g in acc.groups}
        miss = [g for g in p.expand(p.groups, j) if g.lower() not in groups]
        if miss:
            gap("GRP-MISSING", f"{_n(len(miss), 'role group')} missing: {', '.join(miss)}", "Add the groups of the role profile.")
        dls = [g for g in p.expand(p.distribution_lists, j) if g.lower() not in groups]
        if dls:
            gap("GRP-DL", f"not in {', '.join(dls)}", "Add the distribution lists of the role.")
        allowed = {g.lower() for g in p.expand(p.groups + p.privileged_allowed, j)}
        priv = [g for g in acc.groups if _privileged(d, g) and g.lower() not in allowed]
        if priv:
            gap("GRP-PRIV", f"member of {', '.join(priv)}, not part of the {p.name} profile (often copied from a model user)",
                "Remove the privileged groups before day one; if the role needs admin rights, grant them through PIM with an "
                "approval.")
    # access requests
    if d.access is not None and p:
        reqs = [a for a in d.access if (a.employee_id and a.employee_id == j.employee_id) or (upn and a.upn and a.upn == upn)]
        for item in p.expand(p.apps, j):
            rq = [a for a in reqs if _norm(a.item) == _norm(item)]
            if not rq:
                gap("APP-NOREQ", f"{item}: no access request", f"Raise the access request for {item} with the manager's approval.",
                    item=item)
                continue
            a = rq[-1]
            ref = f" ({a.ticket})" if a.ticket else ""
            if a.state == "pending":
                gap("APP-PENDING", f"{item}{ref}: {a.status or 'requested'}, waiting for {a.approver or 'approval'}",
                    f"Chase the approval of {item} with {a.approver or 'the approver'}.", owner=a.approver, item=item)
            elif a.state == "approved":
                gap("APP-APPROVED", f"{item}{ref}: approved, not provisioned yet", f"Provision {item} before day one.", item=item)
            elif a.state == "rejected":
                gap("APP-REJECTED", f"{item}{ref}: {a.status}", f"Agree with the manager whether the role needs {item}.", item=item)
        for item in p.expand(p.shared_mailboxes, j):
            rq = [a for a in reqs if _norm(a.item) == _norm(item)]
            if not rq:
                gap("MBX-NOREQ", f"{item}: no request", f"Request access to {item}.", item=item)
            elif rq[-1].state != "done":
                gap("MBX-PENDING", f"{item}: {rq[-1].status or 'requested'}", f"Grant access to {item} (Full Access and Send As as "
                                                                              "the role needs).", item=item)
    # devices
    mine = sorted([x for x in d.devices if upn and x.upn == upn], key=lambda x: (x.source, x.name))
    r.devices = mine
    laptops = [x for x in mine if x.kind in ("windows", "mac")]
    phones = [x for x in mine if x.kind == "phone"]

    def stock_gap(kind: str, none_code: str, label: str) -> None:
        if d.stock is None:
            gap(none_code, f"no {label} assigned", "Build and assign the device from stock.", item=TYPE_LABEL[kind])
            return
        free = sum(x.free for x in d.stock if x.site == j.site and x.type == kind)
        alloc["dev"][(j.site, kind)] += 1
        if alloc["dev"][(j.site, kind)] > free:
            models = sorted({f"{x.model} at {x.site}" for x in d.stock if x.type == kind and x.site != j.site and x.free})
            gap("DEV-NOSTOCK" if none_code == "DEV-NONE" else "PHN-NONE",
                f"no {label} assigned and none free in stock at {j.site}" + (f" (free elsewhere: {', '.join(models)})" if models else ""),
                f"Order a {label} or move one from another site; if it cannot arrive in time, agree a loan device for the first days.",
                item=TYPE_LABEL[kind], kind="device_order")
        else:
            gap(none_code, f"no {label} assigned ({free} free in stock at {j.site})", f"Build the {label}, assign it to the joiner and "
                                                                                       "check it is compliant.", item=TYPE_LABEL[kind])

    if j.device in ("windows", "mac"):
        if not laptops:
            stock_gap(j.device, "DEV-NONE", TYPE_LABEL[j.device])
        else:
            dev = laptops[0]
            if dev.kind != j.device:
                gap("DEV-PLATFORM", f"{dev.name} is a {TYPE_LABEL[dev.kind]}, HR asked for a {TYPE_LABEL[j.device]}",
                    "Confirm the platform with the manager and swap the device if needed.", item=dev.name)
            if dev.source != "Autopilot" and dev.enrolled and dev.compliance and not dev.compliant:
                why = "; not encrypted (BitLocker or FileVault pending)" if dev.encrypted is False else ""
                gap("DEV-NONCOMPLIANT", f"{dev.name} ({dev.source}) is {dev.compliance}{why}",
                    "Fix the failing compliance setting (encryption, OS version, Defender) and sync until it reports compliant.",
                    item=dev.name)
    needs_phone = bool(p and p.phone_required)
    if j.phone and not phones:
        stock_gap("phone", "PHN-NONE", "phone")
    if needs_phone and not j.phone and not phones:
        gap("PHN-ROLE", f"the {p.name} profile needs a company phone and none was requested",
            "Confirm with the manager and order the phone, or record why the role does not need one this time.")
    # MFA on day one
    if acc and p and p.mfa_required and not (acc.mfa or 0) and not acc.tap:
        has_phone = bool(phones) or j.phone
        if not has_phone and not s.mfa_own_phone_allowed:
            gap("MFA-NODEVICE", "no MFA method registered and no company phone requested",
                "Agree how the joiner registers MFA on day one under your policy (a company phone, a FIDO2 security key or their own "
                "phone) and issue a Temporary Access Pass for the first sign-in.")
        elif left <= s.urgent_days:
            gap("MFA-TAP", "no MFA method registered yet (normal before day one)",
                "Issue a Temporary Access Pass on the morning of day one so the joiner can sign in and register the authenticator.")
    # severity and due dates
    hol = s.holiday_set
    for g in gaps:
        blocks = CHECKS[g.code][4]
        if g.code == "MFA-TAP":
            g.severity = INFO
        elif g.code in ALWAYS_BLOCKER or (blocks and (g.fix_days > left or left <= s.urgent_days)):
            g.severity = BLOCKER
        else:
            g.severity = RISK
        if g.code == "PHN-NONE" and needs_phone and (g.fix_days > left or left <= s.urgent_days):
            g.severity = BLOCKER
        due = add_working(j.start, -max(1, g.fix_days), hol) if j.start > d.today else d.today
        g.due = max(due, d.today)
    gaps.sort(key=lambda g: (SEV_ORDER[g.severity], AREAS.index(g.area), g.code, g.item))
    r.status = BLOCKED if r.blockers else AT_RISK if r.risks else READY
    for a in AREAS:
        xs = [g for g in gaps if g.area == a]
        if not xs:
            r.areas[a] = "ok"
        else:
            r.areas[a] = {BLOCKER: "blocked", RISK: "risk", INFO: "info"}[min((g.severity for g in xs), key=lambda x: SEV_ORDER[x])]
    if j.device == "none":
        r.areas["device"] = "n/a"
    if not j.phone and not needs_phone:
        r.areas["phone"] = "n/a"
    return r


# ---------------------------------------------------------------- everyone

def in_scope(d: Data, j: Joiner) -> bool:
    if j.start < d.today:
        return False
    return working_days(d.today, j.start, d.settings.holiday_set) <= d.settings.horizon_days


def review(d: Data) -> dict:
    alloc = {"lic": Counter(), "dev": Counter()}
    scope = [j for j in d.joiners if in_scope(d, j)]
    results = [check_joiner(d, j, alloc) for j in scope]
    later = [j for j in d.joiners if j.start >= d.today and j not in scope]
    started = [j for j in d.joiners if j.start < d.today]
    hol = d.settings.holiday_set
    horizon_end = add_working(d.today, d.settings.horizon_days - 1, hol) if d.settings.horizon_days else d.today
    if not results:
        horizon_end = add_working(d.today, d.settings.horizon_days, hol)
    return {"results": results, "later": later, "started": started, "horizon_end": horizon_end,
            "licences": licence_forecast(d, results), "devices": device_forecast(d, results), "sites": by_site(results)}


def licence_forecast(d: Data, results: list[Result]) -> list[dict]:
    s = d.settings
    out = []
    skus = sorted({r.profile.licence for r in results if r.profile and r.profile.licence})
    for sku in skus:
        rs = [r for r in results if r.profile and r.profile.licence == sku]
        need = [r for r in rs if not (r.account and sku in r.account.licences) and not any(g.code == "LIC-WRONG" for g in r.gaps)]
        wrong = [r for r in rs if any(g.code == "LIC-WRONG" for g in r.gaps)]
        pool = s.licence_available.get(sku)
        short = max(0, len(need) - pool) if pool is not None else None
        out.append({"sku": sku, "name": s.sku_name(sku), "joiners": len(rs), "assigned": len(rs) - len(need) - len(wrong),
                    "to_assign": len(need) + len(wrong), "available": pool, "short": short,
                    "short_for": [r.joiner for r in rs if any(g.code == "LIC-POOL" for g in r.gaps)],
                    "first_needed": min((r.joiner.start for r in need), default=None)})
    return out


def device_forecast(d: Data, results: list[Result]) -> list[dict]:
    rows = defaultdict(lambda: {"requested": 0, "assigned": 0, "to_assign": 0, "short_for": []})
    for r in results:
        j = r.joiner
        kinds = ([j.device] if j.device in ("windows", "mac") else []) + (["phone"] if j.phone else [])
        for k in kinds:
            row = rows[(j.site, k)]
            row["requested"] += 1
            have = [x for x in r.devices if (x.kind == k if k == "phone" else x.kind in ("windows", "mac"))]
            if have:
                row["assigned"] += 1
            else:
                row["to_assign"] += 1
                if any(g.code in ("DEV-NOSTOCK",) or (g.code == "PHN-NONE" and "none free" in g.detail) for g in r.gaps
                       if g.item == TYPE_LABEL[k]):
                    row["short_for"].append(j)
    out = []
    for (site, k), row in sorted(rows.items()):
        free = None if d.stock is None else sum(x.free for x in d.stock if x.site == site and x.type == k)
        models = "" if d.stock is None else ", ".join(f"{x.model} ({x.free})" for x in d.stock if x.site == site and x.type == k and x.free)
        out.append({"site": site, "type": TYPE_LABEL[k], **row, "free": free,
                    "short": None if free is None else max(0, row["to_assign"] - free), "models": models})
    return out


def by_site(results: list[Result]) -> list[dict]:
    out = []
    for site in sorted({r.joiner.site for r in results}):
        rs = [r for r in results if r.joiner.site == site]
        st = Counter(r.status for r in rs)
        areas = Counter(g.area for r in rs for g in r.gaps if g.severity != INFO)
        out.append({"site": site, "joiners": len(rs), READY: st.get(READY, 0), AT_RISK: st.get(AT_RISK, 0), BLOCKED: st.get(BLOCKED, 0),
                    "next_start": min(r.joiner.start for r in rs), "blockers": sum(len(r.blockers) for r in rs),
                    "gaps": sum(g.severity != INFO for r in rs for g in r.gaps),
                    "top_areas": ", ".join(f"{AREA_LABEL[a]} {c}" for a, c in sorted(areas.items(), key=lambda x: (-x[1], AREAS.index(x[0])))[:3])})
    return out


# ---------------------------------------------------------------- findings (grouped by check)

@dataclass
class Finding:
    severity: str
    code: str
    title: str
    joiners: list
    detail: str
    fix: str
    owner: str
    first_due: date | None = None


def run_all(d: Data, rv: dict | None = None) -> list[Finding]:
    rv = rv if rv is not None else review(d)
    gaps = [g for r in rv["results"] for g in r.gaps]
    out = []
    for code in CHECKS:
        xs = [g for g in gaps if g.code == code]
        if not xs:
            continue
        sev = min((g.severity for g in xs), key=lambda x: SEV_ORDER[x])
        names = sorted({g.joiner.name for g in xs})
        if code == "LIC-POOL":
            lf = {x["sku"]: x for x in rv["licences"]}
            detail = "; ".join(f"{lf[k]['name']} short by {lf[k]['short']} ({lf[k]['available']} free for {lf[k]['to_assign']} joiners "
                               f"still to licence)" for k in sorted({g.item for g in xs}) if k in lf)
        elif len(xs) == 1:
            detail = f"{xs[0].joiner.name}: {xs[0].detail}"
        else:
            detail = "; ".join(f"{g.joiner.name}: {g.detail}" for g in xs[:4]) + (f"; and {len(xs) - 4} more" if len(xs) > 4 else "")
        owners = sorted({g.owner for g in xs})
        out.append(Finding(sev, code, CHECKS[code][1], names, detail, xs[0].fix if len({g.fix for g in xs}) == 1 else CHECKS_FIX.get(code, xs[0].fix),
                           owners[0] if len(owners) == 1 else ", ".join(owners[:3]) + ("…" if len(owners) > 3 else ""),
                           min(g.due for g in xs if g.due)))
    out.sort(key=lambda f: (SEV_ORDER[f.severity], f.first_due or date.max, -len(f.joiners), list(CHECKS).index(f.code)))
    return out


CHECKS_FIX = {
    "APP-NOREQ": "Raise the access requests for the role's apps with the manager's approval.",
    "APP-PENDING": "Chase the approvals with the approvers named in the requests.",
    "APP-APPROVED": "Provision the approved access before day one.",
    "LIC-NONE": "Assign the licence of the role (directly or through the licensing group).",
    "LIC-WRONG": "Assign the licence of the role and remove the other one.",
    "DEV-NONE": "Build and assign the devices from stock and check they are compliant.",
    "DEV-NOSTOCK": "Order or move the devices; agree a loan device where they cannot arrive in time.",
    "PHN-NONE": "Prepare and assign the phones; order where there is no stock.",
    "MBX-NOREQ": "Request access to the shared mailboxes of the role.",
    "MBX-PENDING": "Grant the shared mailbox access.",
}


def fix_first(rv: dict, k: int = 12) -> list[Gap]:
    xs = [g for r in rv["results"] for g in r.gaps if g.severity == BLOCKER]
    xs.sort(key=lambda g: (g.due, g.days_left, AREAS.index(g.area), g.joiner.name, g.code))
    return xs[:k]


def summary(d: Data, rv: dict, findings: list[Finding]) -> dict:
    rs = rv["results"]
    st = Counter(r.status for r in rs)
    s = d.settings
    soon = [r for r in rs if r.days_left <= s.urgent_days]
    return dict(joiners=len(rs), status=st, blockers=sum(len(r.blockers) for r in rs), risks=sum(len(r.risks) for r in rs),
                sites=len(rv["sites"]), soon=len(soon), soon_not_ready=sum(r.status != READY for r in soon),
                late=sum(any(g.code == "REQ-LATE" for g in r.gaps) for r in rs),
                licence_short={x["sku"]: x["short"] for x in rv["licences"] if x["short"]},
                device_short=sum(x["short"] or 0 for x in rv["devices"]), later=len(rv["later"]),
                first=min((r.joiner.start for r in rs), default=None), last=max((r.joiner.start for r in rs), default=None),
                findings=len(findings))


__all__ = ["READY", "AT_RISK", "BLOCKED", "BLOCKER", "RISK", "INFO", "AREAS", "AREA_LABEL", "CHECKS", "Gap", "Result", "Finding",
           "check_joiner", "match_account", "review", "run_all", "summary", "fix_first", "licence_forecast", "device_forecast", "countdown"]
