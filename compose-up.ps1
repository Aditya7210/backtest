param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"

$composeArgs = @("up", "-d")
if ($Build) {
    $composeArgs += "--build"
}

docker compose @composeArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$healthUrl = "http://localhost:8501/_stcore/health"
for ($i = 0; $i -lt 45; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
            break
        }
    } catch {
        # App may still be booting; retry until timeout.
    }
    Start-Sleep -Seconds 1
}

Start-Process "http://localhost:8501"
