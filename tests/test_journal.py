import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
spec = importlib.util.spec_from_file_location("journal", SCRIPTS_DIR / "journal.py")
journal = importlib.util.module_from_spec(spec)
sys.modules["journal"] = journal
spec.loader.exec_module(journal)


def test_parse_tasks_mixed_checkboxes():
    text = "- [x] done one\n- [ ] pending one\n- [X] done two (capital X)\nnot a task line\n"
    tasks = journal.parse_tasks(text)
    assert tasks == [
        {"text": "done one", "done": True},
        {"text": "pending one", "done": False},
        {"text": "done two (capital X)", "done": True},
    ]


def test_note_title_skips_blank_lines_and_strips_heading():
    text = "\n\n# 2026-08-18 — Title Here\n\nbody text\n"
    assert journal.note_title(text) == "2026-08-18 — Title Here"


def test_note_title_empty_when_no_content():
    assert journal.note_title("") == ""


def test_build_index_reads_day_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path)
    day = tmp_path / "2026-01-02"
    day.mkdir()
    (day / "tasks.md").write_text("- [x] shipped it\n- [ ] follow up\n")
    (day / "notes.md").write_text("# A quiet Friday\n\nnothing much happened.\n")

    index = journal.build_index()

    assert set(index["days"].keys()) == {"2026-01-02"}
    entry = index["days"]["2026-01-02"]
    assert entry["task_count"] == 2
    assert entry["done_count"] == 1
    assert entry["title"] == "A quiet Friday"
    assert (tmp_path / "index.json").exists()


def test_build_index_ignores_non_date_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path)
    (tmp_path / "not-a-date").mkdir()
    index = journal.build_index()
    assert index["days"] == {}
