from pathlib import Path
from types import SimpleNamespace

from src.config.enums import LanguageEnum
from src.workers.incremental_sync import IncrementalSyncWorker, FileChange


class _FakeDiff:
    def __init__(self):
        self._map = {
            "A": [SimpleNamespace(b_path="added.py")],
            "M": [SimpleNamespace(b_path="modified.ts")],
            "D": [SimpleNamespace(a_path="deleted.cs")],
            "R": [SimpleNamespace(a_path="old/name.cs", b_path="new/name.cs")],
        }

    def iter_change_type(self, change_type):
        return self._map.get(change_type, [])


class _FakeTree:
    def __init__(self, items):
        self._items = items

    def traverse(self):
        return self._items


class _FakeRepo:
    def __init__(self):
        self._diff = _FakeDiff()

    def tree(self, _to_commit):
        return _FakeTree([
            SimpleNamespace(type="blob", path="src/main.py"),
            SimpleNamespace(type="tree", path="src"),
            SimpleNamespace(type="blob", path="README.md"),
        ])

    def commit(self, _from_commit):
        return SimpleNamespace(diff=lambda _to_commit: self._diff)


def _worker():
    return IncrementalSyncWorker(session=SimpleNamespace(), repo_cache_dir=Path("/tmp"))


def test_detect_language_maps_known_suffixes_and_defaults():
    worker = _worker()

    assert worker._detect_language(Path("a.cs")) == LanguageEnum.CSHARP
    assert worker._detect_language(Path("a.tsx")) == LanguageEnum.TYPESCRIPT
    assert worker._detect_language(Path("a.py")) == LanguageEnum.PYTHON
    assert worker._detect_language(Path("a.vue")) == LanguageEnum.VUE
    assert worker._detect_language(Path("appsettings.json")) == LanguageEnum.CSHARP
    assert worker._detect_language(Path("package.json")) == LanguageEnum.JAVASCRIPT
    assert worker._detect_language(Path("notes.unknown")) == LanguageEnum.UNKNOWN


def test_get_changed_files_initial_sync_marks_all_blobs_added():
    worker = _worker()
    fake_repo = _FakeRepo()

    changes = worker._get_changed_files(fake_repo, from_commit=None, to_commit="abc")

    assert changes == [
        FileChange(path="src/main.py", change_type="A"),
        FileChange(path="README.md", change_type="A"),
    ]


def test_get_changed_files_collects_add_modify_delete_rename_changes():
    worker = _worker()
    fake_repo = _FakeRepo()

    changes = worker._get_changed_files(fake_repo, from_commit="old", to_commit="new")

    assert FileChange(path="added.py", change_type="A") in changes
    assert FileChange(path="modified.ts", change_type="M") in changes
    assert FileChange(path="deleted.cs", change_type="D") in changes
    assert FileChange(path="new/name.cs", change_type="R", old_path="old/name.cs") in changes
    assert len(changes) == 4
