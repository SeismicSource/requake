# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Colored terminal output helpers.

Colors are used only when the output stream is an interactive
terminal, so they are automatically removed when the output is piped
to another command or redirected to a file.  The ``NO_COLOR`` and
``FORCE_COLOR`` environment variables can be used to force colors off
or on.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os
import sys


_RESET = '\x1b[0m'

_CODES = {
    'bold': '\x1b[1m',
    'dim': '\x1b[2m',
    'italic': '\x1b[3m',
    'underline': '\x1b[4m',
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
