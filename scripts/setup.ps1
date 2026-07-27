param(
    [switch]$WithHardware
)

$ErrorActionPreference = "Stop"

uv python install 3.14
uv venv --python 3.14

if ($WithHardware) {
    .\.venv\Scripts\python -m pip install -e ".[dev,aedt,vna]"
} else {
    .\.venv\Scripts\python -m pip install -e ".[dev]"
}

.\.venv\Scripts\python -m pytest

