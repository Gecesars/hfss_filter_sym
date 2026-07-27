param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
.\.venv\Scripts\python -m hfss_vna_bridge --host $HostName --port $Port

