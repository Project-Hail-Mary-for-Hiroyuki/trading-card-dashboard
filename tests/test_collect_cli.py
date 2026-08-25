from __future__ import annotations

import subprocess
import sys

from core.config import load_config


def test_import_collect_no_side_effect():
    """CLIモジュールのimport時にargparseが走らないこと。"""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); import scripts.collect; print('ok')"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout and "usage:" not in proc.stderr


def test_load_config_db_path_is_project_root_relative(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("database:\n  path: data/test_x.db\n")
    cfg = load_config(cfg_path)
    assert cfg.db_path.name == "test_x.db"
    assert str(cfg.db_path).startswith(str(cfg_path.parent.parent)) or cfg.db_path.is_absolute()
