# Setup

Este guia prepara o ambiente de desenvolvimento e operacao da aplicacao.

## 1. Requisitos

Ferramentas basicas:

- Windows 10/11
- PowerShell
- Git
- `uv`

Hardware/software opcionais:

- Ansys Electronics Desktop para backend `pyaedt`
- Licenca HFSS valida
- VISA runtime para backend `pyvisa`
- VNA conectado por LAN, USB ou GPIB

## 2. Python 3.14

Instale o Python 3.14 gerenciado pelo `uv`:

```powershell
uv python install 3.14
```

Crie o ambiente:

```powershell
uv venv --python 3.14
```

Confirme a versao:

```powershell
.\.venv\Scripts\python --version
```

A saida esperada deve iniciar com `Python 3.14`.

## 3. Dependencias

Modo simulado e desenvolvimento:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Modo completo, incluindo AEDT e VNA:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev,aedt,vna]"
```

Alternativa por script:

```powershell
.\scripts\setup.ps1
.\scripts\setup.ps1 -WithHardware
```

## 4. Executar API

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge --host 127.0.0.1 --port 8765
```

Teste:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

## 5. Variaveis de Ambiente

As variaveis abaixo sao opcionais. Elas documentam valores padrao que podem ser
usados por clientes externos.

```powershell
$env:HFSS_BRIDGE_HOST = "127.0.0.1"
$env:HFSS_BRIDGE_PORT = "8765"
$env:HFSS_BRIDGE_AEDT_PROJECT = "D:\simulation\painel triband.aedt"
$env:HFSS_BRIDGE_AEDT_DESIGN = "HFSSDesign1"
$env:HFSS_BRIDGE_VNA_BACKEND = "simulated"
$env:HFSS_BRIDGE_VNA_RESOURCE = "SIM::VNA"
```

## 6. Validacao

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

Os testes automatizados nao acessam AEDT ou VNA real.

