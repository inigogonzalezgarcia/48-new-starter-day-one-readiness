"""Outputs: report.html (verdict tiles, the fix-first list, the countdown board with a card per joiner, the site table, the licence and
device forecasts and every gap), day-one-pack.md (the pack for the weekly joiners call, with owner, due date and done columns), and the
CSVs: joiner-status, gaps, licence-forecast, device-forecast, actions and findings."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .checks import (AREA_LABEL, AREAS, AT_RISK, BLOCKED, BLOCKER, INFO, READY, RISK, Finding, countdown, fix_first, summary)
from .model import FILES, TYPE_LABEL, Data

e = html.escape
TODO = "**[TO COMPLETE]**"


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _d(x) -> str:
    return "" if x is None else x.isoformat()


def _day(x) -> str:
    return "–" if x is None else f"{x:%a %d %b}"


# ---------------------------------------------------------------- csv

def write_status(d: Data, rv: dict, path: Path) -> None:
    head = ["employee_id", "name", "site", "department", "job_title", "profile", "manager", "contract", "device_requested", "phone_requested",
            "start_date", "working_days_left", "status", "upn", "devices"] + [f"{a}_status" for a in AREAS] + [
            "blockers", "risks", "first_due", "first_action"]
    rows = []
    for r in rv["results"]:
        j = r.joiner
        open_ = [g for g in r.gaps if g.severity != INFO]
        first = min(open_, key=lambda g: (g.due, g.severity != BLOCKER)) if open_ else None
        rows.append([j.employee_id, j.name, j.site, j.department, j.title, r.profile.name if r.profile else "", j.manager, j.contract,
                     TYPE_LABEL[j.device], "yes" if j.phone else "no", _d(j.start), r.days_left, r.status, r.account.upn if r.account else "",
                     "; ".join(f"{x.name} ({x.source})" for x in r.devices)] + [r.areas[a] for a in AREAS] + [
                     len(r.blockers), len(r.risks), _d(first.due) if first else "", first.fix if first else ""])
    _w(path, head, rows)


def write_gaps(d: Data, rv: dict, path: Path) -> None:
    rows = []
    for r in rv["results"]:
        for g in r.gaps:
            rows.append([r.joiner.employee_id, r.joiner.name, r.joiner.site, _d(r.joiner.start), r.days_left, r.status, g.severity, g.area,
                         g.code, g.title, g.item, g.detail, g.fix, g.owner, g.fix_days, _d(g.due)])
    _w(path, ["employee_id", "name", "site", "start_date", "working_days_left", "joiner_status", "severity", "area", "code", "check", "item",
              "detail", "action", "owner", "fix_days", "due"], rows)


def write_licences(rv: dict, path: Path) -> None:
    _w(path, ["sku", "name", "joiners", "assigned", "to_assign", "free_units", "short", "first_needed", "short_for"],
       [[x["sku"], x["name"], x["joiners"], x["assigned"], x["to_assign"], "" if x["available"] is None else x["available"],
         "" if x["short"] is None else x["short"], _d(x["first_needed"]), "; ".join(j.name for j in x["short_for"])] for x in rv["licences"]])


def write_devices(rv: dict, path: Path) -> None:
    _w(path, ["site", "type", "requested", "assigned", "to_assign", "free_in_stock", "short", "models_in_stock", "short_for"],
       [[x["site"], x["type"], x["requested"], x["assigned"], x["to_assign"], "" if x["free"] is None else x["free"],
         "" if x["short"] is None else x["short"], x["models"], "; ".join(j.name for j in x["short_for"])] for x in rv["devices"]])


def _ref(g) -> str:
    return f"{g.joiner.employee_id}-{g.code}" + (f"-{g.item}" if g.item and g.code.startswith(("APP", "MBX")) else "")


def _actions(rv: dict) -> list:
    xs = [g for r in rv["results"] for g in r.gaps if g.severity in (BLOCKER, RISK)]
    return sorted(xs, key=lambda g: (g.due, g.severity != BLOCKER, g.joiner.start, g.joiner.name, g.code, g.item))


def write_actions(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["ref", "employee_id", "joiner", "site", "start_date", "severity", "code", "action", "detail", "owner", "due", "done"],
       [[_ref(g), g.joiner.employee_id, g.joiner.name, g.joiner.site, _d(g.joiner.start), g.severity, g.code, g.fix, g.detail, g.owner,
         _d(g.due), ""] for g in _actions(rv)])


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "code", "check", "joiners", "names", "detail", "next_step", "owner", "first_due"],
       [[f.severity, f.code, f.title, len(f.joiners), "; ".join(f.joiners), f.detail, f.fix, f.owner, _d(f.first_due)] for f in findings])


# ---------------------------------------------------------------- the pack

def _md(x) -> str:
    return str(x).replace("|", "/").replace("\n", " ")


def _overall(sm: dict) -> str:
    st = sm["status"]
    return BLOCKED if st.get(BLOCKED) else AT_RISK if st.get(AT_RISK) else READY


AREA_MD = {"ok": "ok", "risk": "risk", "blocked": "**BLOCKED**", "info": "to do", "n/a": "–"}


def pack_md(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s = d.settings
    sm = summary(d, rv, findings)
    st = sm["status"]
    rs = rv["results"]
    out = [f"# {title}", "",
           f"> Generated by dayone on {d.as_of:%a %d %b %Y %H:%M} from the exports listed under *Scope and evidence*. Read-only: nothing was "
           f"changed in any tool. Joiners starting from {_day(sm['first'])} to {_day(sm['last'])} (the next {s.horizon_days} working days); "
           f"the countdown is the working days left to prepare, today included. Sections marked {TODO} are for the call.", "",
           f"**Overall: {_overall(sm)}. {sm['joiners']} joiners: {st.get(READY, 0)} ready, {st.get(AT_RISK, 0)} at risk, "
           f"{st.get(BLOCKED, 0)} blocked.**", "",
           "## Agenda (30 minutes)", "",
           "| Minutes | Topic | Section | Who |", "|---|---|---|---|",
           "| 5 | Who starts this week and next, what changed since last week | Headlines, Joiners by start date | IT onboarding lead |",
           "| 10 | Blockers: one owner and one date each, or a fallback for day one | Fix first | Owners |",
           "| 10 | At risk: licences, devices, access approvals, data mismatches | Open gaps, Licences, Devices | Owners, HR, managers |",
           "| 5 | Late requests and rehires: what HR and managers need to change | Notes | HR |", "",
           "## Headlines", ""]
    out += [f"- {sm['blockers']} blockers and {sm['risks']} risks; {sm['soon_not_ready']} of the {sm['soon']} joiners starting in the next "
            f"{s.urgent_days} working days are not ready.",
            f"- {sm['late']} {'request was' if sm['late'] == 1 else 'requests were'} raised less than {s.lead_time_days} working days before the start."]
    for x in rv["licences"]:
        if x["short"]:
            out.append(f"- {x['name']}: {x['to_assign']} joiners still to licence and {x['available']} free units: **short by {x['short']}** "
                       f"({', '.join(j.name for j in x['short_for'])}).")
    for x in rv["devices"]:
        if x["short"]:
            out.append(f"- {x['site']}: {x['type']} short by {x['short']} ({', '.join(j.name for j in x['short_for'])}).")
    for g in fix_first(rv, 8):
        out.append(f"- **{_md(g.joiner.name)}** ({g.joiner.site}, {countdown(g.days_left)}): {_md(g.title).lower()}: {_md(g.detail)}.")
    out += ["", "## Fix first", "", "The blockers, by due date: each needs an owner and a date today, or a fallback agreed with the manager.", "",
            "| Joiner | Starts | Left | Gap | Action | Owner | Due | Done |", "|---|---|---|---|---|---|---|---|"]
    ff = fix_first(rv, 100)
    out += [f"| {_md(g.joiner.name)} ({g.joiner.site}) | {_day(g.joiner.start)} | {g.days_left} | {_md(g.title)}: {_md(g.detail)} | "
            f"{_md(g.fix)} | {_md(g.owner)} | {_day(g.due)} | |" for g in ff] or ["| No blockers | | | | | | | |"]
    out += ["", "## Joiners by start date", "", "| Joiner | Site | Role | Starts | Left | Status | " + " | ".join(AREA_LABEL[a] for a in AREAS) + " |",
            "|---|---|---|---|---|---|" + "---|" * len(AREAS)]
    for r in rs:
        j = r.joiner
        out.append(f"| {_md(j.name)} | {j.site} | {_md(j.title)} | {_day(j.start)} | {r.days_left} | **{r.status}** | "
                   + " | ".join(AREA_MD[r.areas[a]] for a in AREAS) + " |")
    out += ["", "## Open gaps", "", "Every gap that is not a blocker, by due date. *Risk* changes the joiner to AT RISK; *to do* is a "
            "step for the day itself and does not change the status.", "",
            "| Ref | Joiner | Starts | Gap | Action | Owner | Due | Done |", "|---|---|---|---|---|---|---|---|"]
    rest = sorted([g for r in rs for g in r.gaps if g.severity != BLOCKER], key=lambda g: (g.due, g.severity == INFO, g.joiner.start, g.joiner.name, g.code))
    out += [f"| {_ref(g)} | {_md(g.joiner.name)} | {_day(g.joiner.start)} | {'(to do) ' if g.severity == INFO else ''}{_md(g.title)}: {_md(g.detail)} | "
            f"{_md(g.fix)} | {_md(g.owner)} | {_day(g.due)} | |" for g in rest] or ["| – | No open gaps | | | | | | |"]
    out += ["", "## Sites", "", "| Site | Joiners | Ready | At risk | Blocked | Next start | Most gaps in |", "|---|---|---|---|---|---|---|"]
    out += [f"| {x['site']} | {x['joiners']} | {x[READY]} | {x[AT_RISK]} | {x[BLOCKED]} | {_day(x['next_start'])} | {x['top_areas'] or '–'} |"
            for x in rv["sites"]]
    out += ["", "## Licences", "", "| Licence | Joiners | Assigned | To assign | Free units | Short | First needed |", "|---|---|---|---|---|---|---|"]
    out += [f"| {x['name']} (`{x['sku']}`) | {x['joiners']} | {x['assigned']} | {x['to_assign']} | "
            f"{'not given' if x['available'] is None else x['available']} | {'–' if x['short'] is None else ('**' + str(x['short']) + '**' if x['short'] else 0)} | "
            f"{_day(x['first_needed'])} |" for x in rv["licences"]]
    out += ["", "## Devices", "", "| Site | Type | Requested | Assigned | To assign | Free in stock | Short | Models in stock |",
            "|---|---|---|---|---|---|---|---|"]
    out += [f"| {x['site']} | {x['type']} | {x['requested']} | {x['assigned']} | {x['to_assign']} | {'–' if x['free'] is None else x['free']} | "
            f"{'–' if x['short'] is None else ('**' + str(x['short']) + '**' if x['short'] else 0)} | {_md(x['models']) or '–'} |" for x in rv["devices"]]
    out += ["", "## Scope and evidence", "", f"- Organisation: {s.organisation}", f"- Reference date: {d.as_of:%a %d %b %Y %H:%M}",
            f"- In scope: starting in the next {s.horizon_days} working days (to {_day(sm['last'])}); {sm['later']} later "
            f"{'joiner' if sm['later'] == 1 else 'joiners'} not checked yet", f"- Lead time target: {s.lead_time_days} working days; urgent "
            f"window: {s.urgent_days} working days", "", "| Source | File | Records |", "|---|---|---|"]
    out += [f"| {FILES.get(k, k)} | `{k}` | {v:,} |" for k, v in d.sources.items()]
    out += ["", "## Notes", "",
            "- READY: no open gap. AT RISK: at least one gap with time to fix it. BLOCKED: a gap that stops day one and whose fix no longer fits "
            f"before the start (its fix days are more than the working days left, or the start is within {s.urgent_days} working days), "
            "or a privileged group the role should not have.",
            "- A rehire reuses the original account (re-enable, restore, review groups and licences); a second account with the same "
            "employeeId is a duplicate to resolve before day one.",
            "- Accounts created by copying a model user carry the model's groups: the role profile is the reference, not the colleague.",
            f"- Decisions of the call: {TODO}", "",
            "## Sign-off", "", f"- Prepared by (IT onboarding lead): {TODO}", f"- Reviewed with (HR, service desk, workplace, facilities, "
            f"managers): {TODO}", f"- Next call: {s.next_call or TODO}", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;
--g:#dff3e8;--a:#fdf0d5;--r:#fbe0dd;--n:#eef0f2}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;
--bad:#f2685c;--info:#5aa9f0;--g:#173527;--a:#3d2f12;--r:#45201d;--n:#232a31}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}h3{font-size:15px;margin:0}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:24px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.blocked,.blocker{color:var(--bad)}.atrisk,.risk{color:var(--warn)}.ready,.ok{color:var(--ok)}.info{color:var(--info)}
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-top:5px solid var(--ok);border-radius:10px;padding:12px 14px;color:inherit}
.card.blocked{border-top-color:var(--bad)}.card.atrisk{border-top-color:var(--warn)}
.card .cd{float:right;text-align:center;line-height:1;font-weight:700;font-size:26px}.card .cd small{display:block;font-size:11px;font-weight:400;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}.chip{font-size:11px;padding:1px 6px;border-radius:6px;background:var(--n);color:var(--muted)}
.chip.ok{background:var(--g);color:inherit}.chip.risk{background:var(--a);color:inherit}.chip.blocked{background:var(--r);color:inherit;font-weight:700}
.card ul{margin:8px 0 0;padding-left:18px;font-size:13px}
td.subj{min-width:150px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:340px}td.sm{font-size:13px}
.brk{overflow-wrap:anywhere;word-break:break-word}
footer{margin-top:40px;font-size:13px}
"""


def _cls(x: str) -> str:
    return x.lower().replace(" ", "").replace("/", "")


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {_cls(cls)}'>{e(text)}</span>"


def _table(head: list[str], rows: list[str]) -> str:
    return "<div class='wrap'><table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows) + "</table></div>"


def render_html(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s = d.settings
    sm = summary(d, rv, findings)
    st = sm["status"]
    overall = _overall(sm)
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(s.organisation)} · joiners starting {e(_day(sm['first']))} to {e(_day(sm['last']))} "
         f"(next {s.horizon_days} working days) · run on {d.as_of:%a %d %b %Y %H:%M}</p>",
         f"<span class='overall {_cls(overall)}'>Overall: {e(overall)} · {st.get(BLOCKED, 0)} blocked, {st.get(AT_RISK, 0)} at risk, "
         f"{st.get(READY, 0)} ready</span>", "<div class='tiles'>"]
    lic = ", ".join(f"{s.sku_name(k)} −{v}" for k, v in sm["licence_short"].items())
    tiles = [("Joiners", str(sm["joiners"]), f"{sm['sites']} sites · {sm['later']} later"),
             ("Blocked", str(st.get(BLOCKED, 0)), f"{sm['blockers']} blockers"),
             ("At risk", str(st.get(AT_RISK, 0)), f"{sm['risks']} risks"),
             ("Ready", str(st.get(READY, 0)), "nothing open"),
             (f"Next {s.urgent_days} days", f"{sm['soon_not_ready']} of {sm['soon']}", "starting, not ready"),
             ("Late requests", str(sm["late"]), f"under {s.lead_time_days} working days"),
             ("Licences short", str(sum(sm["licence_short"].values())), lic or "pool covers the joiners"),
             ("Devices short", str(sm["device_short"]), "no stock at the site")]
    h += [f"<div class='tile'><span class='muted'>{e(x)}</span><b>{e(y)}</b><span class='muted'>{e(z)}</span></div>" for x, y, z in tiles]
    h.append("</div>")
    ff = fix_first(rv)
    h.append("<h2>Fix first</h2><p class='muted'>Blockers by due date: a gap that stops day one and no longer fits before the start, or "
             "a privileged group the role should not have.</p>")
    h.append(_table(["Joiner", "Starts", "Gap", "Action", "Owner", "Due"],
                    [f"<tr><td class='nw'><b>{e(g.joiner.name)}</b><br><span class='muted'>{e(g.joiner.site)} · {e(countdown(g.days_left))}</span></td>"
                     f"<td class='nw'>{e(_day(g.joiner.start))}</td><td class='sm brk'><b>{e(g.title)}</b>: {e(g.detail)}</td>"
                     f"<td class='fix'>{e(g.fix)}</td><td class='sm'>{e(g.owner)}</td><td class='nw'>{e(_day(g.due))}</td></tr>" for g in ff]
                    or ["<tr><td colspan='6'>No blockers.</td></tr>"]))
    h.append("<h2>Countdown</h2><p class='muted'>One card per joiner by start date, with the working days left to prepare (today "
             "included) and the state of each area.</p><div class='board'>")
    for r in rv["results"]:
        j = r.joiner
        chips = "".join(f"<span class='chip {_cls(r.areas[a])}'>{e(AREA_LABEL[a])}</span>" for a in AREAS if r.areas[a] != "n/a")
        li = [f"<li class='{g.severity}'>{e(g.title)}: {e(g.detail)}</li>" for g in r.gaps if g.severity != INFO][:3]
        more = sum(g.severity != INFO for g in r.gaps) - len(li)
        h.append(f"<div class='card {_cls(r.status)}'><span class='cd'>{r.days_left}<small>days</small></span><h3>{e(j.name)}</h3>"
                 f"<span class='muted'>{e(j.title)} · {e(j.site)} · {e(_day(j.start))}</span><br>{_pill(r.status, r.status)}"
                 f"<div class='chips'>{chips}</div>"
                 + (f"<ul>{''.join(li)}{f'<li class=muted>and {more} more</li>' if more > 0 else ''}</ul>" if li else "") + "</div>")
    h.append("</div><h2>Sites</h2>")
    h.append(_table(["Site", "Joiners", "Ready", "At risk", "Blocked", "Next start", "Most gaps in"],
                    [f"<tr><td><b>{e(x['site'])}</b></td><td class='num'>{x['joiners']}</td><td class='num ready'>{x[READY]}</td>"
                     f"<td class='num atrisk'>{x[AT_RISK]}</td><td class='num blocked'>{x[BLOCKED]}</td><td class='nw'>{e(_day(x['next_start']))}</td>"
                     f"<td class='sm'>{e(x['top_areas'] or '–')}</td></tr>" for x in rv["sites"]]))
    h.append("<h2>Licences</h2>")
    h.append(_table(["Licence", "Joiners", "Assigned", "To assign", "Free units", "Short", "Short for"],
                    [f"<tr><td><b>{e(x['name'])}</b> <span class='muted'>{e(x['sku'])}</span></td><td class='num'>{x['joiners']}</td>"
                     f"<td class='num'>{x['assigned']}</td><td class='num'>{x['to_assign']}</td>"
                     f"<td class='num'>{'–' if x['available'] is None else x['available']}</td>"
                     f"<td class='num {'blocked' if x['short'] else ''}'>{'–' if x['short'] is None else x['short']}</td>"
                     f"<td class='sm'>{e(', '.join(j.name for j in x['short_for']))}</td></tr>" for x in rv["licences"]]))
    h.append("<h2>Devices</h2>")
    h.append(_table(["Site", "Type", "Requested", "Assigned", "To assign", "Free in stock", "Short", "Models in stock"],
                    [f"<tr><td><b>{e(x['site'])}</b></td><td>{e(x['type'])}</td><td class='num'>{x['requested']}</td>"
                     f"<td class='num'>{x['assigned']}</td><td class='num'>{x['to_assign']}</td>"
                     f"<td class='num'>{'–' if x['free'] is None else x['free']}</td>"
                     f"<td class='num {'blocked' if x['short'] else ''}'>{'–' if x['short'] is None else x['short']}</td>"
                     f"<td class='sm'>{e(x['models'] or '–')}</td></tr>" for x in rv["devices"]]))
    h.append("<h2>All gaps</h2>")
    h.append(_table(["Severity", "Joiner", "Check", "Detail", "Owner", "Due"],
                    [f"<tr><td>{_pill(g.severity, 'TO DO' if g.severity == INFO else g.severity.upper())}</td><td class='nw'>{e(r.joiner.name)}</td>"
                     f"<td class='subj'>{e(g.title)}</td><td class='sm brk'>{e(g.detail)}</td><td class='sm'>{e(g.owner)}</td>"
                     f"<td class='nw'>{e(_day(g.due))}</td></tr>" for r in rv["results"] for g in r.gaps]))
    h.append("<footer class='muted'>Generated by dayone. Fictional demo data unless you ran it on your own exports. The pack for the weekly "
             "joiners call is day-one-pack.md.</footer></main></body></html>")
    return "".join(h)


__all__ = ["render_html", "pack_md", "write_status", "write_gaps", "write_licences", "write_devices", "write_actions", "write_findings"]
