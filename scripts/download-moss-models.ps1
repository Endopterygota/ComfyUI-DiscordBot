param(
    [string]$ComfyRoot = "G:\AI_NEW\comfyui-rocm-091926",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ComfyRoot -PathType Container)) {
    throw "ComfyUI-Ordner nicht gefunden: $ComfyRoot"
}

$Curl = (Get-Command curl.exe -ErrorAction Stop).Source
$BaseUrl = "https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main"
$Downloads = @(
    @{
        RelativePath = "models\diffusion_models\moss_image_sft_int8_convrot.safetensors"
        Url = "$BaseUrl/diffusion_models/moss_image_sft_int8_convrot.safetensors"
    },
    @{
        RelativePath = "models\text_encoders\qwen3.5_9b_w4a8_gptq.safetensors"
        Url = "$BaseUrl/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors"
    },
    @{
        RelativePath = "models\vae\flux2-vae.safetensors"
        Url = "$BaseUrl/vae/flux2-vae.safetensors"
    }
)

foreach ($Download in $Downloads) {
    $Destination = Join-Path $ComfyRoot $Download.RelativePath
    $Partial = "$Destination.part"
    $DestinationDirectory = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null

    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $SizeGiB = (Get-Item -LiteralPath $Destination).Length / 1GB
        Write-Host ("Bereits vorhanden: {0} ({1:N2} GiB)" -f $Download.RelativePath, $SizeGiB) -ForegroundColor Green
        continue
    }

    if (Test-Path -LiteralPath $Partial -PathType Leaf) {
        $PartialGiB = (Get-Item -LiteralPath $Partial).Length / 1GB
        Write-Host ("Setze fort: {0} ab {1:N2} GiB" -f $Download.RelativePath, $PartialGiB) -ForegroundColor Yellow
    }
    else {
        Write-Host "Lade: $($Download.RelativePath)" -ForegroundColor Cyan
    }

    $CurlArguments = @(
        "--fail",
        "--location",
        "--continue-at", "-",
        "--retry", "100",
        "--retry-delay", "10",
        "--retry-all-errors",
        "--connect-timeout", "30",
        "--speed-limit", "1024",
        "--speed-time", "180",
        "--output", $Partial,
        $Download.Url
    )
    if ($Quiet) {
        $CurlArguments = @("--silent", "--show-error") + $CurlArguments
    }
    else {
        $CurlArguments = @("--progress-bar") + $CurlArguments
    }

    & $Curl @CurlArguments

    if ($LASTEXITCODE -ne 0) {
        throw "Download fehlgeschlagen. Die Teildatei bleibt fuer den naechsten Versuch erhalten: $Partial"
    }

    Move-Item -LiteralPath $Partial -Destination $Destination
    $SizeGiB = (Get-Item -LiteralPath $Destination).Length / 1GB
    Write-Host ("Fertig: {0} ({1:N2} GiB)" -f $Download.RelativePath, $SizeGiB) -ForegroundColor Green
}

Write-Host "Alle MOSS-Image-Modelle sind installiert." -ForegroundColor Green
