from pathlib import Path

from dynaconf import Dynaconf

setting_dir = Path(__file__).resolve().parents[1]
toml_files = list(setting_dir.rglob("*.toml"))
global_settings = Dynaconf(
    envvar_prefix=False,
    merge_enabled=True,
    settings_files=toml_files,
)


def get_settings():
    return global_settings
