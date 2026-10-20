# Running NHM on a Windows computer

## Fastest path: Docker Desktop (one command)

Verified on a Mac with an equivalent engine (Colima): the image builds, the inference, product and frontend services start, and FL training and evaluation tests pass inside the container. Not yet run on Windows itself.

1. Install **Docker Desktop** (WSL2 backend) and git. Clone **inside WSL2** if you can (`wsl`, then `cd ~`), because bind mounts from the Linux filesystem are much faster than from `C:\`:
   ```bash
   git clone https://github.com/KhareV/Federated-Learning.git nhm && cd nhm
   ```
2. Put three things in the repository root (none of them is in Git):
   * `.env` (Clerk and MongoDB secrets; send it privately, never through GitHub),
   * `nhm_runtime_data.zip` unzipped there (`unzip nhm_runtime_data.zip` gives `data/raw/nstdb`, `data/processed/mitdb`, `data/studio_candidates`),
   * optional `nhm_workspace.zip` unzipped there (gives `.nhm/demo_workspace`: your FL runs, History, monitoring sessions and replays; they show up under the same Clerk account).
3. Start it:
   ```bash
   docker compose up --build
   ```
   The first start builds the image (about 10 minutes), installs the frontend packages and builds the frontend (about 5 minutes more). Later starts take about a minute. Open `http://127.0.0.1:4173/sign-in`. Stop with `Ctrl+C`, or `docker compose down` when it runs in the background (`docker compose up -d`).

How it is put together: `Dockerfile` carries Python 3.11, Node 22 and the pinned dependencies (CPU torch); `compose.yaml` mounts the clone at `/app`, keeps the Linux `node_modules` in named volumes, keeps the workspace in `./.nhm` (a plain folder, git-ignored) and publishes only port 4173 (the browser reaches the product API through the frontend's proxy).

**Portable numerics (important):** the frozen inference start-up check compares the released model's output on a pinned float32 test vector with a tolerance of 1e-7. Another CPU or BLAS build cannot match that: on the container's CPU the logits differ by 4.9e-7 absolute (agreement to about six digits), so the inference service refused to start. The container therefore sets `NHM_PORTABLE_NUMERICS=1`, which loads `docker/sitecustomize.py` and widens `numpy.allclose` tolerances tighter than 1e-4 to 1e-4. A wrong or corrupted model differs by orders of magnitude more, so the check still catches real faults, and digest and hash checks are untouched. No frozen file is modified. The same applies to any other machine you run on.

## Alternative: WSL2 without Docker

**WSL2 (Ubuntu) + the GitHub repository + one zip for the files Git does not carry.** The project was built and verified on macOS; WSL2 gives it a Linux environment close to that, avoids Windows-only process and path problems, and the Windows browser reaches `http://127.0.0.1:4173` inside WSL2 as usual. A native-Windows install is possible but untested (the launcher starts `npm` as a plain executable, which Windows only finds as `npm.cmd`).

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

## 5. Without Docker on another CPU

The portable-numerics note above applies here too: the inference service will refuse to start on a CPU whose float32 results differ from the recording machine's. Set `NHM_PORTABLE_NUMERICS=1` and put `docker/sitecustomize.py` somewhere on the Python path (for example copy it into the venv's `site-packages/sitecustomize.py`).
