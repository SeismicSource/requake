# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Colored help and usage output for the Requake command line.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import re
import sys
import textwrap
import argparse
from ..terminal import color_enabled, hyperlink, style

# Stream that help or usage output is being written to; used to decide
# whether colors should be used.  ``None`` means ``sys.stdout``.
_help_stream = None

_USAGE_PREFIX = 'Usage: '

# Tokens to colorize inside a usage line: option strings, ``<metavars>``,
# uppercase metavars and the trailing ellipsis.  Square brackets belong to
# the usage grammar and are left uncolored.
_USAGE_TOKEN_PATTERN = (
    r'\[|\]'
    r'|(?<![\w-])-{1,2}[A-Za-z][\w-]*'
    r'|<[^<>]+>'
    r'|(?<![\w])[A-Z][A-Z0-9_]+'
    r'|\.\.\.'
)

# URLs in help text, excluding common trailing punctuation so that it is
# not swallowed by the hyperlink.
_URL_PATTERN = re.compile(r'https?://[^\s<>"\']*[^\s<>"\'\.,;:]')


def _set_help_stream(stream):
    """Set the stream help output is being written to."""
    global _help_stream  # pylint: disable=global-statement
    _help_stream = stream


def _help_colors_enabled():
    """Return True if help output should be colorized."""
    return color_enabled(_help_stream)


def _style_help(text, *styles):
    """Style a piece of help output."""
    return style(text, *styles, stream=_help_stream)


def _linkify_url(match):
    """Turn a URL found in help output into a clickable hyperlink."""
    return hyperlink(match.group(), stream=_help_stream)


def _linkify_urls(text):
    """Make the URLs in a piece of help output clickable."""
    return _URL_PATTERN.sub(_linkify_url, text)


def _colorize_usage_token(match):
    """Colorize a single token of a usage line."""
    token = match.group()
    return token if token in ('[', ']') else _style_help(token, 'cyan')


def _collect_metavars(formatter, actions):
    """Return the metavar strings of a set of actions."""
    metavars = []
    for action in actions:
        if isinstance(action.metavar, str):
            metavars.append(action.metavar)
        elif not action.option_strings:
            default = formatter._get_default_metavar_for_positional(action)
            metavars.extend(formatter._metavar_formatter(action, default)(1))
    return metavars


def _colorize_usage_args(text, metavars):
    """Colorize options and metavars in a usage string."""
    literals = sorted(
        (m for m in metavars if m), key=len, reverse=True
    )
    pattern = '|'.join(
        [re.escape(item) for item in literals] + [_USAGE_TOKEN_PATTERN]
    )
    return re.compile(pattern).sub(_colorize_usage_token, text)


def _colorize_usage(text, prog, metavars):
    """Colorize a usage line (prefix, program name and arguments)."""
    if not text.startswith(_USAGE_PREFIX):
        return text
    body = text[len(_USAGE_PREFIX):]
    if prog and body.startswith(prog):
        program = _style_help(prog, 'gray')
        body = body[len(prog):]
    else:
        program = ''
    args = _colorize_usage_args(body, metavars)
    return f'{_style_help(_USAGE_PREFIX, "dark_orange")}{program}{args}'


def _colorize_action(text, invocation):
    """Colorize the option strings or the name of a formatted action."""
    if not invocation or not _help_colors_enabled():
        return text
    return text.replace(invocation, _style_help(invocation, 'cyan'), 1)


class ColoredHelpMixin:
    """Add colors and clickable URLs to argparse help and usage output."""

    def format_help(self):
        """Make the URLs in the help output clickable."""
        return _linkify_urls(super().format_help())

    def format_usage(self):
        """Make the URLs in the usage output clickable."""
        return _linkify_urls(super().format_usage())

    def start_section(self, heading):
        """Capitalize and colorize section headings."""
        if heading and heading is not argparse.SUPPRESS:
            heading = _style_help(heading.title(), 'dark_orange')
        super().start_section(heading)

    def _format_usage(self, usage, actions, groups, prefix):
        """Colorize the usage line."""
        if prefix is None:
            prefix = _USAGE_PREFIX
        text = super()._format_usage(usage, actions, groups, prefix)
        if not _help_colors_enabled():
            return text
        metavars = _collect_metavars(self, actions)
        return _colorize_usage(text, self._prog, metavars)

    def _format_action_invocation(self, action):
        """Hide the deprecated spellings of an option string."""
        invocation = super()._format_action_invocation(action)
        for alias in getattr(action, 'hidden_aliases', ()):
            invocation = invocation.replace(f', {alias}', '')
        return invocation

    def _format_action(self, action):
        """Colorize the option strings or the name of an action."""
        text = super()._format_action(action)
        return _colorize_action(text, self._format_action_invocation(action))


class ColoredHelpFormatter(ColoredHelpMixin, argparse.HelpFormatter):
    """Default help formatter, with colored output."""


class NewlineHelpFormatter(ColoredHelpMixin, argparse.HelpFormatter):
    """Custom help formatter that preserves newlines in help messages."""

    def _split_lines(self, text, width):
        lines = []
        for line in text.splitlines():  # Split the text by newlines first
            if len(line) > width:
                # Use textwrap to wrap lines that are too long
                wrap_lines = textwrap.wrap(line, width)
                lines.extend(wrap_lines)
            else:
                # For lines that are short enough, just add them as they are
                lines.append(line)
        return lines


class SubcommandHelpFormatter(
    ColoredHelpMixin, argparse.RawDescriptionHelpFormatter
):
    """
    Custom help formatter that removes the subcommand list from help.

    See: https://stackoverflow.com/a/13429281/2021880
    """

    def _format_action(self, action):
        parts = super(
            argparse.RawDescriptionHelpFormatter, self
        )._format_action(action)
        if action.nargs == argparse.PARSER:
            parts = '\n'.join(parts.split('\n')[1:])
        return _colorize_action(parts, self._format_action_invocation(action))


class ColoredHelpArgumentParser(argparse.ArgumentParser):
    """Argument parser whose help and usage output is colored on terminals."""

    def __init__(self, *args, **kwargs):
        """Set up the parser with the colored help formatter."""
        kwargs.setdefault('formatter_class', ColoredHelpFormatter)
        super().__init__(*args, **kwargs)

    def print_help(self, file=None):
        """Print the help message, colorized if ``file`` is a terminal."""
        _set_help_stream(sys.stdout if file is None else file)
        try:
            super().print_help(file)
        finally:
            _set_help_stream(None)

    def print_usage(self, file=None):
        """Print the usage message, colorized if ``file`` is a terminal."""
        _set_help_stream(sys.stdout if file is None else file)
        try:
            super().print_usage(file)
        finally:
            _set_help_stream(None)
