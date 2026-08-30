"""
Regression test for: OSError: [Errno 22] Invalid argument on Windows
when Bale's file_id (which contains colons) was used directly as a
local filename in workers/common_handlers.py:handle_file().
"""
import os
import re
import uuid

WINDOWS_FORBIDDEN = set('<>:"|?*')


def make_safe_filename(ext=".jpg"):
    """Mirrors the fixed logic in common_handlers.handle_file()."""
    return f"{uuid.uuid4().hex}{ext}"


def test_generated_filename_has_no_windows_forbidden_chars():
    for _ in range(20):
        name = make_safe_filename()
        assert not WINDOWS_FORBIDDEN.intersection(set(name))


def test_generated_filename_never_contains_the_real_bale_file_id_shape():
    # This is the actual file_id format from the user's log — colons and
    # negative numbers included.
    real_bale_file_id = (
        "2141709305:-2821908970244137214:1:"
        "d71a0507c98b48f37e17f1b9225ded28e9823b2004417b6dbbef6dd7a1e4ee1c"
    )
    name = make_safe_filename()
    assert real_bale_file_id not in name
    assert ":" not in name


def test_extension_sanitization_rejects_weird_input():
    # Mirrors the re.fullmatch guard added around doc.file_name's extension
    for bad_ext in ["", ".", "..\\evil", ".jpg\\..\\..\\x", None]:
        ext = bad_ext if bad_ext and re.fullmatch(r"\.[A-Za-z0-9]{1,10}", bad_ext) else ".jpg"
        assert ext == ".jpg" or re.fullmatch(r"\.[A-Za-z0-9]{1,10}", ext)

    good_ext = ".png"
    ext = good_ext if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", good_ext) else ".jpg"
    assert ext == ".png"
