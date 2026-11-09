"""Loading: the joiners from HR (or the ITSM joiner requests), the role profiles, the Entra ID / Active Directory accounts, the Intune or
Jamf devices, and, optionally, the subscribed licences, the Windows Autopilot registrations, the device stock per site and the app and
shared mailbox access requests. Forgiving column names, into plain dataclasses. Working days and the countdown to each start date."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

JOINER_ALIASES = {
    "employee_id": ["EmployeeId", "Employee ID", "employee number", "personnel number", "worker id", "hr id"],
    "name": ["Name", "Full name", "DisplayName", "display name", "employee name"],
    "start": ["StartDate", "Start date", "start", "first day", "hire date", "joining date"],
    "site": ["Site", "Location", "office", "work location"],
    "department": ["Department", "dept", "team"],
    "title": ["JobTitle", "Job title", "Role", "position"],
    "manager": ["Manager", "ManagerUPN", "manager email", "line manager", "manager upn"],
    "contract": ["ContractType", "contract type", "contract", "employment type", "worker type"],
    "device": ["Device", "DeviceType", "device type", "laptop", "computer"],
    "phone": ["Phone", "Mobile phone", "mobile", "company phone"],
    "ticket": ["Ticket", "RequestTicket", "request", "request ticket", "itsm ticket", "key"],
    "raised": ["Raised", "RequestRaised", "request raised", "date raised", "created", "requested on"],
    "upn": ["UserPrincipalName", "UPN", "email", "planned upn"],
}
ACCOUNT_ALIASES = {
    "upn": ["UserPrincipalName", "UPN", "user principal name", "username"],
    "name": ["DisplayName", "Display name", "name"],
    "employee_id": ["EmployeeId", "employee id", "employeeid", "employee number"],
    "enabled": ["AccountEnabled", "account enabled", "enabled"],
    "created": ["CreatedDateTime", "created", "whencreated", "created date"],
    "department": ["Department"],
    "title": ["JobTitle", "job title", "title"],
    "manager": ["Manager", "ManagerUPN", "manager upn", "manager email"],
    "usage_location": ["UsageLocation", "usage location"],
    "licences": ["AssignedLicenses", "assigned licenses", "licenses", "licences", "skus"],
    "groups": ["Groups", "MemberOf", "member of", "group membership"],
    "mfa": ["MfaMethods", "mfa methods", "authentication methods", "methods registered"],
    "tap": ["TemporaryAccessPass", "temporary access pass", "tap"],
    "synced": ["OnPremisesSyncEnabled", "on premises sync enabled", "synced", "dirsync"],
}
DEVICE_ALIASES = {
    "name": ["DeviceName", "Device name", "Computer Name", "computer name", "name"],
    "serial": ["SerialNumber", "Serial Number", "serial"],
    "upn": ["UserPrincipalName", "Email Address", "user principal name", "primary user", "username", "assigned user", "user"],
    "os": ["OperatingSystem", "Operating System", "os", "platform"],
    "model": ["Model"],
    "compliance": ["ComplianceState", "compliance state", "compliance", "compliant"],
    "management": ["ManagementState", "management state", "managed", "enrollment state", "enrolment state"],
    "last_sync": ["LastSyncDateTime", "Last Check-in", "last check in", "last sync", "last contact"],
    "ownership": ["ManagedDeviceOwnerType", "ownership", "owner type", "owner"],
    "encrypted": ["IsEncrypted", "encrypted", "filevault 2 status", "bitlocker"],
}
AUTOPILOT_ALIASES = {
    "serial": ["SerialNumber", "serial number", "serial"],
    "group_tag": ["GroupTag", "group tag", "order id"],
    "upn": ["UserPrincipalName", "assigned user", "user"],
    "state": ["EnrollmentState", "enrollment state", "enrolment state"],
    "model": ["Model"],
}
STOCK_ALIASES = {
    "site": ["Site", "Location", "store"],
    "type": ["DeviceType", "device type", "type", "category"],
    "model": ["Model"],
    "in_stock": ["InStock", "in stock", "quantity", "qty", "available"],
    "reserved": ["Reserved", "allocated"],
}
ACCESS_ALIASES = {
    "employee_id": ["EmployeeId", "employee id"],
    "upn": ["UserPrincipalName", "UPN", "user"],
    "item": ["Item", "Application", "app", "resource", "access", "shared mailbox"],
    "kind": ["Kind", "Type", "request type"],
    "status": ["Status", "state"],
    "ticket": ["Ticket", "Key", "request"],
    "approver": ["Approver", "approved by", "owner"],
}
LICENCE_ALIASES = {
    "sku": ["SkuPartNumber", "sku part number", "sku", "licence", "license"],
    "enabled": ["Enabled", "PrepaidUnitsEnabled", "prepaid enabled", "purchased", "total"],
    "consumed": ["ConsumedUnits", "consumed units", "consumed", "assigned"],
}
YES = {"yes", "y", "true", "1", "on", "si", "x", "required"}
DONE = {"fulfilled", "done", "completed", "complete", "closed", "provisioned", "granted", "resolved"}
APPROVED = {"approved"}
REJECTED = {"rejected", "declined", "denied", "cancelled", "canceled"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%m/%d/%Y")
DEFAULT_OWNERS = {"hr": "HR onboarding", "identity": "Identity and service desk", "licensing": "Microsoft 365 licensing",
                  "workplace": "Workplace (Intune / Jamf)", "mobile": "Mobile devices", "access": "Application owner",
                  "security": "Security / IAM", "manager": "Hiring manager"}
# working days each kind of fix needs before the start date
DEFAULT_FIX_DAYS = {"account": 1, "licence": 1, "licence_purchase": 3, "groups": 1, "access_request": 3, "access_approval": 2,
                    "access_fulfil": 1, "device_build": 2, "device_order": 5, "phone": 2, "mfa": 0, "data": 0}
DEFAULT_SKU_NAMES = {"SPE_E3": "Microsoft 365 E3", "SPE_E5": "Microsoft 365 E5", "SPE_F1": "Microsoft 365 F3",
                     "ENTERPRISEPACK": "Office 365 E3", "ENTERPRISEPREMIUM": "Office 365 E5", "DESKLESSPACK": "Office 365 F3"}
DEFAULT_PRIVILEGED = ["Domain Admins", "Enterprise Admins", "Schema Admins", "Account Operators", "Server Operators", "Global Administrator"]
DEFAULT_PRIVILEGED_PATTERNS = ["admins", "administrator", "privileged", "pim-"]


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"n a", "na", "none", "null", "never"}:
        return None
    s = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", "", s)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_d(v) -> date | None:
    x = parse_dt(v)
    return x.date() if x else None


def tri(v) -> bool | None:
    """yes / no / unknown (empty)."""
    n = _norm(v)
    if not n:
        return None
    return n in YES


def num(v) -> float | None:
    s = str(v or "").strip().replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def split_list(v) -> list[str]:
    return [x.strip() for x in re.split(r"[;|\n]", str(v or "")) if x.strip()]


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = fh.readline()
        fh.seek(0)
        delim = max(",;\t", key=header.count)
        reader = csv.DictReader(fh, delimiter=delim)
        return list(reader.fieldnames or []), list(reader)


def _map(fields: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    heads = {_norm(h): h for h in fields}
    cols = {}
    for k, names in aliases.items():
        for n in names + [k.replace("_", " ")]:
            if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                cols[k] = heads[_norm(n)]
                break
    return cols


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    fields, raw = _read(path)
    cols = _map(fields, aliases)
    return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in raw]


def device_type(v) -> str:
    """windows, mac, none (or '' when unknown), from the joiner request or an OS name."""
    n = _norm(v)
    if not n or n in {"none", "no", "n a", "shared", "shared device", "kiosk"}:
        return "none" if n else ""
    if "mac" in n:
        return "mac"
    if "iphone" in n or "ios" in n or "android" in n or "phone" in n:
        return "phone"
    if "ipad" in n or "tablet" in n:
        return "tablet"
    return "windows"


TYPE_LABEL = {"windows": "Windows laptop", "mac": "MacBook", "phone": "Phone", "tablet": "Tablet", "none": "No device", "": "Not stated"}


# ---------------------------------------------------------------- working days

def is_working(d: date, holidays: set) -> bool:
    return d.weekday() < 5 and d not in holidays


def working_days(a: date, b: date, holidays: set) -> int:
    """Working days in [a, b): from a (included) to b (excluded); negative when b is before a."""
    if b < a:
        return -working_days(b, a, holidays)
    n, d = 0, a
    while d < b:
        n += is_working(d, holidays)
        d += timedelta(days=1)
    return n


def add_working(d: date, n: int, holidays: set) -> date:
    """The working day n working days after d (n > 0) or before d (n < 0)."""
    step = 1 if n >= 0 else -1
    left = abs(n)
    while left:
        d += timedelta(days=step)
        if is_working(d, holidays):
            left -= 1
    return d


# ---------------------------------------------------------------- records

@dataclass
class Joiner:
    employee_id: str
    name: str
    start: date
    site: str = ""
    department: str = ""
    title: str = ""
    manager: str = ""
    contract: str = ""
    device: str = ""             # windows, mac, none, ''
    phone: bool = False
    ticket: str = ""
    raised: date | None = None
    upn: str = ""


@dataclass
class Account:
    upn: str
    name: str = ""
    employee_id: str = ""
    enabled: bool | None = None
    created: datetime | None = None
    department: str = ""
    title: str = ""
    manager: str = ""
    usage_location: str = ""
    licences: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    mfa: int | None = None
    tap: bool | None = None
    synced: bool | None = None


@dataclass
class Device:
    name: str
    serial: str = ""
    upn: str = ""
    os: str = ""
    model: str = ""
    compliance: str = ""
    management: str = ""
    last_sync: date | None = None
    ownership: str = ""
    encrypted: bool | None = None
    source: str = "Intune"      # Intune, Jamf, Autopilot
    enrolled: bool = True

    @property
    def kind(self) -> str:
        return device_type(self.os)

    @property
    def compliant(self) -> bool:
        return _norm(self.compliance) in {"compliant", "yes", "true", "1"}


@dataclass
class Stock:
    site: str
    type: str
    model: str = ""
    in_stock: int = 0
    reserved: int = 0

    @property
    def free(self) -> int:
        return max(0, self.in_stock - self.reserved)


@dataclass
class Access:
    item: str
    employee_id: str = ""
    upn: str = ""
    kind: str = "app"
    status: str = ""
    ticket: str = ""
    approver: str = ""

    @property
    def state(self) -> str:
        """done, approved, pending, rejected."""
        n = _norm(self.status)
        if n in DONE:
            return "done"
        if n in APPROVED:
            return "approved"
        if n in REJECTED:
            return "rejected"
        return "pending"


@dataclass
class Profile:
    name: str
    job_titles: list = field(default_factory=list)
    departments: list = field(default_factory=list)
    licence: str = ""
    groups: list = field(default_factory=list)
    distribution_lists: list = field(default_factory=list)
    apps: list = field(default_factory=list)
    shared_mailboxes: list = field(default_factory=list)
    phone_required: bool = False
    mfa_required: bool = True
    privileged_allowed: list = field(default_factory=list)

    def expand(self, items: list, j: Joiner) -> list:
        return [x.replace("{site}", j.site).replace("{department}", j.department) for x in items]


@dataclass
class Settings:
    organisation: str = "New starter day-one readiness"
    as_of: datetime | None = None
    horizon_days: int = 10
    lead_time_days: int = 10
    urgent_days: int = 3
    holidays: list = field(default_factory=list)
    enable_on_start: bool = False
    hybrid: bool = False
    mfa_own_phone_allowed: bool = True
    fix_days: dict = field(default_factory=lambda: dict(DEFAULT_FIX_DAYS))
    licence_available: dict = field(default_factory=dict)
    sku_names: dict = field(default_factory=lambda: dict(DEFAULT_SKU_NAMES))
    privileged_groups: list = field(default_factory=lambda: list(DEFAULT_PRIVILEGED))
    privileged_patterns: list = field(default_factory=lambda: list(DEFAULT_PRIVILEGED_PATTERNS))
    owners: dict = field(default_factory=lambda: dict(DEFAULT_OWNERS))
    next_call: str = ""

    def owner(self, area: str) -> str:
        return self.owners.get(area) or DEFAULT_OWNERS.get(area, "IT onboarding lead")

    def fix(self, kind: str) -> int:
        return int(self.fix_days.get(kind, DEFAULT_FIX_DAYS.get(kind, 1)))

    def sku_name(self, sku: str) -> str:
        return self.sku_names.get(sku, sku)

    @property
    def holiday_set(self) -> set:
        return {d for d in (parse_d(x) for x in self.holidays) if d}


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k) or v is None:
            continue
        cur = getattr(s, k)
        if k == "as_of":
            s.as_of = parse_dt(v)
        elif k == "licence_available":
            s.licence_available = {str(a).upper(): int(num(b) or 0) for a, b in v.items()}
        elif k in ("fix_days", "sku_names", "owners"):
            cur.update({str(a): b for a, b in v.items()})
        elif isinstance(cur, list):
            setattr(s, k, [str(x) for x in v])
        elif isinstance(cur, bool):
            setattr(s, k, bool(v))
        elif isinstance(cur, int):
            setattr(s, k, int(num(v) or 0))
        else:
            setattr(s, k, str(v))
    return s


def profiles_from_dict(raw: dict) -> tuple[list[Profile], Profile | None]:
    def one(p: dict, name: str = "") -> Profile:
        return Profile(str(p.get("name") or name), [str(x) for x in p.get("job_titles", [])], [str(x) for x in p.get("departments", [])],
                       str(p.get("licence", "")).upper(), list(p.get("groups", [])), list(p.get("distribution_lists", [])),
                       list(p.get("apps", [])), list(p.get("shared_mailboxes", [])), bool(p.get("phone_required", False)),
                       bool(p.get("mfa_required", True)), list(p.get("privileged_allowed", [])))
    profiles = [one(p) for p in raw.get("profiles", [])]
    default = one(raw["default"], "Default") if raw.get("default") else None
    return profiles, default


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    joiners: list[Joiner] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    default_profile: Profile | None = None
    accounts: list[Account] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    stock: list[Stock] | None = None
    access: list[Access] | None = None
    sources: dict = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def profile(self, j: Joiner) -> Profile | None:
        t, dpt = _norm(j.title), _norm(j.department)
        for p in self.profiles:
            if t and t in {_norm(x) for x in p.job_titles}:
                return p
        for p in self.profiles:
            if dpt and dpt in {_norm(x) for x in p.departments} and not p.job_titles:
                return p
        return self.default_profile


# ---------------------------------------------------------------- loaders

def load_joiners(path: Path) -> list[Joiner]:
    out = []
    for r in _rows(path, JOINER_ALIASES):
        start = parse_d(r.get("start"))
        if not r.get("employee_id") or not start:
            continue
        out.append(Joiner(r["employee_id"], r.get("name", ""), start, r.get("site", "").upper(), r.get("department", ""), r.get("title", ""),
                          r.get("manager", "").lower(), r.get("contract", ""), device_type(r.get("device")), bool(tri(r.get("phone"))),
                          r.get("ticket", ""), parse_d(r.get("raised")), r.get("upn", "").lower()))
    return sorted(out, key=lambda j: (j.start, j.site, j.name, j.employee_id))


def load_accounts(path: Path) -> list[Account]:
    out = []
    for r in _rows(path, ACCOUNT_ALIASES):
        if not r.get("upn"):
            continue
        mfa = num(r.get("mfa"))
        out.append(Account(r["upn"].lower(), r.get("name", ""), r.get("employee_id", ""), tri(r.get("enabled")), parse_dt(r.get("created")),
                           r.get("department", ""), r.get("title", ""), r.get("manager", "").lower(), r.get("usage_location", "").upper(),
                           [x.upper() for x in split_list(r.get("licences"))], split_list(r.get("groups")),
                           None if mfa is None else int(mfa), tri(r.get("tap")), tri(r.get("synced"))))
    return out


def load_devices(path: Path, source: str = "Intune") -> list[Device]:
    out = []
    for r in _rows(path, DEVICE_ALIASES):
        if not r.get("name") and not r.get("serial"):
            continue
        mg = _norm(r.get("management"))
        enrolled = not mg or mg in {"managed", "yes", "true", "enrolled", "1"}
        out.append(Device(r.get("name") or r.get("serial", ""), r.get("serial", "").upper(), r.get("upn", "").lower(), r.get("os", ""),
                          r.get("model", ""), r.get("compliance", ""), r.get("management", ""), parse_d(r.get("last_sync")),
                          r.get("ownership", ""), tri(r.get("encrypted")), source, enrolled))
    return out


def load_autopilot(path: Path) -> list[Device]:
    """Windows Autopilot registrations, as data only: a registered device assigned to the joiner that is not enrolled yet."""
    out = []
    for r in _rows(path, AUTOPILOT_ALIASES):
        if not r.get("serial"):
            continue
        out.append(Device(r["serial"].upper(), r["serial"].upper(), r.get("upn", "").lower(), "Windows", r.get("model", ""), "",
                          r.get("state", ""), None, r.get("group_tag", ""), None, "Autopilot", _norm(r.get("state")) == "enrolled"))
    return out


def load_stock(path: Path) -> list[Stock]:
    return [Stock(r["site"].upper(), device_type(r.get("type")), r.get("model", ""), int(num(r.get("in_stock")) or 0),
                  int(num(r.get("reserved")) or 0)) for r in _rows(path, STOCK_ALIASES) if r.get("site") and r.get("type")]


def load_access(path: Path) -> list[Access]:
    out = []
    for r in _rows(path, ACCESS_ALIASES):
        if not r.get("item") or not (r.get("employee_id") or r.get("upn")):
            continue
        kind = "shared mailbox" if "mailbox" in _norm(r.get("kind")) else "app"
        out.append(Access(r["item"], r.get("employee_id", ""), r.get("upn", "").lower(), kind, r.get("status", ""), r.get("ticket", ""),
                          r.get("approver", "")))
    return out


def load_licences(path: Path) -> dict[str, int]:
    out = {}
    for r in _rows(path, LICENCE_ALIASES):
        if r.get("sku"):
            out[r["sku"].upper()] = int(num(r.get("enabled")) or 0) - int(num(r.get("consumed")) or 0)
    return out


FILES = {
    "joiners.csv": "Joiners from HR or the ITSM joiner requests, one row per new starter",
    "role_profiles.json": "Expected groups, licence, apps, shared mailboxes, lists and phone per role or department",
    "accounts.csv": "Entra ID / Active Directory accounts with licences, groups and MFA methods",
    "devices.csv": "Intune or Jamf Pro devices with the assigned user",
    "autopilot.csv": "Windows Autopilot registrations (optional)",
    "licences.csv": "Subscribed licences with enabled and consumed units (optional; else licence_available in settings)",
    "stock.csv": "Laptops and phones in stock per site (optional)",
    "access_requests.csv": "App and shared mailbox access requests per joiner (optional)",
}


def load(folder: Path, as_of: datetime | None = None) -> Data:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"no folder {folder}")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    for need in ("joiners.csv", "accounts.csv"):
        if not (folder / need).exists():
            raise FileNotFoundError(f"{folder}: need {need} ({FILES[need]})")
    d = Data(s, when)
    d.joiners = load_joiners(folder / "joiners.csv")
    if not d.joiners:
        raise ValueError(f"{folder / 'joiners.csv'}: no joiners (check the EmployeeId and StartDate columns)")
    rp = folder / "role_profiles.json"
    if rp.exists():
        d.profiles, d.default_profile = profiles_from_dict(json.loads(rp.read_text(encoding="utf-8")))
    d.accounts = load_accounts(folder / "accounts.csv")
    d.sources = {"joiners.csv": len(d.joiners), "role_profiles.json": len(d.profiles) + (1 if d.default_profile else 0),
                 "accounts.csv": len(d.accounts)}
    if (folder / "devices.csv").exists():
        d.devices = load_devices(folder / "devices.csv")
        d.sources["devices.csv"] = len(d.devices)
    if (folder / "autopilot.csv").exists():
        ap = load_autopilot(folder / "autopilot.csv")
        d.devices += ap
        d.sources["autopilot.csv"] = len(ap)
    if (folder / "licences.csv").exists():
        lic = load_licences(folder / "licences.csv")
        s.licence_available = {**s.licence_available, **lic}
        d.sources["licences.csv"] = len(lic)
    if (folder / "stock.csv").exists():
        d.stock = load_stock(folder / "stock.csv")
        d.sources["stock.csv"] = len(d.stock)
    if (folder / "access_requests.csv").exists():
        d.access = load_access(folder / "access_requests.csv")
        d.sources["access_requests.csv"] = len(d.access)
    return d


__all__ = ["Data", "Settings", "Joiner", "Account", "Device", "Stock", "Access", "Profile", "load", "load_joiners", "load_accounts",
           "load_devices", "load_autopilot", "load_stock", "load_access", "load_licences", "settings_from_dict", "profiles_from_dict",
           "working_days", "add_working", "is_working", "device_type", "TYPE_LABEL", "FILES"]
