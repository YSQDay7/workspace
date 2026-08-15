$ports = 8000, 5173
foreach ($port in $ports) {
  $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($connection in $connections) {
    Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Output "Stopped process $($connection.OwningProcess) on port $port"
  }
}
Write-Output "Services stopped."
