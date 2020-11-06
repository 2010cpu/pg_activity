from typing import Optional

from blessed.keyboard import Keystroke

from . import keys
from .types import DurationMode, QueryDisplayMode, QueryMode, SortKey, enum_next


def refresh_time(
    key: Optional[str], value: float, minimum: float = 0.5, maximum: float = 5
) -> float:
    """Return an updated refresh time interval from input key respecting bounds.

    >>> refresh_time("+", 1)
    2
    >>> refresh_time("+", 5)
    5
    >>> refresh_time("+", 5, maximum=10)
    6
    >>> refresh_time("-", 2)
    1
    >>> refresh_time("-", 1)
    0.5
    >>> refresh_time("-", 0.5)
    0.5
    >>> refresh_time("=", 42)
    Traceback (most recent call last):
        ...
    ValueError: =
    """
    if key == keys.REFRESH_TIME_DECREASE:
        return max(value - 1, minimum)
    elif key == keys.REFRESH_TIME_INCREASE:
        return min(int(value + 1), maximum)
    raise ValueError(key)


def duration_mode(key: Keystroke, mode: DurationMode) -> DurationMode:
    """Return the updated duration mode matching input key.

    >>> from blessed.keyboard import Keystroke as k

    >>> duration_mode(k("42"), DurationMode.query)
    <DurationMode.query: 1>
    >>> duration_mode(k("T"), DurationMode.transaction)
    <DurationMode.backend: 3>
    """
    if key == keys.CHANGE_DURATION_MODE:
        return enum_next(mode)
    return mode


def verbose_mode(key: Keystroke, mode: QueryDisplayMode) -> QueryDisplayMode:
    """Return the updated query display mode (aka verbose mode) matching input
    key.

    >>> from blessed.keyboard import Keystroke as k

    >>> verbose_mode(k("42"), QueryDisplayMode.truncate)
    <QueryDisplayMode.truncate: 1>
    >>> verbose_mode(k("v"), QueryDisplayMode.wrap_noindent)
    <QueryDisplayMode.wrap: 3>
    """
    if key == keys.CHANGE_DISPLAY_MODE:
        return enum_next(mode)
    return mode


def query_mode(key: Keystroke) -> Optional[QueryMode]:
    """Return the query mode matching input key or None.

    >>> import curses
    >>> from blessed.keyboard import Keystroke as k

    >>> query_mode(k("42"))
    >>> query_mode(k("1"))
    <QueryMode.activities: 'running queries'>
    >>> query_mode(k(code=curses.KEY_F3))
    <QueryMode.blocking: 'blocking queries'>
    """
    if key.is_sequence and key.code in keys.QUERYMODE_FROM_KEYS:
        key = key.code
    return keys.QUERYMODE_FROM_KEYS.get(key)


def sort_key_for(
    key: Keystroke, query_mode: QueryMode, is_local: bool
) -> Optional[SortKey]:
    """Return the sort key matching input key or None.

    >>> from blessed.keyboard import Keystroke as k
    >>> from pgactivity.types import QueryMode

    >>> sort_key_for(k("1"), QueryMode.activities, True)
    >>> sort_key_for(k("m"), QueryMode.activities, True)
    <SortKey.mem: 2>
    >>> sort_key_for(k("w"), QueryMode.activities, True)
    <SortKey.write: 4>
    >>> sort_key_for(k("t"), QueryMode.activities, True)
    <SortKey.duration: 5>
    >>> sort_key_for(k("m"), QueryMode.waiting, True)
    <SortKey.duration: 5>
    >>> sort_key_for(k("c"), QueryMode.activities, True)
    <SortKey.cpu: 1>
    >>> sort_key_for(k("c"), QueryMode.activities, False)
    <SortKey.duration: 5>
    >>> sort_key_for(k("m"), QueryMode.blocking, False)
    <SortKey.duration: 5>
    """
    if not is_local or query_mode != QueryMode.activities:
        return SortKey.default()
    return {
        keys.SORTBY_CPU: SortKey.cpu,
        keys.SORTBY_MEM: SortKey.mem,
        keys.SORTBY_READ: SortKey.read,
        keys.SORTBY_TIME: SortKey.duration,
        keys.SORTBY_WRITE: SortKey.write,
    }.get(key)
