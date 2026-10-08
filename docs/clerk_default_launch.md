# Default NHM website launch

From the repository root, run `python -m scripts.run_nhm`. Connected Clerk TEST authentication is the default. The launcher reads the ignored root `.env` when present (or accepts `--env-file PATH`); exported environment variables take precedence. It validates the TEST keys, builds the frontend with the **publishable** key only, and starts an isolated workspace. The Clerk secret is passed only to the product API. Missing or invalid keys cause startup to fail; there is no DemoAuth fallback.

The default ports are 8001 (inference), 8002 (product API), and 4173 (website). Use `--inference-port`, `--product-port`, and `--frontend-port` to choose other ports. Open the printed `/sign-in` URL. The backend `/product/v1/system` should report `auth_provider=CLERK` and `demo_mode=false`.

For an intentionally offline run, use `python -m scripts.run_nhm --demo` (equivalent to the existing faculty demo with explicit DemoAuth acknowledgement). That historical faculty launcher is separate from the FL10 Observatory product route. Never put keys in tracked files or paste them into reports.
