"""Short status text: one emoji per meaning, and a line that fits an iPhone SE."""

from mypystub import status_text as s

# Labels don't wrap on iOS; about this many characters fit an iPhone SE
SE_WIDTH = 40


def columns(text: str) -> int:
    """A rough width: emoji are two columns wide, variation selectors none."""
    return sum(0 if c == "\ufe0f" else 2 if ord(c) > 0x2000 else 1 for c in text)


def test_results_say_what_and_how_in_a_few_words() -> None:
    assert s.packages_result(0) == "📦 ✅ up to date"
    assert s.packages_result(3) == "📦 ⚠️ 3 to update"
    assert s.app_result(0) == "📱 ✅ up to date"
    assert s.app_result(4) == "📱 ⚠️ 4 behind"
    assert s.app_result(0, newer_build=True) == "📱 ⚠️ new build"
    assert s.could_not_check(s.PACKAGES) == "📦 ❌ no answer"
    assert s.checking("rich") == "🔍 rich"


def test_the_worst_after_a_check_fits_an_iphone_se() -> None:
    worst = s.join(s.packages_result(12), s.app_result(12))
    assert columns(worst) <= SE_WIDTH, worst
    both_failed = s.join(s.could_not_check(s.PACKAGES), s.could_not_check(s.APP))
    assert columns(both_failed) <= SE_WIDTH, both_failed


def test_empty_results_leave_no_stray_separator() -> None:
    assert s.join("", s.app_result(0), "") == "📱 ✅ up to date"
    assert s.join() == ""


def test_each_emoji_means_one_thing() -> None:
    marks = [s.PACKAGES, s.APP, s.CHECKING, s.OK, s.WARN, s.FAILED, s.DELETED]
    assert len(set(marks)) == len(marks)
