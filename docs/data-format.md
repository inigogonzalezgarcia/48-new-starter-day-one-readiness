# Data format

Put the files in one folder and run `python -m dayone review <folder>`. `joiners.csv` and `accounts.csv` are required; `role_profiles.json` is what the accounts are compared with, and every other file adds its checks (a check without its file is skipped, not passed). Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the alternatives below are accepted. Dates as ISO 8601 (`2026-11-16`, `2026-11-02T10:15:00Z`), `dd/mm/yyyy` or `MM/dd/yyyy`; the time zone suffix is ignored. Yes/no columns accept `Yes`, `True`, `1`. Lists inside a cell (licences, groups) are separated with `;`.

`scripts/Export-DayOneData.ps1` writes `accounts.csv`, `devices.csv`, `licences.csv` and, with `-IncludeAutopilot`, `autopilot.csv` from Microsoft Graph. `joiners.csv` comes from HR or the joiner requests of the ITSM tool; `stock.csv` from the asset register; `access_requests.csv` from the ITSM access requests.

## How the check works

| Step | Rule |
|---|---|
| Scope | Joiners whose start date is today or later and within `horizon_days` working days. Later joiners are counted, not checked; joiners whose start date has passed are left out |
| Countdown | Working days left to prepare: from today (included) to the start date (excluded), without weekends and the dates in `holidays`. A joiner starting tomorrow has 1 |
| Matching | The account with the joiner's employeeId; if there is none, the planned UPN from HR; if there is none, a single account with the same display name and no employeeId (reported as `ACC-NOID`). An enabled account wins over a disabled one; a disabled account created more than 60 days before the request belongs to an earlier employment (a rehire) |
| Role profile | The profile whose `job_titles` contains the joiner's job title; else the first profile with no job titles whose `departments` contains the department; else `default`. `{site}` and `{department}` in group names are replaced with the joiner's |
| Gap | Every check that fails is a gap with an owner, the working days its fix needs (`fix_days`) and a due date: the start date minus those working days, and never before today |
| Severity | A gap that stops day one (account, licence, role groups, apps, device, a phone the role needs, MFA) is a **blocker** when its fix days are more than the working days left, or the start is within `urgent_days`; otherwise a **risk**. A privileged group the role should not have is always a blocker. Data gaps (department, manager, employeeId, late request, extra licence) are risks. *To do* (`info`) marks a step for the day itself and does not change the status |
| Status | **BLOCKED** with any blocker, **AT RISK** with any risk, **READY** otherwise |
| Licence pool | The joiners still needing a SKU, in start date order, take the free units (`Enabled - ConsumedUnits` from `licences.csv`, or `licence_available` in settings); the ones beyond the free units get `LIC-POOL` with the purchase lead time (`fix_days.licence_purchase`) |
| Stock | The same per site and device type: the joiners with no device take the free units (`InStock - Reserved`) in start date order; beyond them, `DEV-NOSTOCK` with the order lead time (`fix_days.device_order`) |

## joiners.csv

One row per joiner, from HR or the ITSM joiner request.

| Column | Alternatives | Notes |
|---|---|---|
| EmployeeId | Employee ID, employee number, worker id | Required; the key to the account (`employeeId` in Entra ID) |
| Name | Full name, DisplayName | |
| StartDate | Start date, first day, hire date | Required |
| Site | Location, office | The site code (`MAD`, `BCN`); same codes as `stock.csv` |
| Department | dept, team | Compared with the account and used to find the role profile |
| JobTitle | Job title, Role, position | Used to find the role profile |
| Manager | ManagerUPN, line manager, manager email | The manager's UPN or e-mail; compared with the account's manager. Owner of `APP-NOREQ`, `MBX-NOREQ` and `PHN-ROLE` |
| ContractType | contract, employment type | Informational (permanent, temporary, contractor) |
| DeviceType | Device, laptop | `Windows laptop`, `MacBook` or `None` (anything with *mac* is a Mac, *none* or *shared* is no device, the rest is Windows) |
| Phone | Mobile phone, company phone | Yes when a company phone was requested |
| Ticket | RequestTicket, request | The joiner request in the ITSM tool |
| Raised | RequestRaised, date raised, requested on | Date the request was raised; under `lead_time_days` working days before the start is `REQ-LATE` |
| UserPrincipalName | UPN, planned upn | Optional: the planned UPN, used when no account has the employeeId |

## role_profiles.json

```json
{
  "profiles": [
    {"name": "Trader", "job_titles": ["Trader"], "licence": "SPE_E5",
     "groups": ["SG-Trading-Desk", "SG-MarketData-Users", "SG-Site-{site}"], "distribution_lists": ["DL-Trading"],
     "apps": ["Bloomberg Terminal", "Trading Platform (OMS)"], "shared_mailboxes": ["trading-confirmations"],
     "phone_required": true},
    {"name": "Finance", "departments": ["Finance"], "licence": "SPE_E3", "groups": ["SG-Finance", "SG-Site-{site}"]},
    {"name": "Service Desk Analyst", "job_titles": ["Service Desk Analyst"], "licence": "SPE_E3",
     "groups": ["SG-IT-ServiceDesk"], "privileged_allowed": ["SG-PIM-Helpdesk-Administrators"]}
  ],
  "default": {"licence": "SPE_E3", "groups": ["SG-Site-{site}", "SG-All-Staff"]}
}
```

| Key | Notes |
|---|---|
| `name` | Shown in the reports |
| `job_titles`, `departments` | How a joiner is matched (job title first) |
| `licence` | The SKU part number (`skuPartNumber` of Microsoft Graph): `SPE_E3` is Microsoft 365 E3, `SPE_E5` Microsoft 365 E5, `SPE_F1` Microsoft 365 F3, `ENTERPRISEPACK` Office 365 E3 |
| `groups` | Security and Microsoft 365 groups the role needs on day one (`GRP-MISSING`) |
| `distribution_lists` | Lists the joiner should be in (`GRP-DL`, a risk, never a blocker) |
| `apps` | Applications that need an access request (`APP-*`, checked against `access_requests.csv`) |
| `shared_mailboxes` | Shared mailboxes that need a request (`MBX-*`) |
| `phone_required` | The role needs a company phone (`PHN-ROLE` when none was requested; `PHN-NONE` becomes a blocker near the start) |
| `mfa_required` | Default `true`; `false` for roles that do not sign in with MFA on day one (shared devices) |
| `privileged_allowed` | Privileged groups the role is entitled to (for example a PIM-eligible helpdesk group), so they are not flagged |

## accounts.csv

From Microsoft Graph (`Get-MgUser`, `Get-MgUserManager`, `Get-MgUserMemberOf`, `Get-MgUserAuthenticationMethod`), or an Active Directory export with the same columns.

| Column | Alternatives | Notes |
|---|---|---|
| UserPrincipalName | UPN, username | Required |
| DisplayName | name | Used for the name match |
| EmployeeId | employee number | The key to the joiner |
| AccountEnabled | enabled | `False` is `ACC-DISABLED`, unless `enable_on_start` is true |
| CreatedDateTime | whencreated, created | Tells a rehire's old account from the new one |
| Department, JobTitle | | Compared with HR |
| Manager | ManagerUPN | The manager's UPN |
| UsageLocation | usage location | Two-letter country code; a licence cannot be assigned to a user with no usage location |
| AssignedLicenses | licenses, skus | SKU part numbers separated by `;` |
| Groups | MemberOf | Group (and directory role) display names separated by `;` |
| MfaMethods | authentication methods | Number of methods registered other than the password and the Temporary Access Pass |
| TemporaryAccessPass | tap | Yes when a Temporary Access Pass exists |
| OnPremisesSyncEnabled | synced | With `hybrid: true`, `False` is `ACC-CLOUDONLY` |

## devices.csv

From Intune (`Get-MgDeviceManagementManagedDevice`) or a Jamf Pro inventory export.

| Column | Alternatives | Notes |
|---|---|---|
| DeviceName | Computer Name, name | Required (or the serial number) |
| SerialNumber | Serial Number | |
| UserPrincipalName | Email Address, primary user, assigned user | The joiner's UPN; how a device is linked to the joiner |
| OperatingSystem | Operating System, platform | `Windows`, `macOS` (laptops), `iOS`, `Android` (phones); `iPadOS` is a tablet and is not counted as a phone |
| Model | | |
| ComplianceState | compliance | Anything but `compliant` on an enrolled laptop is `DEV-NONCOMPLIANT` (Intune also reports `noncompliant`, `inGracePeriod`, `unknown`) |
| ManagementState | managed | Empty or `managed` is enrolled |
| LastSyncDateTime | Last Check-in | Informational |
| ManagedDeviceOwnerType | ownership | Informational |
| IsEncrypted | encrypted, FileVault 2 Status | `False` is named in the reason (BitLocker or FileVault pending) |

## autopilot.csv (optional)

Windows Autopilot registrations (`Get-MgDeviceManagementWindowsAutopilotDeviceIdentity`), used as data only: a registered device with the joiner as assigned user counts as their laptop, enrolled or not (it enrols at the first sign-in).

| Column | Alternatives | Notes |
|---|---|---|
| SerialNumber | serial | Required |
| GroupTag | group tag, order id | Informational |
| UserPrincipalName | assigned user | The joiner's UPN |
| EnrollmentState | enrollment state | `enrolled`, `notContacted`, `failed`… |
| Model | | |

## licences.csv (optional)

From `Get-MgSubscribedSku`. Free units = `Enabled - ConsumedUnits`; it overrides `licence_available` in settings for the same SKU. Without either, the pool is not checked.

| Column | Alternatives | Notes |
|---|---|---|
| SkuPartNumber | sku | Required |
| SkuId | | Informational |
| Enabled | PrepaidUnitsEnabled, purchased | `prepaidUnits.enabled` |
| ConsumedUnits | consumed, assigned | |

## stock.csv (optional)

| Column | Alternatives | Notes |
|---|---|---|
| Site | Location | Required |
| DeviceType | type, category | `Windows laptop`, `MacBook` or `Phone` (iPhone, Android) |
| Model | | Shown in the device forecast and as *free elsewhere* |
| InStock | quantity, available | |
| Reserved | allocated | Units already promised; free = in stock − reserved |

Without `stock.csv` a joiner with no device gets `DEV-NONE` with the build time, and stock is not forecast.

## access_requests.csv (optional)

One row per app or shared mailbox request, from the ITSM tool. Without it, apps and shared mailboxes are not checked.

| Column | Alternatives | Notes |
|---|---|---|
| EmployeeId | | The joiner (or the UPN) |
| UserPrincipalName | UPN | |
| Item | Application, resource | Same name as in the role profile (case and punctuation ignored) |
| Kind | Type | `Application` or `Shared mailbox` |
| Status | state | `Fulfilled`, `Done`, `Completed`, `Provisioned`, `Granted` are done; `Approved` is approved, not provisioned; `Rejected`, `Declined`, `Cancelled` are rejected; anything else is waiting for approval |
| Ticket | Key | Shown in the reason |
| Approver | approved by | Owner of `APP-PENDING` |

## settings.json

| Setting | Default | Meaning |
|---|---|---|
| `organisation` | | Shown in the reports |
| `as_of` | now | Reference date and time (`--as-of` overrides it) |
| `horizon_days` | 10 | Joiners starting within this many working days are checked |
| `lead_time_days` | 10 | A request raised fewer working days before the start is late |
| `urgent_days` | 3 | Inside this window every day-one gap is a blocker |
| `holidays` | [] | Dates (`YYYY-MM-DD`) that are not working days |
| `enable_on_start` | false | True when accounts are enabled on the morning of day one (a disabled account is then not a gap) |
| `hybrid` | false | True when accounts are created in AD and synced (a cloud-only account is then `ACC-CLOUDONLY`) |
| `mfa_own_phone_allowed` | true | False when joiners cannot register MFA on a personal phone (no company phone and no method is then `MFA-NODEVICE`) |
| `fix_days` | account 1, licence 1, licence_purchase 3, groups 1, access_request 3, access_approval 2, access_fulfil 1, device_build 2, device_order 5, phone 2, mfa 0, data 0 | Working days each fix needs before the start |
| `licence_available` | {} | Free units per SKU when there is no `licences.csv` |
| `sku_names` | SPE_E3, SPE_E5, SPE_F1, ENTERPRISEPACK… | Friendly names; an assigned SKU in this list that is not the role's is `LIC-WRONG` or `LIC-EXTRA` |
| `privileged_groups` | Domain Admins, Enterprise Admins… | Exact names of privileged groups |
| `privileged_patterns` | admins, administrator, privileged, pim- | Parts of a name that make a group privileged |
| `owners` | | Owner per area: `hr`, `identity`, `licensing`, `workplace`, `mobile`, `access`, `security` |
| `next_call` | | Date of the next weekly joiners call, in the pack |

## Checks

| Code | Area | Blocks day one | Gap |
|---|---|---|---|
| REQ-LATE | Request | no | Request raised fewer than `lead_time_days` working days before the start |
| ACC-MISSING | Account | yes | No account with the employeeId, planned UPN or name |
| ACC-REHIRE | Account | yes | Only a disabled account from an earlier employment: re-enable it, do not create a new one |
| ACC-DUPLICATE | Account | yes | A new account was created while the old one has the same employeeId |
| ACC-DISABLED | Account | yes | The joiner's account is disabled (unless `enable_on_start`) |
| ACC-NOID | Account | no | Matched by name: employeeId empty |
| ACC-DEPT, ACC-MANAGER | Account | no | Department or manager different from HR |
| ACC-USAGELOC | Account | yes | No usage location |
| ACC-CLOUDONLY | Account | no | Cloud-only account in a hybrid directory |
| LIC-NONE, LIC-WRONG | Licence | yes | The role's licence not assigned, or another one instead |
| LIC-EXTRA | Licence | no | Another licence as well as the role's |
| LIC-POOL | Licence | yes | No free unit left for this joiner |
| GRP-MISSING | Groups | yes | Role groups missing |
| GRP-DL | Groups | no | Distribution lists missing |
| GRP-PRIV | Groups | always a blocker | Privileged group not in the role profile (often copied from a model user) |
| APP-NOREQ, APP-PENDING, APP-APPROVED, APP-REJECTED | Access | yes | App access not requested, waiting for approval, approved and not provisioned, or rejected |
| MBX-NOREQ, MBX-PENDING | Access | no | Shared mailbox not requested or not provisioned |
| DEV-NONE, DEV-NOSTOCK | Device | yes | No laptop assigned (with stock at the site, or none) |
| DEV-PLATFORM | Device | yes | Windows assigned for a Mac request or the other way round |
| DEV-NONCOMPLIANT | Device | yes | Enrolled but not compliant |
| PHN-NONE | Phone | when the role needs a phone | Phone requested, none assigned |
| PHN-ROLE | Phone | yes | The role needs a phone and none was requested |
| MFA-NODEVICE | MFA | yes | No method, no Temporary Access Pass, no company phone and personal phones not allowed |
| MFA-TAP | MFA | to do | Within the urgent window with no method yet: issue a Temporary Access Pass for the first sign-in |
