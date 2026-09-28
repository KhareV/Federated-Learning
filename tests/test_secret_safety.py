import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKED = [ROOT / "configs/base.yaml", ROOT / "tests/fixtures/mongodb_observed_v0.json"]


def test_configs_and_fixtures_do_not_contain_mongodb_credentials() -> None:
    credential_uri = re.compile(r"mongodb(?:\+srv)?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE)
    for path in CHECKED:
        assert credential_uri.search(path.read_text(encoding="utf-8")) is None, path

