param(
    [Parameter(Mandatory = $true)][string]$Payload,
    [ValidateSet('Send', 'Verify')][string]$Mode = 'Send'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$sendAttempted = $false
$mail = $null
$attachment = $null
$outlook = $null
$namespace = $null
$verified = $false
try {
    $data = Get-Content -LiteralPath $Payload -Raw -Encoding UTF8 | ConvertFrom-Json
    $outlook = New-Object -ComObject Outlook.Application
    $namespace = $outlook.GetNamespace('MAPI')
    if ($namespace.Accounts.Count -eq 0) { throw 'No signed-in classic Outlook account.' }
    if ($Mode -eq 'Send') {
        $filter = "[Subject] = '" + $data.subject.Replace("'", "''") + "'"
        foreach ($folderId in @(5, 4)) {
            $folder = $namespace.GetDefaultFolder($folderId)
            $matches = $folder.Items.Restrict($filter)
            if ($matches.Count -gt 0) {
                Write-Output 'Already present in Outlook Sent Items or Outbox.'
                exit 0
            }
        }
    }
    $mail = $outlook.CreateItem(0)
    $mail.To = $data.recipient
    $mail.Subject = $data.subject
    $mail.BodyFormat = 2
    $mail.HTMLBody = [IO.File]::ReadAllText($data.body, [Text.Encoding]::UTF8)
    if (-not $mail.Recipients.ResolveAll()) { throw 'Outlook could not resolve the recipient.' }
    $attachment = $mail.Attachments.Add($data.chart, 1, 0)
    $attachment.PropertyAccessor.SetProperty(
        'http://schemas.microsoft.com/mapi/proptag/0x3712001F', 'dayledger-chart')
    $attachment.PropertyAccessor.SetProperty(
        'http://schemas.microsoft.com/mapi/proptag/0x370E001F', 'image/png')
    $attachment.PropertyAccessor.SetProperty(
        'http://schemas.microsoft.com/mapi/proptag/0x7FFE000B', $true)
    $mail.Save()
    if ($Mode -eq 'Verify') {
        $entryId = $mail.EntryID
        $saved = $namespace.GetItemFromID($entryId)
        if ($saved.Attachments.Count -ne 1) { throw 'Inline chart was not saved.' }
        $cid = $saved.Attachments.Item(1).PropertyAccessor.GetProperty(
            'http://schemas.microsoft.com/mapi/proptag/0x3712001F')
        if ($cid -ne 'dayledger-chart') { throw 'Inline chart content ID is invalid.' }
        $saved.Delete()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($saved)
        $verified = $true
        Write-Output 'Verified Outlook recipient, HTML body and inline PNG. No email sent.'
    } else {
        $sendAttempted = $true
        $mail.Send()
        Write-Output 'Handed to Outlook for delivery. Offline messages remain in Outbox.'
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    if ($null -ne $mail -and -not $sendAttempted -and -not $verified) {
        try { $mail.Delete() } catch {}
    }
    if ($sendAttempted) { exit 3 } else { exit 2 }
} finally {
    foreach ($object in @($attachment, $mail, $namespace, $outlook)) {
        if ($null -ne $object) {
            try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($object) } catch {}
        }
    }
}
