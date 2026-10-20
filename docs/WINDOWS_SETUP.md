# Running NHM on a Windows computer

Recommended: **WSL2 (Ubuntu) + the GitHub repository + one zip for the files Git does not carry.** The project was built and verified on macOS; WSL2 gives it a Linux environment close to that, avoids Windows-only process and path problems, and the Windows browser reaches `http://127.0.0.1:4173` inside WSL2 as usual. A native-Windows install is possible but untested (the launcher starts `npm` as a plain executable, which Windows only finds as `npm.cmd`).

## 1. What travels how

| What | How | Size |
|---|---|---|
| Source, docs, tests, evidence reports, checkpoints (`checkpoints/*.pt` are tracked) | `git clone` from GitHub | ~600 MB |
| `.env` (Clerk and MongoDB secrets) | never GitHub: password manager, or a direct file transfer you delete afterwards | 1 KB |
| Datasets the site reads at run time: `data/raw/nstdb`, `data/processed/mitdb/1.0.0/PREPROC_V1` | zip on the Mac, send with any file-share (Blip, USB, OneDrive) | ~340 MB |
| Your stored candidates `data/studio_candidates` and, if you want your runs and History, `~/.nhm/demo_workspace` | optional zip | few MB |
| Large raw datasets (`data/raw/ptbxl` 3.2 GB, `mitbih_noise_stress` 2.1 GB, `incartdb`, `bidmc`) | only to re-run experiments; public downloads, checksums are in `data/raw/*/SHA256SUMS.txt` | 6+ GB |

On the Mac, from the repository root:

```bash
zip -r nhm_runtime_data.zip data/raw/nstdb data/processed/mitdb data/studio_candidates
```

## 2. One-time setup on Windows

1. Install WSL2 (`wsl --install -d Ubuntu` in an administrator PowerShell) and open Ubuntu.
2. In Ubuntu (clone **inside** the Linux filesystem, e.g. `~/projects`, not under `/mnt/c`):
   ```bash
   sudo apt update && sudo apt install -y git python3.11 python3.11-venv build-essential unzip
   curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
   git clone https://github.com/KhareV/Federated-Learning.git nhm && cd nhm
   ```
   If `python3.11` is not available on your Ubuntu, use the deadsnakes PPA or `pyenv`; the project requires Python 3.11 exactly (`>=3.11,<3.12`).
3. Python environment:
   ```bash
   python3.11 -m venv .venv-studio311 && source .venv-studio311/bin/activate
   pip install -r requirements-dev.lock -r requirements-capstone-auth.lock -r requirements-hardware.txt
   pip install --no-deps -e .
   ```
4. Frontend:
   ```bash
   (cd frontend && npm ci) && (cd frontend/clerk-sdk && npm ci)
   ```
5. Put the files Git does not carry in place: unzip `nhm_runtime_data.zip` in the repository root, and copy `.env` to the repository root.
6. Clerk and Atlas: the Clerk keys in `.env` work from any machine. If you use the MongoDB hardware source, add the Windows computer's public IP to the Atlas Network Access list.

## 3. Run

```bash
source .venv-studio311/bin/activate
PYTHONPATH=src:. python -m scripts.demo_preflight     # build, ports, model checksum, workspace
PYTHONUNBUFFERED=1 PYTHONPATH=src:. python -m scripts.run_nhm --durable
```
Open `http://127.0.0.1:4173/sign-in` in the Windows browser.

## 4. Things to expect

* **Line endings:** the repository contains `.gitattributes` (`* -text`) so Git never converts files. The governance locks pin SHA-256 digests of source files; a checkout with converted line endings (Git for Windows' default `core.autocrlf=true`) would fail the launcher's integrity check with `BOUND_FILE_DRIFT`. If you ever clone with native Windows Git instead, run `git config --global core.autocrlf false` **before** cloning.
* **Bit-exact reproducibility:** frozen state digests and the 3-round parity checks were verified on macOS (Apple Silicon). A different CPU or numerical library can change the last floating-point bits, so a few digest-equality tests may fail on another machine even though the site and its metrics behave the same. Treat those as platform notes, not product faults.
* **Browser gates** (`scripts/verify_hardware_connected_browser.py`) drive Chrome through its debug port and were only run on macOS.
* **Never** rebuild the frontend while the site is running; stop it first.

## 5. Docker instead?

Possible, not needed for a demonstration: the stack needs Python 3.11, Node, the secrets file and about 340 MB of data mounted in, and the Docker layer adds a second thing to debug without removing any of the above. WSL2 gives the same Linux behaviour with less ceremony. If you want a container anyway, say so and a Dockerfile and compose file can be added.
