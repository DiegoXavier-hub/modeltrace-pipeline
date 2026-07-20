# Espera o cloudflared escrever a URL publica no log e imprime so a URL
# (ou nada, se estourar o tempo). Chamado por publicar_na_web.bat.
param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [int]$TimeoutSeconds = 25
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $LogPath) {
        $match = Select-String -LiteralPath $LogPath -Pattern 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' |
            Select-Object -First 1
        if ($match) {
            Write-Output $match.Matches[0].Value
            exit 0
        }
    }
    Start-Sleep -Seconds 1
}
exit 1
