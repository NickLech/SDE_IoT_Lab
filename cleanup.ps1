# Post-lab cleanup
Set-Location $PSScriptRoot

docker compose --profile debug down --rmi all

Write-Host "Cleanup completed"
