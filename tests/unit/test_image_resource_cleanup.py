import os
import time

from app.services.image_resource_service import cleanup_file, cleanup_stale_files


def test_cleanup_stale_files_removes_old_files_and_preserves_protected(tmp_path):
    old_file = tmp_path / "old.png"
    protected_file = tmp_path / "protected.png"
    fresh_file = tmp_path / "fresh.png"
    for path in (old_file, protected_file, fresh_file):
        path.write_bytes(b"image")

    old_time = time.time() - 3600
    os.utime(old_file, (old_time, old_time))
    os.utime(protected_file, (old_time, old_time))

    assert cleanup_stale_files(
        tmp_path,
        max_age_seconds=60,
        protected_paths={protected_file},
    ) == 1
    assert not old_file.exists()
    assert protected_file.exists()
    assert fresh_file.exists()


def test_cleanup_file_is_idempotent(tmp_path):
    path = tmp_path / "temporary.png"
    path.write_bytes(b"image")

    assert cleanup_file(path) is True
    assert cleanup_file(path) is True
    assert not path.exists()
