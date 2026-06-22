"""
Per-session image search and voice message limit tests.
Run: python scripts/test_session_usage_limits.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("IMAGE_SEARCH_LIMIT_PER_SESSION", "3")
os.environ.setdefault("VOICE_MESSAGE_LIMIT_PER_SESSION", "5")


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_image_search_under_limit():
    from app.chatbot.session_usage_limits import (
        check_image_search_allowed,
        consume_image_search,
        reset_session_usage,
    )

    sid = "test_usage_img_under"
    reset_session_usage(sid)

    for i in range(2):
        allowed, current, limit = check_image_search_allowed(sid)
        _assert(allowed, f"attempt {i + 1} should be allowed")
        ok, used, lim = consume_image_search(sid)
        _assert(ok, f"consume {i + 1} should succeed")
        _assert(used == i + 1, f"used={used}")
        _assert(lim == 3, f"limit={lim}")

    allowed, current, _ = check_image_search_allowed(sid)
    _assert(allowed, "third slot should still be available")
    _assert(current == 2, f"current={current}")
    print("PASS image_search_under_limit")


def test_image_search_at_limit_blocks():
    from app.chatbot.session_usage_limits import (
        check_image_search_allowed,
        consume_image_search,
        reset_session_usage,
    )

    sid = "test_usage_img_block"
    reset_session_usage(sid)

    for _ in range(3):
        ok, _, _ = consume_image_search(sid)
        _assert(ok, "consume within limit should succeed")

    allowed, used, limit = check_image_search_allowed(sid)
    _assert(not allowed, "should block at limit")
    _assert(used == 3, f"used={used}")
    _assert(limit == 3, f"limit={limit}")

    ok, used2, limit2 = consume_image_search(sid)
    _assert(not ok, "consume at limit should fail")
    _assert(used2 == 3, f"used2={used2}")
    _assert(limit2 == 3, f"limit2={limit2}")
    print("PASS image_search_at_limit_blocks")


def test_voice_under_limit():
    from app.chatbot.session_usage_limits import (
        check_voice_allowed,
        consume_voice_message,
        reset_session_usage,
    )

    sid = "test_usage_voice_under"
    reset_session_usage(sid)

    for i in range(4):
        allowed, _, _ = check_voice_allowed(sid)
        _assert(allowed, f"voice attempt {i + 1} should be allowed")
        ok, used, limit = consume_voice_message(sid)
        _assert(ok, f"consume {i + 1} should succeed")
        _assert(used == i + 1, f"used={used}")
        _assert(limit == 5, f"limit={limit}")

    allowed, current, _ = check_voice_allowed(sid)
    _assert(allowed, "fifth slot should still be available")
    _assert(current == 4, f"current={current}")
    print("PASS voice_under_limit")


def test_voice_at_limit_blocks():
    from app.chatbot.session_usage_limits import (
        check_voice_allowed,
        consume_voice_message,
        reset_session_usage,
    )

    sid = "test_usage_voice_block"
    reset_session_usage(sid)

    for _ in range(5):
        ok, _, _ = consume_voice_message(sid)
        _assert(ok, "consume within limit should succeed")

    allowed, used, limit = check_voice_allowed(sid)
    _assert(not allowed, "should block at limit")
    _assert(used == 5, f"used={used}")
    _assert(limit == 5, f"limit={limit}")

    ok, used2, _ = consume_voice_message(sid)
    _assert(not ok, "consume at limit should fail")
    _assert(used2 == 5, f"used2={used2}")
    print("PASS voice_at_limit_blocks")


def test_reset_clears_counts():
    from app.chatbot.session_usage_limits import (
        check_image_search_allowed,
        check_voice_allowed,
        consume_image_search,
        consume_voice_message,
        get_session_usage,
        reset_session_usage,
    )

    sid = "test_usage_reset"
    reset_session_usage(sid)
    consume_image_search(sid)
    consume_image_search(sid)
    consume_voice_message(sid)
    consume_voice_message(sid)
    consume_voice_message(sid)

    usage = get_session_usage(sid)
    _assert(usage["image_search_count"] == 2, f"img={usage['image_search_count']}")
    _assert(usage["voice_message_count"] == 3, f"voice={usage['voice_message_count']}")

    reset_session_usage(sid)
    usage = get_session_usage(sid)
    _assert(usage["image_search_count"] == 0, "image count should reset")
    _assert(usage["voice_message_count"] == 0, "voice count should reset")

    img_ok, _, _ = check_image_search_allowed(sid)
    voice_ok, _, _ = check_voice_allowed(sid)
    _assert(img_ok, "image should be allowed after reset")
    _assert(voice_ok, "voice should be allowed after reset")
    print("PASS reset_clears_counts")


def main() -> None:
    test_image_search_under_limit()
    test_image_search_at_limit_blocks()
    test_voice_under_limit()
    test_voice_at_limit_blocks()
    test_reset_clears_counts()
    print("\nAll session usage limit tests passed.")


if __name__ == "__main__":
    main()
