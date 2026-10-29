# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utility functions for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os
import sys
import locale
import shutil
import hashlib
import threading
import multiprocessing
from datetime import datetime
from ..terminal import (
    display_width, error, frame, hyperlink, style, truncate_to_width,
)
from .configobj import ConfigObj, ParseError
from .configobj.validate import Validator
locale.setlocale(locale.LC_ALL, '')


_seen_msgs = set()


def log_once(logger, level, msg, *args, **kwargs):
    """
    Log a message only once.

    :param logger: Logger object.
    :type logger: logging.Logger
    :param level: Log level.
    :type level: str
    :param msg: Message to log.
    :type msg: str
    :param args: Arguments for the message.
    :param kwargs: Keyword arguments for the message.
    """
    text = str(msg)
    digest = hashlib.blake2b(
        text.encode('utf-8'),
        digest_size=8,
    ).digest()
    if digest in _seen_msgs:
        return
    _seen_msgs.add(digest)
    log_fn = getattr(logger, level, None)
    if log_fn is None:
        raise ValueError(f'Invalid log level: {level}')
    log_fn(text, *args, **kwargs)


def err_exit(msg):
    """
    Exit with error message.

    :param msg: Error message.
    :type msg: str
    """
    sys.stderr.write(error(msg, stream=sys.stderr) + '\n')
    sys.exit(1)


def parse_configspec():
    """
    Parse configuration specification file.

    :return: Configuration specification object.
    :rtype: configobj.ConfigObj
    """
    curdir = os.path.dirname(__file__)
    configspec_file = os.path.join(curdir, 'configspec.conf')
    return read_config(configspec_file)


def confirm_action(prompt, default=False):
    """
    Ask for yes/no confirmation and return True for yes.

    :param prompt: Prompt shown to the user.
    :type prompt: str
    :param default: Default answer when user provides empty input.
    :type default: bool
    :return: True if user confirms, False otherwise.
    :rtype: bool
    """
    suffix = style('[Y/n] ', 'dim') if default else style('[y/N] ', 'dim')
    answer = input(f'{style(prompt, "bold")} {suffix}').strip()
    return answer.lower() in {'y', 'yes'} if answer else default


def write_ok(filepath, force=False):
    """
    Check if a file can be written.

    :param filepath: File path.
    :type filepath: str
    :param force: Force writing.
    :type force: bool

    :return: True if file can be written, False otherwise.
    :rtype: bool
    """
    if force:
        return True
    if os.path.exists(filepath):
        return confirm_action(
            f'"{filepath}" already exists. Do you want to overwrite it?'
        )
    return True


def write_sample_config(configspec, progname):
    """
    Write a sample configuration file.

    :param configspec: Configuration specification file.
    :type configspec: str
    :param progname: Program name.
    :type progname: str
    """
    c = ConfigObj(configspec=configspec, default_encoding='utf8')
    val = Validator()
    c.validate(val)
    c.defaults = []
    c.initial_comment = configspec.initial_comment
    c.comments = configspec.comments
    configfile = f'{progname}.conf'
    if write_ok(configfile):
        with open(configfile, 'wb') as fp:
            c.write(fp)
        print(style(f'Sample config file written to: "{configfile}"', 'green'))


def read_config(config_file, configspec=None):
    """
    Read a configuration file.

    :param config_file: Configuration file.
    :type config_file: str
    :param configspec: Configuration specification file.
    :type configspec: str
    :return: Configuration object.
    :rtype: configobj.ConfigObj
    """
    kwargs = {
        'configspec': configspec,
        'file_error': True,
        'default_encoding': 'utf8'
    }
    if configspec is None:
        kwargs.update({
            'interpolation': False,
            'list_values': False,
            '_inspec': True
        })
    try:
        config_obj = ConfigObj(config_file, **kwargs)
    except IOError as err:
        err_exit(err)
    except ParseError as err:
        msg = f'Unable to read "{config_file}": {err}'
        err_exit(msg)
    return config_obj


def validate_config(config_obj):
    """
    Validate a configuration object.

    :param config_obj: Configuration object.
    :type config_obj: configobj.ConfigObj
    """
    val = Validator()
    test = config_obj.validate(val)
    if isinstance(test, dict):
        for entry in test:
            if not test[entry]:
                sys.stderr.write(
                    f'Invalid value for "{entry}": "{config_obj[entry]}"\n')
        sys.exit(1)
    if not test:
        err_exit('No configuration value present!')


def update_config_file(config_file, configspec):
    """
    Update a configuration file to the latest version.

    :param config_file: Configuration file.
    :type config_file: str
    :param configspec: Configuration specification file.
    :type configspec: str
    """
    config_obj = read_config(config_file, configspec)
    val = Validator()
    config_obj.validate(val)
    mod_time = datetime.fromtimestamp(os.path.getmtime(config_file))
    mod_time_str = mod_time.strftime('%Y%m%d_%H%M%S')
    config_file_old = f'{config_file}.{mod_time_str}'
    should_update = confirm_action(
        f'Ok to update {config_file}?\n'
        f'(Old file will be saved as {config_file_old})'
    )
    if not should_update:
        sys.exit(0)
    config_new = ConfigObj(configspec=configspec, default_encoding='utf8')
    config_new = read_config(None, configspec)
    config_new.validate(val)
    config_new.defaults = []
    config_new.comments = configspec.comments
    config_new.initial_comment = config_obj.initial_comment
    config_new.final_comment = configspec.final_comment
    for k, v in config_obj.items():
        if k not in config_new:
            continue
        # Fix for force_list(default=None)
        if v == ['None', ]:
            v = None
        config_new[k] = v
    migrate_options = {
        # 'old_option': 'new_option',
        'waveform_data_path': 'sds_data_path',
    }
    for old_opt, new_opt in migrate_options.items():
        if old_opt in config_obj and config_obj[old_opt] != 'None':
            config_new[new_opt] = config_obj[old_opt]
    shutil.copyfile(config_file, config_file_old)
    with open(config_file, 'wb') as fp:
        config_new.write(fp)
        print(style(f'{config_file}: updated', 'green'))


def manage_uncaught_exception(exception):
    """
    Manage an uncaught exception.

    :param exception: Exception object.
    :type exception: Exception
    """
    # pylint: disable=import-outside-toplevel
    from .. import __version__
    import traceback
    import numpy as np
    import scipy as sp
    import obspy
    import matplotlib
    import pygments
    from pygments.lexers.python import PythonLexer
    from pygments.formatters.terminal import TerminalFormatter
    tb_str = ''.join(
        traceback.format_exception(
            type(exception), exception, exception.__traceback__))
    colored_tb = pygments.highlight(tb_str, PythonLexer(), TerminalFormatter())
    bug_header = style(
        "Congratulations, you've found a bug in Requake!", 'bold', 'red'
    )
    report_header = style(
        'Include the following information in your report:', 'bold'
    )
    issues_url = 'https://github.com/SeismicSource/requake/issues'
    email = 'satriano@ipgp.fr'
    issues_link = hyperlink(issues_url, stream=sys.stderr)
    email_link = hyperlink(f'mailto:{email}', email, stream=sys.stderr)
    bug_message = frame(
        f'{bug_header} 🐞\n\n'
        f'Please report it on {issues_link}\n'
        f'or by email to {email_link}.',
        stream=sys.stderr,
    )
    sys.stderr.write(
        f'\n# BEGIN TRACEBACK {"#" * 62}\n'
        f'\n{colored_tb}'
        f'\n# END TRACEBACK {"#" * 62}\n\n'
        f'{bug_message}\n\n'
        f'{report_header}\n\n'
        f'  Requake version: {__version__}\n'
        f'  Python version: {sys.version}\n'
        f'  NumPy version: {np.__version__}\n'
        f'  SciPy version: {sp.__version__}\n'
        f'  ObsPy version: {obspy.__version__}\n'
        f'  Matplotlib version: {matplotlib.__version__}\n'
        f'  Platform: {sys.platform}\n'
        f'  Command line: {" ".join(sys.argv)}\n'
        f'  Error message: {str(exception)}\n'
        '\n'
        'Also, please copy and paste the traceback above in your report.\n\n'
        'Thank you for your help!\n\n'
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
#  Terminal progress utilities
# ---------------------------------------------------------------------------

_SPINNER_FRAMES = ('⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏')


def status(msg):
    """Print a progress message to stderr."""
    print(style(msg, 'dim', stream=sys.stderr), file=sys.stderr)
    sys.stderr.flush()


# Maximum time (in seconds) to wait for an aborted operation to stop, so
# that it can release its resources (e.g. close its database connection)
# before the process exits.
ABORT_JOIN_TIMEOUT_S = 5.0

_abort_requested = False


def request_abort(abort=True):
    """
    Request (or clear) a pending abort.

    Long-running operations poll this flag — including through a SQLite
    progress handler — and stop as soon as possible. Note that the flag
    is global: while it is set, every running database query is
    interrupted, so callers that abort a single operation must clear it
    once that operation has stopped (see :func:`abort_operation`).

    :param abort: whether an abort is requested
    :type abort: bool
    """
    global _abort_requested  # pylint: disable=global-statement
    _abort_requested = abort


def abort_requested():
    """
    Return True when an abort has been requested.

    :return: whether an abort is pending
    :rtype: bool
    """
    return _abort_requested


def abort_operation(thread):
    """
    Request the operation running in *thread* to stop and wait for it.

    Waiting gives the operation the chance to release its resources
    (e.g. close its database connection, so that no ``-wal``/``-shm``
    files are left behind). The abort request is cleared before
    returning, since the process might keep running (e.g. after a pager
    popup has been cancelled).

    :param thread: the thread running the operation to abort
    :type thread: threading.Thread
    """
    request_abort()
    thread.join(timeout=ABORT_JOIN_TIMEOUT_S)
    request_abort(False)


def _terminal_columns(stream=None):
    """
    Return the number of columns of the terminal running *stream*.

    :param stream: stream to query (defaults to ``sys.stderr``)
    :type stream: io.TextIOBase

    :return: number of columns, or None when it cannot be determined
    :rtype: int or None
    """
    stream = sys.stderr if stream is None else stream
    try:
        return os.get_terminal_size(stream.fileno()).columns
    except (AttributeError, ValueError, OSError):
        return None


def run_with_spinner(message, func):
    r"""Run *func* in a thread, showing a braille spinner on stderr.

    The spinner animates on a single line via ``\r``, truncating
    *message* to the width of the terminal: a wrapped line cannot be
    erased by a carriage return, so its frames would pile up on the
    screen.  When the operation completes the line is cleared.
    ``Ctrl+C`` is handled so the terminal is left in a clean state.

    Outside the main process (e.g. in parallel workers) *func* is
    simply run in place, to keep the terminal output of the workers
    clean.
    """
    if multiprocessing.current_process().name != 'MainProcess':
        return func()
    done = threading.Event()
    errors = [None]
    result = [None]

    def _target():
        try:
            result[0] = func()
        except Exception as exc:  # pylint: disable=broad-except
            errors[0] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    columns = _terminal_columns()
    # Keep the line one column short of the terminal width: a terminal
    # wrapping as soon as the last column is written would push the
    # following frames to a new line, where ``\r`` cannot erase them.
    if columns is not None and columns > 3:
        message = truncate_to_width(message, columns - 3)

    # Visible width of the spinner line: a braille frame (one column) plus
    # a space plus the message, whose ANSI styling adds no visible column.
    width = display_width(message) + 2
    i = 0
    try:
        while not done.wait(0.1):
            frame = style(_SPINNER_FRAMES[i % len(_SPINNER_FRAMES)],
                          'cyan', stream=sys.stderr)
            text = style(message, 'dim', stream=sys.stderr)
            print(f'\r{frame} {text}', file=sys.stderr, end='')
            sys.stderr.flush()
            i += 1
        # Clear the spinner line: erase as many columns as the widest line
        # printed, or part of it is left over when the next message is
        # shorter than this one.
        print('\r' + ' ' * width, file=sys.stderr, end='\r')
        sys.stderr.flush()
    except (KeyboardInterrupt, SystemExit):
        # Leave a clean line after the spinner and stop the running
        # operation, waiting for it to release its resources.
        abort_operation(thread)
        print(file=sys.stderr)
        sys.stderr.flush()
        raise

    if errors[0] is not None:
        raise errors[0]
    return result[0]
