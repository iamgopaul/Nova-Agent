$env:PATH = "C:\Program Files (x86)\cloudflared;$env:PATH"
Write-Host "Starting Cloudflare Quick Tunnel for http://localhost:8765..." -ForegroundColor Cyan
Write-Host "Keep this window open. Closing it tears down the tunnel." -ForegroundColor Yellow
Write-Host ""
cloudflared tunnel --url http://localhost:8765
