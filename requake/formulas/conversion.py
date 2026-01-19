# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Function to convert data types.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""


def float_or_none(string):
    """
    Convert string to float, return None if conversion fails.

    :param string: Input string.
    :type string: str
    :return: Float value or None.
    :rtype: float or None
    """
    try:
        val = float(string)
    except (TypeError, ValueError):
        val = None
    return val


def int_or_none(string):
    """
    Convert string to int, return None if conversion fails.

    :param string: Input string.
    :type string: str
    :return: Integer value or None.
    :rtype: int or None
    """
    try:
        val = int(string)
    except (TypeError, ValueError):
        val = None
    return val


def field_match_score(field, field_list):
    """
    Return the length of the longest substring of field that matches any of
    the field names in field_list.

    :param field: field name
    :type field: str
    :param field_list: list of field names
    :type field_list: list of str

    :return: the length of the longest substring of field that matches any of
        the field names in field_list
    :rtype: int
    """
    # return a very high score for a perfect match
    if field.lower().strip() in field_list:
        return 999
    scores = [
        len(guess)
        for guess in field_list
        if guess in field.lower().strip()
    ]
    try:
        return max(scores)
    except ValueError:
        return 0


def guess_field_names(input_fields, field_guesses):
    """
    Guess the field names corresponding to origin time, latitude, longitude,
    depth, magnitude and magnitude type.

    :param input_fields: list of field names
    :type input_fields: list of str
    :param field_guesses: dictionary with field guesses in the form
        field_name: field_guesses_list. This dictionary is updated in place
        and the guessed field names (or None) are stored as values in place
        of the field_guesses_list.
    :type field_guesses: dict
    """
    for field in input_fields:
        scores = {
            field_name: field_match_score(field, field_guesses_list)
            for field_name, field_guesses_list in field_guesses.items()
        }
        best_guess = max(scores, key=scores.get)
        if scores[best_guess] > 0:
            field_guesses[best_guess] = field
    # change to None all fields that have not been guessed
    for field_name, guess in field_guesses.items():
        if not isinstance(guess, str):
            field_guesses[field_name] = None
