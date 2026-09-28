# CI Foundation

The specified remote is GitHub, so `.github/workflows/t001.yml` provides the active Phase-01 CI
definition. It uses Python 3.11, installs the exact development lock, installs the local package
without resolving additional dependencies, and runs `make phase1`. No live database or secret is
required.

