# Installing AgentPack

How to install the `agentpack` command itself. To install a package you *built*
with it, read the generated `dist/INSTALL.md` instead.

**Contents:** [Requirements](#requirements) · [Option 1: pipx](#option-1-pipx-recommended) ·
[Option 2: virtual environment](#option-2-virtual-environment) ·
[Option 3: from source](#option-3-from-source-for-contributors) ·
[Verify](#verify) · [Claude Desktop HTTP bridge](#claude-desktop-http-bridge) ·
[Upgrade](#upgrade) · [Uninstall](#uninstall) · [Troubleshooting](#troubleshooting)

---

## Requirements

- Python **3.11 or newer**
- `git`, if installing from the repository
- When packaging a Claude Desktop HTTP MCPB, either Go **1.25 or newer** or the
  optional Python bridge dependencies

```powershell
py --version
```

```bash
python3 --version
```

AgentPack is not on PyPI yet, so every option below installs from GitHub or from
a local clone.

---

## Option 1: pipx (recommended)

`pipx` installs a CLI into its own isolated environment and puts it on your PATH
permanently — no activation, works from any directory. This is the right choice
if you just want to *use* AgentPack.

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
# open a new terminal so PATH is refreshed
pipx install git+https://github.com/uzigolan/agentpack.git
```

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
# open a new shell so PATH is refreshed
pipx install git+https://github.com/uzigolan/agentpack.git
```

---

## Option 2: virtual environment

Use this if you prefer not to install pipx. The command only exists while the
environment is activated.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install git+https://github.com/uzigolan/agentpack.git
```

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install git+https://github.com/uzigolan/agentpack.git
```

Activation lasts for the current shell only. In a new terminal, activate again
or call the executable by its full path:

```powershell
C:\path\to\.venv\Scripts\agentpack.exe version
```

---

## Option 3: from source (for contributors)

An editable install, so your changes take effect immediately. Clone first, then
set up the environment:

```powershell
git clone https://github.com/uzigolan/agentpack.git
cd agentpack
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

```bash
git clone https://github.com/uzigolan/agentpack.git
cd agentpack
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The `[dev]` extra adds `pytest` and `ruff`. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Verify

```powershell
agentpack version
agentpack list-targets
agentpack doctor
```

Expected: a version number, six target adapters, and an environment summary.

Build the bundled example to confirm end to end:

```powershell
agentpack package -f examples\network-operations\agentpack.yaml
```

That writes `examples/network-operations/dist/`, including `INSTALL.md` and
`packages/`.

### Import a complete portable stdio pack

When a producer exports `pack.json`, `skills/`, `mcps/`, and a self-contained
`runtime/`, import the whole directory. This keeps the skills and runtime
together and replaces `${packageRoot}` with each target's installed plugin or
bundle root during packaging.

```powershell
agentpack init -n rad-agent-stdio --version 0.25.1
agentpack pack import "C:\path\to\rad-mcp-server\dist\pack_stdio" -n rad-agent-stdio
agentpack validate -n rad-agent-stdio
agentpack package -n rad-agent-stdio
```

Use `--overwrite` on the import command when intentionally refreshing an
existing imported pack. The recipient does not need Python, Go, or the producer
checkout when the imported runtime is already a self-contained executable.

---

## Claude Desktop HTTP bridge

AgentPack embeds a Windows HTTP bridge in each generated HTTP MCPB. On first
extension launch it installs under `%LOCALAPPDATA%\AgentPack\bridge` and then
connects using the endpoint and secret headers entered in Claude Desktop. No
Node.js, Python, or producer checkout is required by the installing user.

The package builder supports two paths. AgentPack prefers Go 1.25 or newer when
`go` is on `PATH`. On Windows, download it from
[https://go.dev/dl/](https://go.dev/dl/), run the
appropriate MSI, then close and reopen PowerShell:

```powershell
go version
```

If `winget` is available, it can install Go instead:

```powershell
winget install --exact --id GoLang.Go
```

If PowerShell reports that `winget` is not recognized, use the MSI method
above; installing `winget` is not required.

Alternatively, install the Python bridge dependencies in the same environment
as AgentPack:

```powershell
# Editable source checkout
python -m pip install -e ".[bridge-python]"

# Already installed in a virtual environment
python -m pip install "mcp>=1.27,<2" "pyinstaller>=6.15"
```

For a pipx installation, inject the dependencies into AgentPack's environment:

```powershell
pipx inject agentpack "mcp>=1.27,<2" "pyinstaller>=6.15"
```

When Go is unavailable, AgentPack automatically uses PyInstaller to create a
self-contained Windows executable. Python and PyInstaller are needed only on
the build machine; the generated MCPB does not require Python on the recipient's
machine. The first build is slower, and later builds reuse the cached bridge.

Go is not required when Claude Desktop is not one of the selected targets. To
package only Codex, for example:

```powershell
agentpack package -n NAME -t codex
```

Repeat `-t` to build several selected targets.

---

## Upgrade

```powershell
pipx upgrade agentpack                                     # option 1
python -m pip install --upgrade git+https://github.com/uzigolan/agentpack.git   # option 2
git pull                                                   # option 3 (editable: nothing to reinstall)
```

---

## Uninstall

```powershell
pipx uninstall agentpack        # option 1
python -m pip uninstall agentpack   # options 2 and 3
```

For a venv install you can simply delete the `.venv` directory.

AgentPack writes nothing outside the project you point it at, so there is no
global state to clean up.

---

## Troubleshooting

### `agentpack : The term 'agentpack' is not recognized...`

The environment is not active. Either activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

or call the executable directly:

```powershell
.\.venv\Scripts\agentpack.exe version
```

With pipx, open a **new** terminal after `pipx ensurepath` so PATH is picked up.

### `Activate.ps1 cannot be loaded because running scripts is disabled`

PowerShell execution policy. Allow signed local scripts for your user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### `Python was not found` on Windows

Use the launcher, `py`, instead of `python`. If `py` is missing, install Python
from python.org and tick *Add python.exe to PATH*.

### `ERROR AP1001: no agentpack.yaml found at or above ...`

You are not in a project directory. Either `cd` into the repository that holds
your skills and MCP definitions, or point at the manifest explicitly:

```powershell
agentpack validate -f path\to\agentpack.yaml
```

### `ERROR AP3001 [claude-desktop]: ... requires Go or ... Python bridge dependencies`

AgentPack could not find either supported bridge builder. Install the Python
fallback in the active AgentPack environment and run the package command again:

```powershell
python -m pip install "mcp>=1.27,<2" "pyinstaller>=6.15"
agentpack package -n NAME
```

If AgentPack was installed with pipx, use `pipx inject` instead:

```powershell
pipx inject agentpack "mcp>=1.27,<2" "pyinstaller>=6.15"
agentpack package -n NAME
```

To use Go instead, install Go 1.25 or newer from
[https://go.dev/dl/](https://go.dev/dl/), reopen PowerShell, and verify it with
`go version`.

If you do not need a Claude Desktop package, select only the required targets;
for example, `agentpack package -n NAME -t codex`.

### `agentpack init` created files I did not want

`init` scaffolds an example package (`agentpack.yaml`, `skills/example/`,
`mcp/example.yaml`) in the **current directory**. Do not run it inside the
AgentPack repository itself. Delete those three paths if you did.
