from pathlib import Path

import pytest

from coding_agent.demo import FixtureResetError, FixtureResetter, snapshot


def test_reset_is_deterministic_and_preserves_external_files(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "app.py").write_text("initial\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    sentinel = tmp_path / "outside.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    resetter = FixtureResetter(seed, runtime)

    first = resetter.reset("demo")
    (first.workspace / "app.py").write_text("modified\n", encoding="utf-8")
    (first.workspace / "generated.txt").write_text("generated\n", encoding="utf-8")
    second = resetter.reset("demo")

    assert first.checksum == second.checksum
    assert second.files == ("app.py",)
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert snapshot(second.workspace).checksum == second.checksum


def test_reset_rejects_traversal_and_external_destination(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "app.py").write_text("initial", encoding="utf-8")
    resetter = FixtureResetter(seed, tmp_path / "runtime")

    with pytest.raises(FixtureResetError):
        resetter.reset("../outside")

