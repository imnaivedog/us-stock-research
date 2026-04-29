<#
.SYNOPSIS
  Deploy and verify the M3-S1 daily_indicators + signals Cloud Run pipeline.

.DEPENDENCIES
  Required tools in PATH:
    - gcloud: https://cloud.google.com/sdk/docs/install
    - cloud-sql-proxy: https://cloud.google.com/sql/docs/postgres/connect-auth-proxy
    - psql: install PostgreSQL client tools and add bin/ to PATH
    - uv: https://docs.astral.sh/uv/getting-started/installation/

.AUTH
  Configure ADC before running:
    gcloud auth application-default login
    gcloud config set project naive-usstock-live

.EXAMPLES
  .\scripts\deploy_signals_pipeline.ps1
  .\scripts\deploy_signals_pipeline.ps1 -SkipBackfill
  .\scripts\deploy_signals_pipeline.ps1 -DryRun
#>

param(
    [switch]$SkipBackfill,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ProjectId = "naive-usstock-live"
$Region = "us-central1"
$Instance = "naive-usstock-live:us-central1:naive-usstock-db"
$DbHost = "127.0.0.1"
$DbPort = "5433"
$DbName = "usstock"
$DbUser = "postgres"
$PsqlArgs = @("--host=$DbHost", "--port=$DbPort", "--dbname=$DbName", "--username=$DbUser")
$ProxyLog = "logs/cloud-sql-proxy.log"
$StartedAt = Get-Date
$ProxyProc = $null

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Require-Tool {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required tool in PATH: $Name"
    }
}

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
    Write-Step $Label
    if ($DryRun) {
        Write-Host "[DRYRUN] $Command"
        return $null
    }
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Label"
    }
}

function Invoke-Sql {
    param([string]$Sql)
    Invoke-Step "psql: $Sql" {
        psql @PsqlArgs -v ON_ERROR_STOP=1 -c $Sql
    }
}

try {
    Write-Step "Checking required tools"
    foreach ($tool in @("gcloud", "cloud-sql-proxy", "psql", "uv")) {
        if ($DryRun) {
            Write-Host "[DRYRUN] require $tool"
        } else {
            Require-Tool $tool
        }
    }

    Write-Step "Starting Cloud SQL Auth Proxy on port $DbPort"
    if ($DryRun) {
        Write-Host "[DRYRUN] Start-Process cloud-sql-proxy $Instance --port $DbPort > $ProxyLog"
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $ProxyLog) | Out-Null
        Set-Content -Path $ProxyLog -Value "" -Encoding UTF8
        $proxyCommand = "cloud-sql-proxy $Instance --port $DbPort > `"$ProxyLog`" 2>&1"
        $ProxyProc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList @("/c", $proxyCommand) `
            -WindowStyle Hidden `
            -PassThru
        $proxyReady = $false
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            if (Test-NetConnection -ComputerName $DbHost -Port $DbPort -InformationLevel Quiet) {
                $proxyReady = $true
                break
            }
            Start-Sleep -Seconds 1
        }
        if (-not $proxyReady) {
            Write-Host "Cloud SQL Auth Proxy log:"
            Get-Content $ProxyLog -ErrorAction SilentlyContinue | Write-Host
            throw "Cloud SQL Auth Proxy did not listen on ${DbHost}:$DbPort within 30s"
        }
    }

    Write-Step "Loading DB password from Secret Manager"
    if ($DryRun) {
        Write-Host "[DRYRUN] `$env:PGPASSWORD = gcloud secrets versions access latest --secret=db-password --project=$ProjectId"
    } else {
        $env:PGPASSWORD = (& gcloud secrets versions access latest --secret=db-password --project=$ProjectId)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($env:PGPASSWORD)) {
            throw "Failed to load db-password secret"
        }
    }

    $migrations = @(
        "db/migrations/003_create_daily_indicators.sql",
        "db/migrations/004_create_signals_l1_l2.sql",
        "db/migrations/005_extend_signals_for_l3_l4.sql",
        "db/migrations/006_add_macro_state_to_signals_daily.sql"
    )
    foreach ($migration in $migrations) {
        Invoke-Step "Applying migration $migration" {
            psql @PsqlArgs -v ON_ERROR_STOP=1 -f $migration
        }
    }

    $schemaSql = @"
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND (tablename LIKE 'signals_%' OR tablename = 'daily_indicators')
ORDER BY tablename;
"@
    Invoke-Step "Verifying schema tables" {
        psql @PsqlArgs -v ON_ERROR_STOP=1 -c $schemaSql
    }
    if ($DryRun) {
        Write-Host "[DRYRUN] assert schema table count == 6"
    } else {
        $schemaCount = psql @PsqlArgs -At -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public' AND (tablename LIKE 'signals_%' OR tablename = 'daily_indicators');"
        if ($LASTEXITCODE -ne 0 -or [int]$schemaCount -ne 6) {
            throw "Expected 6 signal pipeline tables, got $schemaCount"
        }
    }

    Invoke-Step "Replacing compute-indicators-daily Cloud Run Job" {
        gcloud run jobs replace deploy/cloud_run/compute-indicators-daily.yaml --region=$Region --project=$ProjectId
    }
    Invoke-Step "Replacing signals-daily-job Cloud Run Job" {
        gcloud run jobs replace deploy/cloud_run/signals-daily.yaml --region=$Region --project=$ProjectId
    }

    if ($SkipBackfill) {
        Write-Step "Skipping daily_indicators backfill"
    } else {
        Invoke-Step "Backfilling daily_indicators for 2025-04-24 to 2026-04-29" {
            uv run python scripts/backfill_indicators.py --start 2025-04-24 --end 2026-04-29
        }
    }

    Invoke-Step "Executing signals-daily-job" {
        gcloud run jobs execute signals-daily-job --region=$Region --project=$ProjectId --wait
    }

    Write-Step "Acceptance SQL: daily_indicators"
    if ($DryRun) {
        Write-Host "[DRYRUN] psql <split connection args> -c `"SELECT COUNT(*) AS daily_indicators_rows, MIN(trade_date) AS min_date, MAX(trade_date) AS max_date FROM daily_indicators;`""
    } else {
        psql @PsqlArgs -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) AS daily_indicators_rows, MIN(trade_date) AS min_date, MAX(trade_date) AS max_date FROM daily_indicators;"
        if ($LASTEXITCODE -ne 0) { throw "daily_indicators acceptance SQL failed" }
    }

    Write-Step "Acceptance SQL: signals tables"
    $signalsSql = @"
SELECT 'signals_alerts' AS tbl, COUNT(*) FROM signals_alerts
UNION ALL SELECT 'signals_daily', COUNT(*) FROM signals_daily
UNION ALL SELECT 'signals_sectors_daily', COUNT(*) FROM signals_sectors_daily
UNION ALL SELECT 'signals_stocks_daily', COUNT(*) FROM signals_stocks_daily
UNION ALL SELECT 'signals_themes_daily', COUNT(*) FROM signals_themes_daily
ORDER BY 1;
"@
    if ($DryRun) {
        Write-Host "[DRYRUN] psql <split connection args> -c <signals table counts>"
    } else {
        psql @PsqlArgs -v ON_ERROR_STOP=1 -c $signalsSql
        if ($LASTEXITCODE -ne 0) { throw "signals acceptance SQL failed" }
    }

    Write-Step "Done"
    $Head = if ($DryRun) { "<dry-run>" } else { (git rev-parse --short HEAD) }
    $Minutes = [Math]::Round(((Get-Date) - $StartedAt).TotalMinutes, 2)
    Write-Host "master HEAD: $Head"
    Write-Host "elapsed_minutes: $Minutes"
    Write-Host "[OK] deploy_signals_pipeline completed"
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($ProxyProc -and -not $ProxyProc.HasExited) {
        Write-Step "Stopping Cloud SQL Auth Proxy job"
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($ProxyProc.Id)" |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $ProxyProc.Id -Force -ErrorAction SilentlyContinue
    } elseif ($DryRun) {
        Write-Step "Stopping Cloud SQL Auth Proxy job"
        Write-Host "[DRYRUN] Stop-Process <proxy-process>"
    }
}
