$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ScriptDir ".env"
$ExampleFile = Join-Path $ScriptDir ".env.example"

if (-not (Test-Path $EnvFile)) {
    Copy-Item $ExampleFile $EnvFile
    Write-Host "Created $EnvFile from .env.example"
}

function New-FernetKey {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
}

$lines = Get-Content $EnvFile
$keyLine = $lines | Where-Object { $_ -match '^SHORTLIST_SECRET_KEY=' } | Select-Object -First 1
$currentKey = if ($keyLine) { $keyLine.Substring("SHORTLIST_SECRET_KEY=".Length).Trim() } else { "" }

if ([string]::IsNullOrWhiteSpace($currentKey) -or $currentKey -eq "change-me-to-a-strong-random-fernet-key") {
    $newKey = New-FernetKey
    if ($keyLine) {
        $updated = $lines | ForEach-Object {
            if ($_ -match '^SHORTLIST_SECRET_KEY=') { "SHORTLIST_SECRET_KEY=$newKey" } else { $_ }
        }
        Set-Content -Path $EnvFile -Value $updated -Encoding UTF8
    } else {
        Add-Content -Path $EnvFile -Value "`nSHORTLIST_SECRET_KEY=$newKey" -Encoding UTF8
    }
    Write-Host "Generated fresh Fernet SHORTLIST_SECRET_KEY in $EnvFile"
} else {
    Write-Host "SHORTLIST_SECRET_KEY is already configured in $EnvFile"
}
