"""Re-uploading a file replaces its chunks instead of duplicating them (FN-02)."""
import uuid

from app.rag.collections import count_by_source_file, count_for, fetch_all_for
from app.rag.ingestion import ingest_single_file_for_user


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_reuploading_a_file_does_not_duplicate_chunks(weaviate_env, tmp_path):
    user = uuid.uuid4()
    f = _write(tmp_path / "notes.txt", "alpha beta gamma")
    first = ingest_single_file_for_user(user, f)
    second = ingest_single_file_for_user(user, f)
    assert first["replaced"] == 0
    assert second["replaced"] == first["chunks"]
    assert count_by_source_file(user, "notes.txt") == first["chunks"]
    assert count_for(user) == first["chunks"]


def test_reupload_with_new_content_replaces_the_old_text(weaviate_env, tmp_path):
    user = uuid.uuid4()
    f = _write(tmp_path / "notes.txt", "the old version")
    ingest_single_file_for_user(user, f)
    _write(f, "the new version")
    ingest_single_file_for_user(user, f)
    texts = [d.page_content for d in fetch_all_for(user)]
    assert texts == ["the new version"]


def test_other_files_and_other_users_are_untouched(weaviate_env, tmp_path):
    alice, bob = uuid.uuid4(), uuid.uuid4()
    a1 = _write(tmp_path / "a.txt", "alice file a")
    a2 = _write(tmp_path / "b.txt", "alice file b")
    ingest_single_file_for_user(alice, a1)
    ingest_single_file_for_user(alice, a2)
    ingest_single_file_for_user(bob, a1)  # same filename, different user
    ingest_single_file_for_user(alice, a1)  # re-upload
    assert count_by_source_file(alice, "a.txt") == 1
    assert count_by_source_file(alice, "b.txt") == 1
    assert count_by_source_file(bob, "a.txt") == 1


def test_failed_parse_keeps_the_existing_chunks(weaviate_env, tmp_path):
    user = uuid.uuid4()
    f = _write(tmp_path / "notes.txt", "keep me")
    ingest_single_file_for_user(user, f)
    f.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")  # TextLoader(encoding=utf-8) fails
    try:
        ingest_single_file_for_user(user, f)
    except Exception:
        pass
    else:
        raise AssertionError("expected the bad file to fail")
    assert [d.page_content for d in fetch_all_for(user)] == ["keep me"]


def test_similar_file_names_are_not_confused(weaviate_env, tmp_path):
    """Weaviate word-tokenizes source_file ('a.txt' also matches 'b.txt' once the
    stop-word 'a' is dropped; 'report.pdf' matches 'report-final.pdf'). Only the
    exact file name may be replaced or deleted."""
    from app.rag.collections import delete_by_source_file

    user = uuid.uuid4()
    for name in ("a.txt", "b.txt", "report.txt", "report-final.txt"):
        ingest_single_file_for_user(user, _write(tmp_path / name, f"content of {name}"))
    assert count_by_source_file(user, "a.txt") == 1
    assert count_by_source_file(user, "report.txt") == 1
    assert delete_by_source_file(user, "report.txt") == 1
    assert count_by_source_file(user, "report-final.txt") == 1
    assert count_by_source_file(user, "b.txt") == 1
    assert delete_by_source_file(user, "a.txt") == 1
    assert count_for(user) == 2  # b.txt and report-final.txt remain
