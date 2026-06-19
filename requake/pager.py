# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Interactive table pager using curses.

Adapted from SeisCat's interactive pager with the goal of eventual
extraction as a stand-alone library.  Supports two data-source
backends:

* ``ListDataSource`` – in-memory list of rows (fast, for small
  datasets)
* ``DatabaseDataSource`` – SQLite-backed paginated queries (for
  datasets too large to fit in memory)

:copyright:
    2022-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import curses
import threading
import time
from contextlib import suppress


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

class PagerException(Exception):
    """Exception raised when the pager fails."""


DEFAULT_MAX_COLUMN_WIDTH = 40
CLIPBOARD_FAIL_MESSAGE = (
    'Clipboard copy failed.\nInstall wl-copy, xclip, or xsel.'
)


def _do_copy(row, copy_fn=None):
    """Return the text to copy from *row*.

    When *copy_fn* is given it is called with the row; otherwise
    the first column is used.
    """
    return copy_fn(row) if copy_fn is not None else str(row[0])


# ---------------------------------------------------------------------------
#  Data-source protocol / implementations
# ---------------------------------------------------------------------------

class DataSource:
    """Abstract interface for pager data backends."""

    def __init__(self):
        """Initialize the data source."""

    @property
    def fields(self):
        """Column names."""
        raise NotImplementedError

    @property
    def total_count(self):
        """Total number of rows."""
        raise NotImplementedError

    def get_rows(self, offset, limit, sort_col, sort_asc):
        """Return *limit* rows starting at *offset*.

        :param offset: zero-based row offset
        :param limit: max rows to return
        :param sort_col: column index to sort by, or ``None`` for
            default ordering
        :param sort_asc: ``True`` for ascending, ``False`` for
            descending
        """
        raise NotImplementedError

    def get_row(self, index):
        """Return a single row at absolute position *index*."""
        raise NotImplementedError


class ListDataSource(DataSource):
    """In-memory data source wrapping a list of rows."""

    def __init__(self, fields, rows):
        """Initialize with *fields* (column names) and *rows*."""
        self._fields = list(fields)
        self._rows = list(rows)

    @property
    def fields(self):
        """Column names."""
        return self._fields

    @property
    def total_count(self):
        """Total number of rows."""
        return len(self._rows)

    def get_rows(self, offset, limit, sort_col, sort_asc):
        """Return *limit* rows starting at *offset*."""
        if sort_col is not None:
            self._sort_by_column(sort_col, sort_asc)
        end = offset + limit if limit is not None else len(self._rows)
        return [list(r) for r in self._rows[offset:end]]

    def get_row(self, index):
        """Return a single row at absolute position *index*."""
        return list(self._rows[index])

    def _sort_by_column(self, col_index, asc):
        """Sort internal row list in place."""

        def _sort_key(row):
            val = row[col_index] if col_index < len(row) else None
            if val is None:
                return (1, '')
            try:
                return (0, val)
            except TypeError:
                return (0, str(val))

        self._rows.sort(key=_sort_key, reverse=not asc)


class DatabaseDataSource(DataSource):
    """SQLite-backed data source for huge datasets.

    Maintains an internal page cache (default 5× the requested page
    size) so that sequential scrolling and nearby navigation do not
    hit the database on every keypress.

    Parameters
    ----------
    fields : list[str]
        Column names.
    query_fn : callable
        ``query_fn(sort_col, sort_asc, offset, limit) -> list[list]``
        Must return a list of row-data lists.
    count_fn : callable
        ``count_fn() -> int``
        Must return the total row count.
    cache_multiplier : int
        Fetch this many times the requested page size when filling
        the cache (default 5).
    """

    def __init__(self, fields, query_fn, count_fn, cache_multiplier=5):
        """Initialize with *fields*, *query_fn* and *count_fn*."""
        self._fields = list(fields)
        self._query_fn = query_fn
        self._count_fn = count_fn
        self._total_count = None
        self._cache_multiplier = cache_multiplier
        # Cache state
        self._cache_offset = -1
        self._cache_rows = []
        self._cached_sort_col = None
        self._cached_sort_asc = True

    @property
    def fields(self):
        """Column names."""
        return self._fields

    @property
    def total_count(self):
        """Total number of rows (lazy-loaded via *count_fn*)."""
        if self._total_count is None:
            self._total_count = self._count_fn()
        return self._total_count

    def get_rows(self, offset, limit, sort_col, sort_asc):
        """Return *limit* rows starting at *offset* via *query_fn*.

        Uses a sliding-window cache: fetches *cache_multiplier* ×
        *limit* rows at once and serves subsequent nearby requests
        from memory.
        """
        # Invalidate cache when sort parameters change.
        if (sort_col != self._cached_sort_col
                or sort_asc != self._cached_sort_asc):
            self._cache_offset = -1
            self._cache_rows = []
            self._cached_sort_col = sort_col
            self._cached_sort_asc = sort_asc

        # Serve from cache when the requested window fits.
        if self._cache_offset >= 0 and self._cache_rows:
            cache_end = self._cache_offset + len(self._cache_rows)
            if self._cache_offset <= offset and offset + limit <= cache_end:
                start = offset - self._cache_offset
                return [list(r) for r in self._cache_rows[start:start + limit]]

        # Cache miss — fetch a larger window.
        cache_size = max(limit * self._cache_multiplier, limit + 1)
        self._cache_rows = self._query_fn(
            sort_col, sort_asc, offset, cache_size
        )
        self._cache_offset = offset
        return [list(r) for r in self._cache_rows[:limit]]

    def get_row(self, index):
        """Return a single row at absolute position *index*."""
        # Try cache first.
        if self._cache_offset >= 0 and self._cache_rows:
            cache_end = self._cache_offset + len(self._cache_rows)
            if self._cache_offset <= index < cache_end:
                return list(self._cache_rows[index - self._cache_offset])
        # Cache a window around the requested index.
        window = max(10, self._cache_multiplier * 2)
        half = window // 2
        fetch_offset = max(0, index - half)
        rows = self._query_fn(
            self._cached_sort_col, self._cached_sort_asc,
            fetch_offset, window,
        )
        self._cache_rows = rows
        self._cache_offset = fetch_offset
        rel = index - fetch_offset
        return list(rows[rel]) if 0 <= rel < len(rows) else []


# ---------------------------------------------------------------------------
#  Clipboard helpers (unchanged from SeisCat)
# ---------------------------------------------------------------------------


def _copy_with_osc52(text):
    """Try terminal clipboard copy via OSC52 escape sequence."""
    # pylint: disable=import-outside-toplevel
    import base64
    import os
    import sys

    if not sys.stdout.isatty():
        return False

    term = os.environ.get('TERM', '')
    if term == 'dumb':
        return False

    encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
    sequence = f'\033]52;c;{encoded}\a'

    if 'TMUX' in os.environ:
        sequence = f'\033Ptmux;\033{sequence}\033\\'
    elif term.startswith('screen'):
        sequence = f'\033P{sequence}\033\\'

    try:
        with open('/dev/tty', 'wb') as tty:
            tty.write(sequence.encode('ascii'))
            tty.flush()
        return True
    except OSError:
        return False


def _copy_with_iterm2(text):
    """Try iTerm2 clipboard copy via OSC 1337 escape sequence."""
    # pylint: disable=import-outside-toplevel
    import base64
    import os
    import sys

    if os.environ.get('TERM_PROGRAM') != 'iTerm.app':
        return False
    if not sys.stdout.isatty():
        return False

    term = os.environ.get('TERM', '')
    if term == 'dumb':
        return False

    encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
    sequence = f'\033]1337;Copy=:{encoded}\a'

    if 'TMUX' in os.environ:
        sequence = f'\033Ptmux;\033{sequence}\033\\'
    elif term.startswith('screen'):
        sequence = f'\033P{sequence}\033\\'

    try:
        with open('/dev/tty', 'wb') as tty:
            tty.write(sequence.encode('ascii'))
            tty.flush()
        return True
    except OSError:
        return False


def _copy_to_clipboard(text):
    """
    Copy text to system clipboard (cross-platform).

    :param text: text to copy to clipboard
    :return: True if successful, False otherwise
    """
    # pylint: disable=import-outside-toplevel
    import platform
    import subprocess

    def _is_wsl():
        try:
            with open('/proc/version', 'r', encoding='utf-8') as fp:
                return 'microsoft' in fp.read().lower()
        except OSError:
            return False

    system = platform.system()
    utf8_text = text.encode('utf-8')
    utf16_text = text.encode('utf-16le')
    commands = []

    if system == 'Darwin':
        commands = [(['pbcopy'], utf8_text)]
    elif system == 'Windows':
        commands = [(['clip'], utf16_text)]
    else:
        commands = [
            (['wl-copy'], utf8_text),
            (['xclip', '-selection', 'clipboard'], utf8_text),
            (['xsel', '--clipboard', '--input'], utf8_text),
        ]
        if _is_wsl():
            commands.append((['clip.exe'], utf16_text))

    for cmd, payload in commands:
        try:
            subprocess.run(
                cmd,
                input=payload,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, OSError):
            continue

    return True if _copy_with_iterm2(text) else _copy_with_osc52(text)


# ---------------------------------------------------------------------------
#  Formatting helpers
# ---------------------------------------------------------------------------


def _truncate_for_column(text, max_col_width):
    """Truncate text to a fixed column width using an ellipsis."""
    if max_col_width is None or max_col_width <= 0:
        return text
    if len(text) <= max_col_width:
        return text
    if max_col_width <= 3:
        return '.' * max_col_width
    return f'{text[:max_col_width - 3]}...'


def _format_rows(fields, rows, max_col_width=DEFAULT_MAX_COLUMN_WIDTH):
    """
    Format raw data into aligned string rows.

    :param fields: list of column names
    :param rows: list of row data (each row is a list/tuple)
    :return: tuple of (header_string, body_rows_list,
        max_detail_line_len)
    """
    max_len = [len(_truncate_for_column(f, max_col_width)) for f in fields]
    max_detail_len = [len(f) + 2 for f in fields]
    for row in rows:
        for i, val in enumerate(row):
            if i < len(max_len):
                table_val = 'None' if val is None else str(val)
                table_val = _truncate_for_column(table_val, max_col_width)
                detail_val = '' if val is None else str(val)
                max_len[i] = max(max_len[i], len(table_val))
                max_detail_len[i] = max(
                    max_detail_len[i], len(fields[i]) + 2 + len(detail_val)
                )
    header = '  '.join(
        f'{_truncate_for_column(f, max_col_width):{max_len[i]}}'
        for i, f in enumerate(fields)
    )
    body_rows = []
    for row in rows:
        formatted_vals = []
        for i, val in enumerate(row):
            if i >= len(max_len):
                break
            table_val = 'None' if val is None else str(val)
            table_val = _truncate_for_column(table_val, max_col_width)
            formatted_vals.append(f'{table_val:{max_len[i]}}')
        body_rows.append('  '.join(formatted_vals))
    max_detail_line_len = max(max_detail_len, default=0)
    return header, body_rows, max_detail_line_len


def _build_detail_lines(fields, row):
    """Build 'field: value' lines for a single row."""
    lines = []
    for i, field in enumerate(fields):
        val = row[i] if i < len(row) else ''
        val_str = '' if val is None else str(val)
        lines.append(f'{field}: {val_str}')
    return lines


# ---------------------------------------------------------------------------
#  Popup rendering helpers
# ---------------------------------------------------------------------------


def _flush_pending_input():
    """Clear queued keypresses to prevent lag after expensive operations."""
    with suppress(curses.error, AttributeError):
        curses.flushinp()


def _display_busy_popup(stdscr, message='Working... please wait',
                        hint=None, width=None):
    """Display a transient centered popup while a long task is running.

    An optional *hint* is shown on a second line below the message.
    When *width* is given it overrides the auto-computed popup width.
    """
    hint = hint or ''
    with suppress(curses.error):
        max_y, max_x = stdscr.getmaxyx()
        if width is None:
            max_line_len = max(len(message), len(hint))
            popup_width = min(max_line_len + 6, max_x - 4)
        else:
            popup_width = width
        popup_height = 4 if hint else 3
        # When a fixed width is given, keep height stable too: always
        # use the taller (4-line) layout so the popup does not jump.
        if width is not None and popup_height == 3:
            popup_height = 4
        popup_y = (max_y - popup_height) // 2
        popup_x = (max_x - popup_width) // 2
        top_border = f'╔{"═" * (popup_width - 2)}╗'
        content = _format_centered_popup_line(popup_width, message)
        bottom_border = f'╚{"═" * (popup_width - 2)}╝'
        stdscr.addstr(popup_y, popup_x, top_border, curses.A_BOLD)
        stdscr.addstr(popup_y + 1, popup_x, content, curses.A_BOLD)
        if hint:
            hint_line = _format_centered_popup_line(popup_width, hint)
            stdscr.addstr(
                popup_y + 2, popup_x, hint_line, curses.A_BOLD
            )
        elif popup_height == 4:
            # Clear the hint row when the layout is stable (4 lines)
            # but no hint is shown, to avoid leftover text.
            blank = ' ' * popup_width
            stdscr.addstr(popup_y + 2, popup_x, blank)
        stdscr.addstr(
            popup_y + popup_height - 1, popup_x, bottom_border,
            curses.A_BOLD
        )
        stdscr.refresh()


def _run_with_busy_popup(stdscr, message, operation):
    """Show a busy popup while running *operation* in a background thread.

    ``Ctrl+C`` must be pressed twice within 2 seconds to abort;
    ``q`` or ``Esc`` abort immediately.
    """
    error = [None]
    done = threading.Event()
    abort_pending = [False]
    abort_since = [0.0]

    def _target():
        try:
            operation()
        except Exception as exc:  # pylint: disable=broad-except
            error[0] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    hint_text = 'Ctrl+C to abort'
    abort_msg = (
        'Ctrl+C pressed. Press Ctrl+C again within 2s to abort.'
    )
    max_y, max_x = stdscr.getmaxyx()
    stable_width = min(
        max(len(message), len(hint_text), len(abort_msg)) + 6,
        max_x - 4,
    )

    with suppress(curses.error):
        stdscr.nodelay(True)
    try:
        while not done.is_set():
            # Revert abort prompt after 2-second timeout.
            if abort_pending[0] and time.monotonic() - abort_since[0] > 2.0:
                abort_pending[0] = False

            if abort_pending[0]:
                _display_busy_popup(
                    stdscr, abort_msg, width=stable_width
                )
            else:
                _display_busy_popup(
                    stdscr, message, hint=hint_text,
                    width=stable_width,
                )
            try:
                key = stdscr.getch()
            except curses.error:
                continue
            if key in (ord('q'), 27):  # q, Esc
                raise KeyboardInterrupt
            if key == 3:  # Ctrl+C
                if abort_pending[0]:
                    raise KeyboardInterrupt
                abort_pending[0] = True
                abort_since[0] = time.monotonic()
            else:
                abort_pending[0] = False
    finally:
        with suppress(curses.error):
            stdscr.nodelay(False)

    if error[0] is not None:
        raise error[0]


def _format_centered_popup_line(popup_width, text):
    """Return a popup line with text centered between vertical borders."""
    message_padding = popup_width - 2 - len(text)
    message_left = message_padding // 2
    message_right = message_padding - message_left
    return f'║{" " * message_left}{text}{" " * message_right}║'


def _display_message_popup(stdscr, message):
    """
    Display a message popup and wait for any keypress.

    :param stdscr: curses window
    :param message: message to display
    """
    max_y, max_x = stdscr.getmaxyx()
    message_lines = message.splitlines() or ['']
    max_message_len = max(len(line) for line in message_lines)
    popup_width = min(max_message_len + 6, max_x - 4)
    popup_height = len(message_lines) + 4
    popup_y = (max_y - popup_height) // 2
    popup_x = (max_x - popup_width) // 2

    with suppress(curses.error):
        for y in range(popup_y, popup_y + popup_height):
            stdscr.addstr(y, popup_x, ' ' * popup_width)
        top_border = f'╔{"═" * (popup_width - 2)}╗'
        stdscr.addstr(popup_y, popup_x, top_border, curses.A_BOLD)
        for i, line in enumerate(message_lines):
            msg_line = _format_centered_popup_line(popup_width, line)
            stdscr.addstr(
                popup_y + 1 + i, popup_x, msg_line, curses.A_BOLD
            )
        instruction = 'Press any key'
        inst_line = _format_centered_popup_line(popup_width, instruction)
        stdscr.addstr(
            popup_y + 1 + len(message_lines), popup_x, inst_line
        )
        bottom_border = f'╚{"═" * (popup_width - 2)}╝'
        stdscr.addstr(
            popup_y + 2 + len(message_lines), popup_x, bottom_border,
            curses.A_BOLD
        )
        stdscr.refresh()
        stdscr.getch()


def _display_event_details_popup(stdscr, data_source, row_idx,
                                 detail_title='Row Details',
                                 draw_bg_fn=None,
                                 popup_key_handler=None):
    """
    Display a popup with all row details.

    :param stdscr: curses window
    :param data_source: DataSource instance
    :param row_idx: index of the currently displayed row
    :param detail_title: title shown in the popup header
    :param draw_bg_fn: optional callable(row_idx) to redraw the table
    :param popup_key_handler: optional callable(key, row_idx) to handle
        table-navigation keys while popup is open
    """
    max_y, max_x = stdscr.getmaxyx()
    title = f' {detail_title} '
    total_rows = data_source.total_count
    fields = data_source.fields

    def _render(lines, ridx, scroll_offset):
        can_scroll = len(lines) > display_lines
        popup_width = max_popup_width
        popup_x = (max_x - popup_width) // 2
        clear_x = (max_x - max_popup_width) // 2
        for y in range(popup_y, popup_y + popup_height):
            stdscr.addstr(y, clear_x, ' ' * max_popup_width)
        counter = f' {ridx + 1}/{total_rows} '
        inner = popup_width - 2
        top_border = f'╔{counter}{"═" * (inner - len(counter))}╗'
        stdscr.addstr(popup_y, popup_x, top_border, curses.A_BOLD)
        title_padding = popup_width - 2 - len(title)
        title_left = title_padding // 2
        title_right = title_padding - title_left
        title_line = f'║{" " * title_left}{title}{" " * title_right}║'
        stdscr.addstr(popup_y + 1, popup_x, title_line, curses.A_BOLD)
        sep_line = f'╠{"═" * (popup_width - 2)}╣'
        stdscr.addstr(popup_y + 2, popup_x, sep_line, curses.A_BOLD)
        available_width = popup_width - 4
        for i in range(display_lines):
            line_idx = scroll_offset + i
            if line_idx < len(lines):
                content = lines[line_idx]
                if len(content) > available_width:
                    content = content[:available_width]
                else:
                    content = content.ljust(available_width)
                stdscr.addstr(
                    popup_y + 3 + i, popup_x, f'║ {content} ║'
                )
        nav_hint = ' ↑/↓: next/prev |'
        scroll_hint = ' j/k: scroll |' if can_scroll else ''
        hint = f'{nav_hint}{scroll_hint} q/Esc/↵: close '
        inner_width = popup_width - 2
        hint_candidates = [
            hint,
            ' ↑/↓ ev | j/k scroll | q/Esc/↵ ',
            ' ↑/↓ | j/k | q/Esc ',
            ' q/Esc '
        ]
        hint_to_draw = next(
            (c for c in hint_candidates if len(c) <= inner_width), ''
        )
        if not hint_to_draw and inner_width > 0:
            hint_to_draw = hint_candidates[-1][:inner_width]
        hint_fill = inner_width - len(hint_to_draw)
        left_fill = hint_fill // 2
        right_fill = hint_fill - left_fill
        bottom_border = (
            f'╚{"═" * left_fill}{hint_to_draw}{"═" * right_fill}╝'
        )
        stdscr.addstr(
            popup_y + popup_height - 1,
            popup_x, bottom_border, curses.A_BOLD
        )
        stdscr.refresh()

    row = data_source.get_row(row_idx)
    lines = _build_detail_lines(fields, row)
    max_detail_line_len = max((len(line) for line in lines), default=0)
    max_popup_width = min(
        max(max_detail_line_len + 4, len(title) + 4), max_x - 4
    )
    max_display_lines = max(1, max_y - 8)
    display_lines = min(len(lines), max_display_lines)
    popup_height = display_lines + 4
    popup_y = (max_y - popup_height) // 2
    scroll_offset = 0

    while True:
        row = data_source.get_row(row_idx)
        lines = _build_detail_lines(fields, row)
        display_lines = min(len(lines), max_display_lines)
        scroll_offset = min(
            scroll_offset, max(0, len(lines) - display_lines)
        )
        with suppress(curses.error):
            if draw_bg_fn is not None:
                draw_bg_fn(row_idx)
            _render(lines, row_idx, scroll_offset)
        key = stdscr.getch()
        if key in [ord('q'), 27, ord('\n'), ord('\r'), curses.KEY_ENTER]:
            break
        if key in [ord('j')]:
            if scroll_offset + display_lines < len(lines):
                scroll_offset += 1
        elif key in [ord('k')]:
            if scroll_offset > 0:
                scroll_offset -= 1
        elif key in [curses.KEY_DOWN, ord(',')]:
            if row_idx < total_rows - 1:
                row_idx += 1
                scroll_offset = 0
        elif key in [curses.KEY_UP, ord('.')]:
            if row_idx > 0:
                row_idx -= 1
                scroll_offset = 0
        elif popup_key_handler is not None:
            new_row_idx = popup_key_handler(key, row_idx)
            if new_row_idx is not None:
                row_idx = new_row_idx
                scroll_offset = 0
    return row_idx


# ---------------------------------------------------------------------------
#  Sort-selector popup
# ---------------------------------------------------------------------------


def _draw_sort_popup_borders(
        stdscr, popup_y, popup_x, popup_width, popup_height,
        fields, selected_idx):
    """Draw the sort popup borders, title, and field list."""
    for y in range(popup_y, popup_y + popup_height):
        stdscr.addstr(y, popup_x, ' ' * popup_width)
    top_border = f'╔{"═" * (popup_width - 2)}╗'
    stdscr.addstr(popup_y, popup_x, top_border, curses.A_BOLD)
    title = ' Sort by column '
    title_padding = popup_width - 2 - len(title)
    title_left = title_padding // 2
    title_right = title_padding - title_left
    title_line = f'║{" " * title_left}{title}{" " * title_right}║'
    stdscr.addstr(popup_y + 1, popup_x, title_line, curses.A_BOLD)
    sep_line = f'╠{"═" * (popup_width - 2)}╣'
    stdscr.addstr(popup_y + 2, popup_x, sep_line, curses.A_BOLD)
    display_rows = popup_height - 4
    start_idx = max(0, selected_idx - display_rows // 2)
    end_idx = min(len(fields), start_idx + display_rows)
    for i in range(display_rows):
        y = popup_y + 3 + i
        if start_idx + i < end_idx:
            field_idx = start_idx + i
            field_name = fields[field_idx]
            prefix = _sort_column_prefix(field_idx)
            content = f'{prefix}{field_name}'
        else:
            content = ''
        padding = ' ' * (popup_width - 4)
        content = f'{content}{padding}'[:popup_width - 4]
        is_selected = (
            start_idx + i < len(fields)
            and start_idx + i == selected_idx
        )
        option_line = f'║ {content} ║'
        attr = curses.A_REVERSE if is_selected else 0
        stdscr.addstr(y, popup_x, option_line, attr)
    _draw_sort_popup_bottom(
        stdscr, popup_y, popup_x, popup_width, popup_height
    )
    stdscr.refresh()


def _sort_column_prefix(field_idx):
    """Return the key-hint prefix for a sort column."""
    if field_idx == 0:
        return '0. '
    return f'{field_idx}. ' if field_idx <= 9 else '  '


def _draw_sort_popup_bottom(stdscr, popup_y, popup_x, popup_width,
                            popup_height):
    """Draw the bottom border with a truncated hint."""
    hint = ' ↑/↓: navigate | 0-9: select | q/Esc: cancel '
    inner_width = popup_width - 2
    hint_candidates = [
        hint,
        ' ↑/↓ nav | 0-9 sel | q/Esc ',
        ' ↑/↓ | 0-9 | q/Esc ',
        ' q/Esc '
    ]
    hint_to_draw = next(
        (c for c in hint_candidates if len(c) <= inner_width), ''
    )
    if not hint_to_draw and inner_width > 0:
        hint_to_draw = hint_candidates[-1][:inner_width]
    hint_fill = inner_width - len(hint_to_draw)
    left_fill = hint_fill // 2
    right_fill = hint_fill - left_fill
    bottom_border = (
        f'╚{"═" * left_fill}{hint_to_draw}{"═" * right_fill}╝'
    )
    bottom_y = popup_y + popup_height - 1
    stdscr.addstr(bottom_y, popup_x, bottom_border, curses.A_BOLD)


def _handle_sort_popup_input(stdscr, fields, selected_idx):
    """Read and interpret a keypress in the sort popup."""
    try:
        key = stdscr.getch()
    except curses.error:
        return (None, selected_idx)
    if key in (ord('q'), 27):
        return (-1, selected_idx)
    if key in (ord('\n'), ord(' ')):
        return (selected_idx, selected_idx)
    if key in (curses.KEY_DOWN, ord('j')):
        return (None, min(len(fields) - 1, selected_idx + 1))
    if key in (curses.KEY_UP, ord('k')):
        return (None, max(0, selected_idx - 1))
    if chr(key).isdigit():
        digit = int(chr(key))
        col_num = 0 if digit == 0 else digit
        if 0 <= col_num < len(fields):
            return (col_num, selected_idx)
        return (None, selected_idx)
    return (None, selected_idx)


def _draw_sort_popup_and_get_input(
        stdscr, popup_y, popup_x, popup_width, popup_height,
        fields, selected_idx):
    """Draw sort selector popup and handle user input."""
    try:
        _draw_sort_popup_borders(
            stdscr, popup_y, popup_x, popup_width, popup_height,
            fields, selected_idx,
        )
        return _handle_sort_popup_input(stdscr, fields, selected_idx)
    except curses.error:
        return (None, selected_idx)


def _display_sort_selector(stdscr, data_source):
    """
    Display an interactive sort field selector popup.

    :param stdscr: curses window
    :param data_source: DataSource instance
    :return: selected column index (0-indexed), -2 for default sort,
        or None if cancelled
    """
    max_y, max_x = stdscr.getmaxyx()
    fields = ['default'] + list(data_source.fields)
    max_field_len = max(len(f) for f in fields) if fields else 0
    title_len = len(' Sort by column ')
    min_width = max(max_field_len + 6, title_len + 4)
    popup_width = min(min_width, max_x - 4)
    popup_height = min(len(fields) + 4, max_y - 4)
    popup_y = (max_y - popup_height) // 2
    popup_x = (max_x - popup_width) // 2
    selected_idx = 0
    while True:
        selected_col, selected_idx = _draw_sort_popup_and_get_input(
            stdscr, popup_y, popup_x, popup_width, popup_height,
            fields, selected_idx
        )
        if selected_col == -1:
            return None
        if selected_col is not None:
            return -2 if selected_col == 0 else selected_col - 1


# ---------------------------------------------------------------------------
#  Main pager rendering loop
# ---------------------------------------------------------------------------


def _draw_table(
        stdscr, header, body_rows, pager_state,
        available_rows, max_y, max_x,
        num_help_lines, help_line1, help_line2,
        sort_info, total_items, row_label, refresh=True):
    """Draw the table (header, body rows, help lines) onto stdscr."""
    stdscr.erase()
    with suppress(curses.error):
        header_scroll = header[pager_state['h_scroll']:]
        header_display = (
            header_scroll[:max_x] if len(header_scroll) > max_x
            else header_scroll
        )
        stdscr.addstr(0, 0, header_display, curses.A_REVERSE)
        page_rows = body_rows[:available_rows]
        for i, row in enumerate(page_rows):
            row_scroll = row[pager_state['h_scroll']:]
            row_display = (
                row_scroll[:max_x] if len(row_scroll) > max_x
                else row_scroll
            )
            row_index = pager_state['offset'] + i
            if row_index == pager_state['selected_row']:
                color_attr = curses.A_REVERSE
            else:
                try:
                    color_attr = (
                        curses.color_pair(1)
                        if row_index % 2 == 0
                        else curses.color_pair(2)
                    )
                except curses.error:
                    color_attr = 0
            stdscr.addstr(1 + i, 0, row_display, color_attr)
    first_visible = pager_state['offset'] + 1
    last_visible = min(
        pager_state['offset'] + available_rows, total_items
    )
    status_text = (
        f'{row_label} {first_visible}-{last_visible} of '
        f'{total_items}{sort_info}'
    )
    _draw_help_bar(
        stdscr, max_y, max_x,
        num_help_lines, help_line1, help_line2, status_text,
    )
    if refresh:
        stdscr.refresh()


def _draw_help_bar(stdscr, max_y, max_x, num_help_lines,
                   help_line1, help_line2, status_text):
    """Draw the bottom help / status bar."""
    with suppress(curses.error):
        if num_help_lines == 1:
            full_help = f'{help_line1} | {help_line2}'
            full_line = f'{full_help} | {status_text}'
            if len(full_line) <= max_x:
                help_display = f'{full_line}{" " * max_x}'[:max_x]
            else:
                help_display = f'{status_text}{" " * max_x}'[:max_x]
            stdscr.addstr(max_y - 1, 0, help_display, curses.A_REVERSE)
        else:
            width_available = (
                max_x - len(help_line1) - len(status_text) - 3
            )
            padding_width = max(0, width_available)
            line1 = (
                f'{help_line1} | {" " * padding_width}{status_text}'
            )
            line1 = f'{line1}{" " * max_x}'[:max_x]
            line2 = f'{help_line2}{" " * max_x}'[:max_x]
            stdscr.addstr(max_y - 2, 0, line1, curses.A_REVERSE)
            stdscr.addstr(max_y - 1, 0, line2, curses.A_REVERSE)


def _handle_copy_key(stdscr, pager_state, data_source, total_count,
                     copy_label, copy_fn):
    """Handle clipboard copy (``c`` key)."""
    row_idx = pager_state['selected_row']
    if not 0 <= row_idx < total_count:
        return True
    row = data_source.get_row(row_idx)
    if not row:
        return True
    value = _do_copy(row, copy_fn)
    if _copy_to_clipboard(value):
        message = f'{copy_label} {value} copied to clipboard'
    else:
        message = CLIPBOARD_FAIL_MESSAGE
    _display_message_popup(stdscr, message)
    return True


def _handle_sort_key(key, pager_state, data_source, stdscr):
    """Handle sort keys (``0``, ``s``, ``1``-``9``).

    Returns True if a sort key was handled, False otherwise.
    """
    if key == ord('0'):
        pager_state['sort_col'] = pager_state.get('default_sort_col')
        pager_state['sort_asc'] = pager_state.get('default_sort_asc', True)
        pager_state['offset'] = 0
        pager_state['selected_row'] = 0
        return True
    if key == ord('s'):
        _handle_sort_selector_key(pager_state, data_source, stdscr)
        return True
    if chr(key) in '123456789':
        _handle_numeric_sort_key(key, pager_state, data_source)
        return True
    return False


def _handle_sort_selector_key(pager_state, data_source, stdscr):
    """Handle ``s`` key — open the sort selector popup."""
    selected_col = _display_sort_selector(stdscr, data_source)
    if selected_col == -2:
        pager_state['sort_col'] = pager_state.get('default_sort_col')
        pager_state['sort_asc'] = pager_state.get('default_sort_asc', True)
    elif selected_col is not None:
        _toggle_sort_column(pager_state, selected_col)


def _handle_numeric_sort_key(key, pager_state, data_source):
    """Handle ``1``-``9`` numeric sort keys."""
    col_num = int(chr(key)) - 1
    if col_num < len(data_source.fields):
        _toggle_sort_column(pager_state, col_num)


def _toggle_sort_column(pager_state, col_num):
    """Toggle sort direction or switch sort column."""
    if pager_state.get('sort_col') == col_num:
        pager_state['sort_asc'] = not pager_state.get('sort_asc', True)
    else:
        pager_state['sort_col'] = col_num
        pager_state['sort_asc'] = True
    pager_state['offset'] = 0
    pager_state['selected_row'] = 0


def _handle_hscroll_key(key, pager_state, enable_h_scroll,
                        max_row_width, max_x):
    """Handle horizontal scroll keys."""
    if key == curses.KEY_LEFT and enable_h_scroll:
        pager_state['h_scroll'] = max(0, pager_state['h_scroll'] - 5)
    elif key == curses.KEY_RIGHT and enable_h_scroll:
        pager_state['h_scroll'] = min(
            max_row_width - max_x, pager_state['h_scroll'] + 5
        )
    elif key == getattr(curses, 'KEY_SLEFT', None):
        pager_state['h_scroll'] = 0
    elif key == getattr(curses, 'KEY_SRIGHT', None) and enable_h_scroll:
        pager_state['h_scroll'] = max_row_width - max_x


def _handle_pager_input(stdscr, pager_state, available_rows,
                        enable_h_scroll, max_row_width, max_x,
                        data_source, copy_label, copy_fn=None,
                        detail_title='Row Details',
                        redraw_bg=None, popup_key_handler=None):
    """Handle keyboard input for pager navigation and sorting."""
    try:
        key = stdscr.getch()
    except (OSError, KeyboardInterrupt):
        return False
    if key in (ord('q'), 27):
        return False
    total_count = data_source.total_count

    if key == ord('c'):
        return _handle_copy_key(
            stdscr, pager_state, data_source, total_count,
            copy_label, copy_fn,
        )
    if key in (ord('\n'), ord('\r'), curses.KEY_ENTER):
        row_idx = pager_state['selected_row']
        if 0 <= row_idx < total_count:
            new_idx = _display_event_details_popup(
                stdscr, data_source, row_idx,
                detail_title=detail_title,
                draw_bg_fn=redraw_bg,
                popup_key_handler=popup_key_handler,
            )
            pager_state['selected_row'] = new_idx
        return True
    if _handle_sort_key(key, pager_state, data_source, stdscr):
        return True
    _handle_hscroll_key(
        key, pager_state, enable_h_scroll, max_row_width, max_x,
    )
    _handle_nav_keys(
        key, pager_state, available_rows, total_count,
    )
    return True


def _handle_nav_keys(key, pager_state, available_rows, total_count):
    """Handle vertical navigation keys (arrows, page, home, end)."""
    # Down
    if key == curses.KEY_DOWN:
        if pager_state['selected_row'] < total_count - 1:
            pager_state['selected_row'] += 1
            if pager_state['selected_row'] >= (
                    pager_state['offset'] + available_rows):
                pager_state['offset'] += 1
    # Up
    elif key == curses.KEY_UP:
        if pager_state['selected_row'] > 0:
            pager_state['selected_row'] -= 1
            if pager_state['selected_row'] < pager_state['offset']:
                pager_state['offset'] -= 1
    # Page Down
    elif key in [
        curses.KEY_NPAGE,
        ord('f'), ord(' '),
        getattr(curses, 'KEY_SF', None),
    ]:
        pager_state['offset'] = min(
            pager_state['offset'] + available_rows,
            max(0, total_count - available_rows),
        )
        pager_state['selected_row'] = min(
            pager_state['selected_row'] + available_rows,
            total_count - 1,
        )
    # Page Up
    elif key in [
        curses.KEY_PPAGE,
        ord('b'),
        getattr(curses, 'KEY_SR', None),
    ]:
        pager_state['offset'] = max(
            0, pager_state['offset'] - available_rows,
        )
        pager_state['selected_row'] = max(
            0, pager_state['selected_row'] - available_rows,
        )
    # Home
    elif key in (curses.KEY_HOME, ord('g')):
        pager_state['offset'] = 0
        pager_state['selected_row'] = 0
    # End
    elif key in (curses.KEY_END, ord('G')):
        pager_state['selected_row'] = total_count - 1
        pager_state['offset'] = max(0, total_count - available_rows)


def _build_help_lines(copy_label):
    """Build the two help-line strings shown at the bottom."""
    line1 = (
        'q/Esc: quit | ↵: details | ↓/↑/j/k: move'
        ' | ←/→: scroll | ⇧←/⇧→: begin/end'
        f' | c: copy {copy_label}'
    )
    line2 = (
        'Space/f/PgDn/⇧↓: page↓ | b/PgUp/⇧↑: page↑'
        ' | g/Home | G/End | 0: dflt | 1-9/s: sort'
    )
    return line1, line2


def _build_sort_info(data_source, pager_state):
    """Build the 'Sorted by ...' status string."""
    sort_col = pager_state.get('sort_col')
    if sort_col is None or sort_col >= len(data_source.fields):
        return ''
    field_name = data_source.fields[sort_col]
    sort_dir = '↑' if pager_state.get('sort_asc', True) else '↓'
    return f' | Sorted by {field_name} {sort_dir}'


def _determine_help_layout(max_x, help_line1, help_line2, status_text):
    """Decide 1-line vs 2-line bottom help bar."""
    full_help = f'{help_line1} | {help_line2}'
    full_line = f'{full_help} | {status_text}'
    return 2 if len(full_line) > max_x else 1


def _pager_loop_iteration(
        stdscr, data_source, pager_state, row_label, copy_label,
        copy_fn=None, detail_title='Row Details'):
    """Handle one iteration of the table pager loop."""
    max_y, max_x = stdscr.getmaxyx()
    total_items = data_source.total_count
    if total_items == 0:
        _display_message_popup(stdscr, f'No {row_label.lower()} to display.')
        return False

    help_line1, help_line2 = _build_help_lines(copy_label)
    sort_info = _build_sort_info(data_source, pager_state)
    status_text = (
        f'{row_label} 1-{total_items} of {total_items}{sort_info}'
    )
    num_help_lines = _determine_help_layout(
        max_x, help_line1, help_line2, status_text
    )
    available_rows = max_y - 1 - num_help_lines

    # Fetch and format current page of data
    max_col_width = pager_state.get(
        'max_col_width', DEFAULT_MAX_COLUMN_WIDTH
    )
    raw_rows = data_source.get_rows(
        pager_state['offset'], available_rows,
        pager_state.get('sort_col'),
        pager_state.get('sort_asc', True),
    )
    header, body_rows, _ = _format_rows(
        data_source.fields, raw_rows, max_col_width=max_col_width
    )

    # Compute max row width for horizontal scrolling
    max_row_width = max(
        len(header),
        max((len(r) for r in body_rows), default=0)
    )
    enable_h_scroll = max_row_width > max_x
    if enable_h_scroll:
        pager_state['h_scroll'] = max(
            0, min(pager_state['h_scroll'], max_row_width - max_x)
        )
    else:
        pager_state['h_scroll'] = 0

    _draw_table(
        stdscr, header, body_rows, pager_state,
        available_rows, max_y, max_x,
        num_help_lines, help_line1, help_line2,
        sort_info, total_items, row_label
    )

    def _redraw_bg(new_row_idx):
        pager_state['selected_row'] = new_row_idx
        if new_row_idx >= pager_state['offset'] + available_rows:
            pager_state['offset'] = new_row_idx - available_rows + 1
        elif new_row_idx < pager_state['offset']:
            pager_state['offset'] = new_row_idx
        raw = data_source.get_rows(
            pager_state['offset'], available_rows,
            pager_state.get('sort_col'),
            pager_state.get('sort_asc', True),
        )
        hdr, body, _ = _format_rows(
            data_source.fields, raw, max_col_width=max_col_width
        )
        _draw_table(
            stdscr, hdr, body, pager_state,
            available_rows, max_y, max_x,
            num_help_lines, help_line1, help_line2,
            sort_info, total_items, row_label, refresh=False
        )

    def _handle_popup_key(key, current_row_idx):
        if key == curses.KEY_LEFT and enable_h_scroll:
            pager_state['h_scroll'] = max(
                0, pager_state['h_scroll'] - 5
            )
            return current_row_idx
        if key == curses.KEY_RIGHT and enable_h_scroll:
            pager_state['h_scroll'] = min(
                max_row_width - max_x, pager_state['h_scroll'] + 5
            )
            return current_row_idx
        if key == getattr(curses, 'KEY_SLEFT', None):
            pager_state['h_scroll'] = 0
            return current_row_idx
        if key == getattr(curses, 'KEY_SRIGHT', None) and enable_h_scroll:
            pager_state['h_scroll'] = max_row_width - max_x
            return current_row_idx
        if key == ord('c'):
            if 0 <= current_row_idx < total_items:
                row = data_source.get_row(current_row_idx)
                if row:
                    value = _do_copy(row, copy_fn)
                    if _copy_to_clipboard(value):
                        msg = (
                            f'{copy_label} {value} '
                            f'copied to clipboard'
                        )
                    else:
                        msg = CLIPBOARD_FAIL_MESSAGE
                    _display_message_popup(stdscr, msg)
            return current_row_idx
        if key in [
            curses.KEY_PPAGE,
            ord('b'),
            getattr(curses, 'KEY_SR', None),  # Shift+Up
        ]:
            pager_state['offset'] = max(
                0, pager_state['offset'] - available_rows
            )
            pager_state['selected_row'] = max(
                0, pager_state['selected_row'] - available_rows
            )
            return pager_state['selected_row']
        if key in [
            curses.KEY_NPAGE,
            ord('f'), ord(' '),
            getattr(curses, 'KEY_SF', None),  # Shift+Down
        ]:
            pager_state['offset'] = min(
                pager_state['offset'] + available_rows,
                max(0, total_items - available_rows)
            )
            pager_state['selected_row'] = min(
                pager_state['selected_row'] + available_rows,
                total_items - 1
            )
            return pager_state['selected_row']
        if key in [curses.KEY_HOME, ord('g')]:
            pager_state['offset'] = 0
            pager_state['selected_row'] = 0
            return pager_state['selected_row']
        if key in [curses.KEY_END, ord('G')]:
            pager_state['selected_row'] = total_items - 1
            pager_state['offset'] = max(
                0, total_items - available_rows
            )
            return pager_state['selected_row']
        return None

    return _handle_pager_input(
        stdscr, pager_state, available_rows,
        enable_h_scroll, max_row_width, max_x,
        data_source, copy_label, copy_fn=copy_fn,
        detail_title=detail_title,
        redraw_bg=_redraw_bg,
        popup_key_handler=_handle_popup_key
    )


# ---------------------------------------------------------------------------
#  Public entry point
# ---------------------------------------------------------------------------


def display_table_pager(
    data_source,
    row_label='Rows',
    copy_label=None,
    copy_fn=None,
    detail_title='Row Details',
    default_sort_col=None,
    default_sort_asc=True,
    max_col_width=DEFAULT_MAX_COLUMN_WIDTH,
):
    """
    Display an interactive table pager using curses.

    :param data_source: DataSource providing rows to display.
    :type data_source: DataSource
    :param row_label: Label for rows in the status bar
        (e.g. ``'Events'``).
    :param copy_label: Label for the copy-to-clipboard message
        (default: first field name).
    :param copy_fn: Optional callable ``copy_fn(row) -> str`` that
        returns the text to copy.  When omitted the first column
        is used.
    :param detail_title: Title for the row detail popup
        (default ``'Row Details'``).
    :param default_sort_col: Default column index for sorting.
    :param default_sort_asc: Default sort direction.
    :param max_col_width: Maximum column width in characters.
    :raises PagerException: if the pager fails to initialize or run
    """
    if copy_label is None and data_source.fields:
        copy_label = data_source.fields[0]

    def _wrapper(stdscr):
        with suppress(curses.error, AttributeError):
            curses.use_default_colors()
        if curses.has_colors():
            with suppress(curses.error):
                curses.init_pair(1, -1, -1)
                curses.init_pair(2, curses.COLOR_CYAN, -1)
        stdscr.keypad(True)
        with suppress(curses.error, AttributeError):
            curses.mousemask(0)
        with suppress(curses.error, AttributeError):
            curses.curs_set(0)
        with suppress(curses.error, AttributeError):
            curses.set_escdelay(25)

        # If data source needs a first count query, run it with an
        # interruptible busy popup (Ctrl+C / q / Esc cancels).
        _run_with_busy_popup(
            stdscr, 'Loading... please wait',
            lambda: data_source.total_count
        )
        _flush_pending_input()

        pager_state = {
            'offset': 0,
            'selected_row': 0,
            'h_scroll': 0,
            'sort_col': default_sort_col,
            'sort_asc': default_sort_asc,
            'default_sort_col': default_sort_col,
            'default_sort_asc': default_sort_asc,
            'max_col_width': max_col_width,
        }

        while True:
            should_continue = _pager_loop_iteration(
                stdscr, data_source, pager_state,
                row_label, copy_label, copy_fn=copy_fn,
                detail_title=detail_title,
            )
            if not should_continue:
                break

    try:
        curses.wrapper(_wrapper)
    except (curses.error, OSError, KeyboardInterrupt) as e:
        raise PagerException(f'Pager failed: {e}') from e
