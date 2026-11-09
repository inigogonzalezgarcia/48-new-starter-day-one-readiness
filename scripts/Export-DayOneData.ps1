<#
.SYNOPSIS
    Read-only export of the data that dayone reads from Microsoft Graph: the accounts of the joiners (accounts.csv), their Intune
    devices (devices.csv), the subscribed licences (licences.csv) and, optionally, the Windows Autopilot registrations (autopilot.csv).

.DESCRIPTION
    Only read operations: Get-Mg* cmdlets. Nothing is created, changed, assigned or deleted, and no credential or token is written to
    disk: Connect-MgGraph signs in interactively and the session stays in memory.

    Modules (Microsoft Graph PowerShell SDK): Microsoft.Graph.Authentication, Microsoft.Graph.Users,
    Microsoft.Graph.Identity.SignIns, Microsoft.Graph.Identity.DirectoryManagement, Microsoft.Graph.DeviceManagement and, with
    -IncludeAutopilot, Microsoft.Graph.DeviceManagement.Enrollment.

    Read scopes (delegated): User.Read.All, GroupMember.Read.All, UserAuthenticationMethod.Read.All,
    DeviceManagementManagedDevices.Read.All and Organization.Read.All; DeviceManagementServiceConfig.Read.All only with
    -IncludeAutopilot. Reading other users' authentication methods also needs an Entra role that allows it (for example
    Authentication Administrator or Global Reader, as your tenant grants it).

    Accounts (accounts.csv)
      Get-MgUser -All -Property id, userPrincipalName, displayName, employeeId, accountEnabled, createdDateTime, department, jobTitle,
      usageLocation, assignedLicenses, onPremisesSyncEnabled. Only the users whose employeeId is in joiners.csv, or that were created in
      the last -CreatedWithinDays days, are kept (employeeId is only returned when it is selected, which -Property does).
      For each of them: Get-MgUserManager (the manager's UPN), Get-MgUserMemberOf -All (the display names of the groups and directory
      roles) and Get-MgUserAuthenticationMethod (the methods other than the password and the Temporary Access Pass are counted in
      MfaMethods; TemporaryAccessPass says whether a pass exists). The licence GUIDs are turned into SKU part numbers (SPE_E3, SPE_F1)
      with Get-MgSubscribedSku.

    Licences (licences.csv)
      Get-MgSubscribedSku -All: SkuPartNumber, SkuId, PrepaidUnits.Enabled as Enabled and ConsumedUnits. Free units = Enabled - Consumed.

    Devices (devices.csv)
      Get-MgDeviceManagementManagedDevice -All -Property deviceName, serialNumber, userPrincipalName, operatingSystem, model,
      complianceState, managementState, lastSyncDateTime, managedDeviceOwnerType, isEncrypted, for the joiners' UPNs only.
      A Jamf Pro computer or mobile device inventory export with the same columns (Computer Name, Serial Number, Email Address,
      Operating System, Model, Last Check-in) can be appended or used instead; dayone accepts both sets of column names.

    Windows Autopilot (autopilot.csv, -IncludeAutopilot)
      Get-MgDeviceManagementWindowsAutopilotDeviceIdentity -All: serialNumber, groupTag, userPrincipalName, enrollmentState, model, for
      the joiners' UPNs. Used as data only: a registered device assigned to the joiner counts as their device.

    Not exported here (see docs/data-format.md): joiners.csv (HR or the ITSM joiner requests), role_profiles.json, stock.csv (the
    asset register), access_requests.csv (the ITSM access requests) and settings.json.

.PARAMETER Joiners
    The joiners.csv from HR (EmployeeId column), used to select the accounts. Default .\data\joiners.csv.

.PARAMETER OutputFolder
    Where the CSV files are written (default .\data).

.PARAMETER CreatedWithinDays
    Also keep the accounts created in the last N days (default 45), to catch accounts created without an employeeId.

.PARAMETER IncludeAutopilot
    Export the Windows Autopilot registrations too (adds the DeviceManagementServiceConfig.Read.All scope).

.EXAMPLE
    .\scripts\Export-DayOneData.ps1 -Joiners .\data\joiners.csv -OutputFolder .\data

.EXAMPLE
    .\scripts\Export-DayOneData.ps1 -Joiners .\data\joiners.csv -OutputFolder .\data -IncludeAutopilot -CreatedWithinDays 60
#>
[CmdletBinding()]
param(
    [string] $Joiners = '.\data\joiners.csv',
    [string] $OutputFolder = '.\data',
    [int] $CreatedWithinDays = 45,
    [switch] $IncludeAutopilot
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

function Format-Date($Value) {
    if (-not $Value) { return '' }
    return ([datetime] $Value).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}

$scopes = @('User.Read.All', 'GroupMember.Read.All', 'UserAuthenticationMethod.Read.All', 'DeviceManagementManagedDevices.Read.All',
            'Organization.Read.All')
if ($IncludeAutopilot) { $scopes += 'DeviceManagementServiceConfig.Read.All' }
Connect-MgGraph -NoWelcome -Scopes $scopes

# ------------------------------------------------------------------ licences
$skus = @{}
$licences = foreach ($s in Get-MgSubscribedSku -All) {
    $skus[[string] $s.SkuId] = $s.SkuPartNumber
    [pscustomobject]@{
        SkuPartNumber = $s.SkuPartNumber
        SkuId         = $s.SkuId
        Enabled       = $s.PrepaidUnits.Enabled
        ConsumedUnits = $s.ConsumedUnits
    }
}
$licences | Export-Csv -Path (Join-Path $OutputFolder 'licences.csv') -NoTypeInformation -Encoding utf8
Write-Host ("{0,7} licence SKUs -> licences.csv" -f @($licences).Count)

# ------------------------------------------------------------------ accounts
$ids = @{}
if (Test-Path $Joiners) {
    foreach ($j in Import-Csv $Joiners) { if ($j.EmployeeId) { $ids[$j.EmployeeId.Trim()] = $true } }
}
$since = (Get-Date).AddDays(-$CreatedWithinDays)
$props = 'id', 'userPrincipalName', 'displayName', 'employeeId', 'accountEnabled', 'createdDateTime', 'department', 'jobTitle',
         'usageLocation', 'assignedLicenses', 'onPremisesSyncEnabled'
$users = Get-MgUser -All -Property $props | Where-Object {
    ($_.EmployeeId -and $ids.ContainsKey($_.EmployeeId)) -or ($_.CreatedDateTime -and $_.CreatedDateTime -ge $since)
}
$upns = @{}
$accounts = foreach ($u in $users) {
    $upns[$u.UserPrincipalName.ToLower()] = $true
    $manager = ''
    try { $manager = (Get-MgUserManager -UserId $u.Id).AdditionalProperties['userPrincipalName'] } catch { $manager = '' }
    $groups = Get-MgUserMemberOf -UserId $u.Id -All | ForEach-Object { $_.AdditionalProperties['displayName'] } | Where-Object { $_ }
    $methods = @(Get-MgUserAuthenticationMethod -UserId $u.Id | ForEach-Object { $_.AdditionalProperties['@odata.type'] })
    $mfa = @($methods | Where-Object { $_ -notin @('#microsoft.graph.passwordAuthenticationMethod',
                                                    '#microsoft.graph.temporaryAccessPassAuthenticationMethod') }).Count
    $tap = $methods -contains '#microsoft.graph.temporaryAccessPassAuthenticationMethod'
    [pscustomobject]@{
        UserPrincipalName     = $u.UserPrincipalName
        DisplayName           = $u.DisplayName
        EmployeeId            = $u.EmployeeId
        AccountEnabled        = $u.AccountEnabled
        CreatedDateTime       = Format-Date $u.CreatedDateTime
        Department            = $u.Department
        JobTitle              = $u.JobTitle
        Manager               = $manager
        UsageLocation         = $u.UsageLocation
        AssignedLicenses      = (@($u.AssignedLicenses | ForEach-Object { $skus[[string] $_.SkuId] }) -join ';')
        Groups                = (@($groups) -join ';')
        MfaMethods            = $mfa
        TemporaryAccessPass   = if ($tap) { 'Yes' } else { 'No' }
        OnPremisesSyncEnabled = $u.OnPremisesSyncEnabled
    }
}
$accounts | Export-Csv -Path (Join-Path $OutputFolder 'accounts.csv') -NoTypeInformation -Encoding utf8
Write-Host ("{0,7} accounts -> accounts.csv" -f @($accounts).Count)

# ------------------------------------------------------------------ devices (Intune)
$dprops = 'deviceName', 'serialNumber', 'userPrincipalName', 'operatingSystem', 'model', 'complianceState', 'managementState',
          'lastSyncDateTime', 'managedDeviceOwnerType', 'isEncrypted'
$devices = foreach ($d in Get-MgDeviceManagementManagedDevice -All -Property $dprops) {
    if (-not $d.UserPrincipalName -or -not $upns.ContainsKey($d.UserPrincipalName.ToLower())) { continue }
    [pscustomobject]@{
        DeviceName             = $d.DeviceName
        SerialNumber           = $d.SerialNumber
        UserPrincipalName      = $d.UserPrincipalName
        OperatingSystem        = $d.OperatingSystem
        Model                  = $d.Model
        ComplianceState        = [string] $d.ComplianceState
        ManagementState        = [string] $d.ManagementState
        LastSyncDateTime       = Format-Date $d.LastSyncDateTime
        ManagedDeviceOwnerType = [string] $d.ManagedDeviceOwnerType
        IsEncrypted            = $d.IsEncrypted
    }
}
$devices | Export-Csv -Path (Join-Path $OutputFolder 'devices.csv') -NoTypeInformation -Encoding utf8
Write-Host ("{0,7} devices -> devices.csv" -f @($devices).Count)

# ------------------------------------------------------------------ Windows Autopilot (optional, data only)
if ($IncludeAutopilot) {
    $ap = foreach ($a in Get-MgDeviceManagementWindowsAutopilotDeviceIdentity -All) {
        if (-not $a.UserPrincipalName -or -not $upns.ContainsKey($a.UserPrincipalName.ToLower())) { continue }
        [pscustomobject]@{
            SerialNumber      = $a.SerialNumber
            GroupTag          = $a.GroupTag
            UserPrincipalName = $a.UserPrincipalName
            EnrollmentState   = [string] $a.EnrollmentState
            Model             = $a.Model
        }
    }
    $ap | Export-Csv -Path (Join-Path $OutputFolder 'autopilot.csv') -NoTypeInformation -Encoding utf8
    Write-Host ("{0,7} Autopilot registrations -> autopilot.csv" -f @($ap).Count)
}

Write-Host 'Add joiners.csv, role_profiles.json, stock.csv, access_requests.csv and settings.json, then run:'
Write-Host '  python -m dayone review data/'
