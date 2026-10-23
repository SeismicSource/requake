# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Colored terminal output and hyperlink helpers.

Colors and hyperlinks are used only when the output stream is an
interactive terminal, so they are automatically removed when the output
is piped to another command or redirected to a file.  The ``NO_COLOR``
and ``FORCE_COLOR`` environment variables can be used to force colors
off or on.

Hyperlinks additionally require a terminal known to support OSC 8, since
many terminals that handle colors (e.g. ``xterm``) ignore them; the
``NO_HYPERLINK`` and ``FORCE_HYPERLINK`` environment variables can be
used to force hyperlinks off or on.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os
import re
import sys
import contextlib
import unicodedata


_RESET = '\x1b[0m'

# Accent applied to the text of terminal hyperlinks.  The dashed
# underline (SGR 4:5) degrades to a plain underline on terminals that do
# not support it.
_LINK_STYLES = ('dashed_underline',)

# Link accent color: a mid-tone blue with a contrast ratio above 4:1
# against both black and white, so that it stays readable on dark and
# light terminals alike.  It is emitted as truecolor when available and
# as the closest 256-color palette entry (31) otherwise.
_LINK_RGB = (0, 116, 217)
_LINK_RGB_256 = (0, 135, 175)
_LINK_COLOR_TRUECOLOR = '\x1b[38;2;{};{};{}m'.format(*_LINK_RGB)
_LINK_COLOR_256 = '\x1b[38;5;31m'

# Scheme dropped from the displayed URL, since the link carries the target
_URL_SCHEME = re.compile(r'^https?://')

# Escape sequences that do not occupy terminal columns: CSI (colors and
# styles) and OSC (hyperlinks)
_ESCAPE_PATTERN = re.compile(
    r'\x1b\[[0-?]*[ -/]*[@-~]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
)

# Terminals known to support OSC 8 hyperlinks, by ``TERM_PROGRAM`` value
_HYPERLINK_TERM_PROGRAMS = frozenset({
    'Hyper', 'Rio', 'WezTerm', 'ghostty', 'iTerm.app', 'vscode',
})

# Terminals known to support OSC 8 hyperlinks, by ``TERM`` value
_HYPERLINK_TERMS = frozenset({
    'alacritty', 'foot', 'foot-extra', 'kitty', 'wezterm',
    'xterm-ghostty', 'xterm-kitty',
})

# Minimum versions of VTE (GNOME Terminal and friends) and Konsole
# supporting OSC 8 hyperlinks
_VTE_MIN_VERSION = 5000
_KONSOLE_MIN_VERSION = 210400

_CODES = {
    'bold': '\x1b[1m',
    'dim': '\x1b[2m',
    'italic': '\x1b[3m',
    'underline': '\x1b[4m',
    'dashed_underline': '\x1b[4m\x1b[4:5m',
    'black': '\x1b[30m',
    'red': '\x1b[31m',
    'green': '\x1b[32m',
    'yellow': '\x1b[33m',
    'blue': '\x1b[34m',
    'magenta': '\x1b[35m',
    'cyan': '\x1b[36m',
    'white': '\x1b[37m',
    'dark_orange': '\x1b[38;5;208m',
    'gray': '\x1b[38;5;244m',
}


def color_enabled(stream=None):
    """
    Return whether colored output should be used for ``stream``.

    Colors are enabled only for interactive terminals, are disabled
    when the ``NO_COLOR`` environment variable is set or ``TERM`` is
    ``dumb``, and are forced when the ``FORCE_COLOR`` environment
    variable is set.

    :param stream: output stream used to decide if colors are enabled
        (defaults to ``sys.stdout``)
    :type stream: io.TextIOBase

    :return: True if colored output should be used
    :rtype: bool
    """
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    if os.environ.get('TERM') == 'dumb':
        return False
    if stream is None:
        stream = sys.stdout
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _known_hyperlink_terminal():
    """
    Return whether the current terminal is known to support OSC 8.

    Detection is based on the environment variables exported by the
    terminals themselves.  Unknown terminals are treated as unsupported,
    because emitting OSC 8 to a terminal that ignores it would show the
    URL without its scheme and without a working link.

    :return: True if the terminal supports OSC 8 hyperlinks
    :rtype: bool
    """
    if os.environ.get('WT_SESSION'):
        return True
    if os.environ.get('TERM_PROGRAM') in _HYPERLINK_TERM_PROGRAMS:
        return True
    if os.environ.get('LC_TERMINAL') == 'iTerm2':
        return True
    for var, min_version in (
        ('VTE_VERSION', _VTE_MIN_VERSION),
        ('KONSOLE_VERSION', _KONSOLE_MIN_VERSION),
    ):
        with contextlib.suppress(ValueError):
            if int(os.environ.get(var, 0)) >= min_version:
                return True
    return os.environ.get('TERM', '') in _HYPERLINK_TERMS


def _hyperlink_enabled(stream=None):
    """
    Return whether OSC 8 hyperlinks should be used for ``stream``.

    Hyperlinks require an interactive terminal with colors enabled, and
    a terminal known to support OSC 8 (see
    :func:`_known_hyperlink_terminal`).  The ``NO_HYPERLINK`` and
    ``FORCE_HYPERLINK`` environment variables force them off and on.

    :param stream: output stream used to decide if hyperlinks are enabled
        (defaults to ``sys.stdout``)
    :type stream: io.TextIOBase

    :return: True if hyperlinks should be used
    :rtype: bool
    """
    if os.environ.get('NO_HYPERLINK'):
        return False
    if os.environ.get('FORCE_HYPERLINK'):
        return True
    return color_enabled(stream) and _known_hyperlink_terminal()


def style(text, *styles, stream=None):
    """
    Apply ANSI styles to ``text``.

    :param text: text to be styled
    :type text: str
    :param styles: style names, e.g. ``'bold'``, ``'cyan'``
    :type styles: str
    :param stream: output stream used to decide if colors are enabled
    :type stream: io.TextIOBase

    :return: styled text, or plain text when colors are disabled
    :rtype: str
    """
    text = str(text)
    if not styles or not color_enabled(stream):
        return text
    unknown = [name for name in styles if name not in _CODES]
    if unknown:
        raise ValueError(f'Unknown style(s): {", ".join(unknown)}')
    prefix = ''.join(_CODES[name] for name in styles)
    return f'{prefix}{text}{_RESET}'


def _link_color():
    """
    Return the SGR sequence for the link accent color.

    Truecolor is used when the terminal advertises it, otherwise the
    closest 256-color palette entry is used.

    :return: SGR escape sequence
    :rtype: str
    """
    colorterm = os.environ.get('COLORTERM', '').lower()
    if colorterm in ('truecolor', '24bit'):
        return _LINK_COLOR_TRUECOLOR
    return _LINK_COLOR_256


def hyperlink(url, text=None, stream=None):
    """
    Make ``url`` clickable in terminals supporting OSC 8 hyperlinks.

    The link text is accented in a mid-tone blue, readable on both dark
    and light terminals, with a dashed underline, so that it stands out
    from the surrounding text.  When no display text is given, the URL
    is shown without its ``http://`` or ``https://`` scheme, since the
    link itself carries the target.

    The escape sequences are emitted only when the stream is an
    interactive terminal with colors enabled and the terminal is known to
    support OSC 8 (see :func:`_hyperlink_enabled`).  In every other case
    the full URL is returned as plain text, so that it stays readable and
    usable when copied -- notably in terminals, such as ``xterm``, that
    support colors but silently drop OSC 8 sequences.

    :param url: target of the link
    :type url: str
    :param text: text displayed in place of ``url``
    :type text: str
    :param stream: output stream used to decide if hyperlinks are enabled
    :type stream: io.TextIOBase

    :return: clickable text, or plain text when hyperlinks are disabled
    :rtype: str
    """
    url = str(url)
    if not _hyperlink_enabled(stream):
        return url if text is None else str(text)
    text = _URL_SCHEME.sub('', url) if text is None else str(text)
    text = f'{_link_color()}{style(text, *_LINK_STYLES, stream=stream)}'
    # OSC 8 ; params ; URI ST text OSC 8 ; ; ST
    return f'\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\'


def _display_width(text):
    """
    Return the number of terminal columns used by ``text``.

    Escape sequences are ignored, and wide characters (e.g. emoji) are
    counted as two columns.

    :param text: text to measure
    :type text: str

    :return: number of columns
    :rtype: int
    """
    text = _ESCAPE_PATTERN.sub('', text)
    return sum(
        2 if unicodedata.east_asian_width(char) in 'WF' else 1
        for char in text if not unicodedata.combining(char)
    )


def frame(text, stream=None):
    """
    Draw a frame around ``text``.

    Lines are padded to the width of the longest one, escape sequences
    (colors and hyperlinks) and wide characters being taken into
    account.  The frame is drawn in red when colors are enabled.

    :param text: text to be framed
    :type text: str
    :param stream: output stream used to decide if colors are enabled
    :type stream: io.TextIOBase

    :return: framed text
    :rtype: str
    """
    lines = str(text).splitlines() or ['']
    width = max(_display_width(line) for line in lines)
    border = '─' * (width + 2)
    bar = style('│', 'red', stream=stream)
    framed = [
        style(f'┌{border}┐', 'red', stream=stream),
        *(
            f'{bar} {line}{" " * (width - _display_width(line))} {bar}'
            for line in lines
        ),
        style(f'└{border}┘', 'red', stream=stream),
    ]
    return '\n'.join(framed)


def error(text, stream=None):
    """
    Format ``text`` as an error message.

    :param text: error message
    :type text: str
    :param stream: output stream used to decide if colors are enabled
    :type stream: io.TextIOBase

    :return: formatted error message
    :rtype: str
    """
    prefix = style('ERROR:', 'bold', 'red', stream=stream)
    return f'{prefix} {text}'


def warning(text, stream=None):
    """
    Format ``text`` as a warning message.

    :param text: warning message
    :type text: str
    :param stream: output stream used to decide if colors are enabled
    :type stream: io.TextIOBase

    :return: formatted warning message
    :rtype: str
    """
    prefix = style('WARNING:', 'bold', 'yellow', stream=stream)
    return f'{prefix} {text}'
