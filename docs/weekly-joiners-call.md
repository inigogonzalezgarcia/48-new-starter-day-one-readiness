# Weekly joiners call

How to run the day-one readiness check every week and use it in the joiners call. The tool only reads exports; accounts, licences, groups, devices and access are changed by their owners through the usual processes.

## Who attends

| Role | In the call |
|---|---|
| IT onboarding lead (chair) | Runs the exports and the check, chairs the call, follows the blockers to the end |
| HR onboarding | Start dates, changes and cancellations, late requests, rehires, manager and department changes |
| Service desk / identity | Accounts, usage location, groups, licences, the first sign-in and the Temporary Access Pass |
| Workplace (Intune / Jamf) | Laptops and phones: build, assignment, compliance, stock and orders |
| Facilities | Desk, badge, locker and anything physical on day one |
| Hiring managers (for their joiners, when there is a blocker) | Access requests and approvals, the role profile, what the joiner really needs on day one |
| IAM / security (when there is a privileged group or a rehire) | Privileged access, duplicate identities |

## Cadence

| When | What | Output |
|---|---|---|
| Monday 08:00 | HR sends `joiners.csv` (start dates in the next three weeks); export accounts, devices and licences (`scripts/Export-DayOneData.ps1`), the stock and the access requests | `data/` |
| Monday 08:30 | Run the check | `output/` |
| Monday 10:00 | Joiners call, 30 minutes (agenda in the pack) | owners and dates for every blocker |
| Daily until the start | Re-run for the joiners in the urgent window; close the blockers | updated `joiner-status.csv` |
| Day one, 09:00 | The service desk issues the Temporary Access Pass, the joiner registers MFA, the manager confirms access | |
| Day three | Ask the joiner and the manager what was missing; add it to the role profile | `role_profiles.json` |

```powershell
.\scripts\Export-DayOneData.ps1 -Joiners .\data\joiners.csv -OutputFolder .\data
```

```bash
python -m dayone review data/
```

## How to read the pack

- **Overall** is the worst status of any joiner: one blocked joiner makes the week BLOCKED.
- **The countdown** is the working days left to prepare, today included: a joiner starting tomorrow has 1. Every fix has a number of working days it needs (`fix_days`); when that no longer fits, a gap becomes a blocker.
- **Fix first** is the list for the call: each blocker leaves the call with an owner and a date, or with a fallback agreed with the manager (a loan laptop, a temporary access, a start one day later for one system).
- **Open gaps** are the risks: there is still time, but someone has to do it this week. *To do* items are steps for the day itself, such as the Temporary Access Pass.
- **Licences and devices** show the pool and the stock against everyone starting in the window, not one joiner at a time: three joiners short of E3 next Monday is a purchase today.
- **Ready** means every check passed against the role profile. It does not cover what the role profile does not list; that is what the day-three question is for.

## What "ready" means

A joiner is ready for day one when, before the start date:

1. the account exists, is enabled (or is enabled on the morning, by your process), carries the employeeId from HR, the right department and manager, and has a usage location;
2. the role's licence is assigned, and no other one;
3. the role's groups and lists are there, and nothing privileged that the role does not need;
4. every app and shared mailbox of the role is requested, approved and provisioned;
5. the laptop (and the phone, if the role needs one) is assigned to the joiner, enrolled and compliant;
6. there is a plan for the first sign-in: a Temporary Access Pass on the morning, and a way to register MFA that your policy accepts.

## Model users

Creating an account by copying a colleague is fast and hides two problems: the joiner gets everything the colleague collected over the years, including groups from previous roles and sometimes admin rights, and misses whatever the colleague never needed. The check compares the account with the role profile, not with the colleague:

- every privileged group that is not in the profile (`GRP-PRIV`) is a blocker at any distance from the start date; if the role needs admin rights, they are granted through PIM with an approval, not inherited;
- role groups missing (`GRP-MISSING`) say what the profile expects and the copy did not bring;
- when the same gap repeats for a role, fix the profile or the provisioning, not the account.

## Rehires

A rehire is someone whose employeeId already has an account from an earlier employment.

- Reuse the original account: re-enable it, reset the password, review its groups and licences against today's role, and restore the mailbox and OneDrive if they were kept.
- A second account with the same employeeId (`ACC-DUPLICATE`) splits the history, confuses HR-driven provisioning and leaver processes, and usually wastes a licence. Decide which one stays before day one, usually the original, and remove the other.
- HR should flag rehires in the request; the check finds them anyway from the employeeId.

## Late requests

A request raised two days before the start leaves no time for an order, an approval or a licence purchase. Record every late request (`REQ-LATE`), agree with HR and the manager what will be ready on day one and what follows, and bring the count to HR each month: the target lead time is in `settings.json` (`lead_time_days`).

## Keeping it useful

- Keep `role_profiles.json` owned by IT and reviewed with HR and the managers of each role twice a year.
- Keep the `fix_days` honest: if a laptop order takes seven working days, say seven.
- Keep `stock.csv` current on the morning of the call; the forecast is only as good as the count.
- Do not use the status to blame a team: a blocker is a date and an owner, not a score.
