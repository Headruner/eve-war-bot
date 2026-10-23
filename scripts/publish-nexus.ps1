# -----------------------------------------------------------------------------
# Build the EVE War Bot image and push it to a Nexus Docker registry (Windows).
# Needs Docker Desktop running.
#
#   Copy-Item nexus.env.example nexus.env     # fill in NEXUS_REGISTRY, NEXUS_USER
#   powershell -ExecutionPolicy Bypass -File scripts\publish-nexus.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\publish-nexus.ps1 -NoTests
#
# Pushes two tags:  <registry>/<name>:<version from app/__init__.py>  and  :latest
# -----------------------------------------------------------------------------
param([switch]$NoTests)
# native tools (docker, python) write progress to stderr - check exit codes instead
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

# read nexus.env (KEY=VALUE lines)
$cfg = @{ IMAGE_NAME = "eve-war-bot"; PLATFORM = "linux/amd64" }
if (Test-Path "nexus.env") {
    Get-Content "nexus.env" | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$' -and $_ -notmatch '^\s*#') {
            if ($Matches[2] -ne "") { $cfg[$Matches[1]] = $Matches[2] }
        }
    }
}
foreach ($k in "NEXUS_REGISTRY", "NEXUS_USER", "NEXUS_PASSWORD", "IMAGE_NAME", "PLATFORM") {
    $v = [Environment]::GetEnvironmentVariable($k)
    if ($v) { $cfg[$k] = $v }
}
if (-not $cfg["NEXUS_REGISTRY"]) { throw "Set NEXUS_REGISTRY in nexus.env (e.g. nexus.example.com:8083)" }

$registry = $cfg["NEXUS_REGISTRY"].TrimEnd("/")
$loginHost = $registry.Split("/")[0]
$version = (Select-String -Path "app\__init__.py" -Pattern '__version__ = "(.*)"').Matches[0].Groups[1].Value
$image = "$registry/$($cfg['IMAGE_NAME'])"

function Invoke-Checked([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

Write-Host "==> Image:    ${image}:$version  (+ :latest)"
Write-Host "==> Platform: $($cfg['PLATFORM'])"

if (-not $NoTests) {
    $hasPytest = $false
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try { & python -c "import pytest" 2>$null; $hasPytest = ($LASTEXITCODE -eq 0) } catch { }
    }
    if ($hasPytest) {
        Write-Host "==> Running tests"
        Invoke-Checked "tests" { python -m pytest -q }
    } else {
        Write-Host "==> pytest not installed - skipping tests (pip install -r requirements.txt pytest)"
    }
}

Write-Host "==> Logging in to $loginHost"
if ($cfg["NEXUS_USER"] -and $cfg["NEXUS_PASSWORD"]) {
    Invoke-Checked "docker login" { $cfg["NEXUS_PASSWORD"] | docker login $loginHost -u $cfg["NEXUS_USER"] --password-stdin }
} elseif ($cfg["NEXUS_USER"]) {
    Invoke-Checked "docker login" { docker login $loginHost -u $cfg["NEXUS_USER"] }
} else {
    Invoke-Checked "docker login" { docker login $loginHost }
}

Write-Host "==> Building and pushing"
Invoke-Checked "docker buildx build" {
    docker buildx build --platform $cfg["PLATFORM"] `
        --build-arg "EVE_BOT_IMAGE_REF=${image}:latest" `
        --label "org.opencontainers.image.version=$version" `
        -t "${image}:$version" -t "${image}:latest" --push .
}

Write-Host @"

==> Done. On the Linux server run (one time):

  docker login $loginHost
  mkdir -p ~/eve-war-bot && cd ~/eve-war-bot
  docker run --rm --user "`$(id -u):`$(id -g)" -v "`$PWD:/out" ${image}:latest install
  nano config/credentials.json
  bash scripts/bot.sh start

Later updates on the server:  bash scripts/bot.sh update
"@
