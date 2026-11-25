# Post-lab cleanup
Set-Location $PSScriptRoot

docker compose --profile debug down --rmi all --volumes

Write-Host "Cleanup completed"
