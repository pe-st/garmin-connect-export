#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File: gcexport.py
Original author: Kyle Krafka (https://github.com/kjkjava/)
Date: April 28, 2015
Fork author: Michael P (https://github.com/moderation/)
Date: February 21, 2016
Fork author: Peter Steiner (https://github.com/pe-st/)
Date: June 2017
Date: March 2020 - Python3 support by Thomas Th. (https://github.com/telemaxx/)

Description:    Use this script to export your fitness data from Garmin Connect.
                See README.md for more information, CHANGELOG.md for a history of the changes

Activity & event types:
    https://connect.garmin.com/modern/main/js/properties/event_types/event_types.properties
    https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties
"""

# Standard library imports
import argparse
import csv
import http.cookiejar
import io
import json
import logging
import os
import os.path
import re
import string
import sys
import unicodedata
import urllib.request
import zipfile
from datetime import datetime, timedelta, tzinfo
from getpass import getpass
from math import floor
from platform import python_version
from subprocess import call
from timeit import default_timer as timer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

# PyPI imports
import garth
from garth.exc import GarthException

# Local application/library specific imports
from filtering import read_exclude, update_download_stats

COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR), urllib.request.HTTPSHandler(debuglevel=0))

SCRIPT_VERSION = '4.5.0'

# This version here should correspond to what is written in CONTRIBUTING.md#python-3x-versions
MINIMUM_PYTHON_VERSION = (3, 10)

# this is almost the datetime format Garmin used in the activity-search-service
# JSON 'display' fields (Garmin didn't zero-pad the date and the hour, but %d and %H do)
ALMOST_RFC_1123 = "%a, %d %b %Y %H:%M"

# used by sanitize_filename()
VALID_FILENAME_CHARS = f'-_.() {string.ascii_letters}{string.digits}'

# map the numeric parentTypeId to its name for the CSV output
# this comes from https://connect.garmin.com/activity-service/activity/activityTypes
PARENT_TYPE_ID = {
    1: 'running',
    2: 'cycling',
    4: 'other',
    9: 'walking',
    17: 'any',
    26: 'swimming',
    29: 'fitness_equipment',
    144: 'diving',
    157: 'safety',
    165: 'winter_sports',
    206: 'team_sports',
    219: 'racket_sports',
    228: 'water_sports',
}

# typeId values using pace instead of speed
USES_PACE = {1, 3, 9}  # running, hiking, walking

HR_ZONES_EMPTY = [None, None, None, None, None]

# Maximum number of activities you can request at once.
# Used to be 100 and enforced by Garmin for older endpoints; for the current endpoint 'URL_GC_LIST'
# the limit is not known (I have less than 1000 activities and could get them all in one go)
LIMIT_MAXIMUM = 1000

MAX_TRIES = 3

CSV_TEMPLATE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "csv_header_default.properties")

GARMIN_BASE_URL = "https://connect.garmin.com"

# URLs for various services.
URL_GC_USER = f'{GARMIN_BASE_URL}/userprofile-service/socialProfile'
URL_GC_USERSTATS = f'{GARMIN_BASE_URL}/userstats-service/statistics/'
URL_GC_LIST = f'{GARMIN_BASE_URL}/activitylist-service/activities/search/activities?'
URL_GC_ACTIVITY = f'{GARMIN_BASE_URL}/activity-service/activity/'
URL_GC_DEVICE = f'{GARMIN_BASE_URL}/device-service/deviceservice/app-info/'
URL_GC_GEAR = f'{GARMIN_BASE_URL}/gear-service/gear/filterGear?activityId='
URL_GC_ACT_PROPS = f'{GARMIN_BASE_URL}/modern/main/js/properties/activity_types/activity_types.properties'
URL_GC_EVT_PROPS = f'{GARMIN_BASE_URL}/modern/main/js/properties/event_types/event_types.properties'
URL_GC_GPX_ACTIVITY = f'{GARMIN_BASE_URL}/download-service/export/gpx/activity/'
URL_GC_TCX_ACTIVITY = f'{GARMIN_BASE_URL}/download-service/export/tcx/activity/'
URL_GC_ORIGINAL_ACTIVITY = f'{GARMIN_BASE_URL}/download-service/files/activity/'


class GarminException(Exception):
    """Exception for problems with Garmin Connect (connection, data consistency etc)."""


def resolve_path(directory, subdir, time):
    """
    Replace time variables and returns changed path. Supported place holders are {YYYY} and {MM}
    :param directory: export root directory
    :param subdir: subdirectory, can have place holders.
    :param time: date-time-string
    :return: Updated dictionary string
    """
    ret = os.path.join(directory, subdir)
    if re.compile(".*{YYYY}.*").match(ret):
        ret = ret.replace("{YYYY}", time[0:4])
    if re.compile(".*{MM}.*").match(ret):
        ret = ret.replace("{MM}", time[5:7])

    return ret


def hhmmss_from_seconds(sec):
    """Helper function that converts seconds to HH:MM:SS time format."""
    if isinstance(sec, (float, int)):
        formatted_time = str(timedelta(seconds=int(sec))).zfill(8)
    else:
        formatted_time = "0.000"
    return formatted_time


def kmh_from_mps(mps):
    """Helper function that converts meters per second (mps) to km/h."""
    return str(mps * 3.6)


def sanitize_filename(name, max_length=0):
    """
    Remove or replace characters that are unsafe for filename
    """
    # inspired by https://stackoverflow.com/a/698714/3686
    cleaned_filename = unicodedata.normalize('NFKD', name) if name else ''
    stripped_filename = ''.join(c for c in cleaned_filename if c in VALID_FILENAME_CHARS).replace(' ', '_')
    return stripped_filename[:max_length] if max_length > 0 else stripped_filename


def write_to_file(filename, content, mode='w', file_time=None):
    """
    Helper function that persists content to a file.

    :param filename:     name of the file to write
    :param content:      content to write; can be 'bytes' or 'str'.
                         If it's 'bytes' and the mode 'w', it will be converted/decoded
    :param mode:         'w' or 'wb'
    :param file_time:    if given use as timestamp for the file written (in seconds since 1970-01-01)
    """
    if mode == 'w':
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        with io.open(filename, mode, encoding='utf-8') as text_file:
            text_file.write(content)
    elif mode == 'wb':
        with io.open(filename, 'wb') as binary_file:
            binary_file.write(content)
    else:
        raise ValueError('Unsupported file mode: ', mode)
    if file_time:
        os.utime(filename, (file_time, file_time))


def http_req(url, post=None, headers=None):
    """
    Helper function that makes the HTTP requests.

    :param url:          URL for the request
    :param post:         dictionary of POST parameters
    :param headers:      dictionary of headers
    :return: response body (type 'bytes')
    """
    request = Request(url)
    # Tell Garmin we're some supported browser.
    request.add_header(
        'User-Agent',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2816.0 Safari/537.36',
    )
    request.add_header('nk', 'NT')  # necessary since 2021-02-23 to avoid http error code 402
    request.add_header('authorization', str(garth.client.oauth2_token))
    request.add_header('di-backend', 'connectapi.garmin.com')
    if headers:
        for header_key, header_value in headers.items():
            request.add_header(header_key, header_value)
    if post:
        post = urlencode(post)  # Convert dictionary to POST parameter string.
        post = post.encode("utf-8")
    start_time = timer()
    try:
        response = OPENER.open(request, data=post)
    except HTTPError as ex:
        if hasattr(ex, 'code'):
            logging.error('Server couldn\'t fulfill the request, url %s, code %s, error: %s', url, ex.code, ex)
            logging.info('Headers returned:\n%s', ex.info())
        raise
    except URLError as ex:
        if hasattr(ex, 'reason'):
            logging.error('Failed to reach url %s, error: %s', url, ex)
        raise
    logging.debug('Got %s in %s s from %s', response.getcode(), timer() - start_time, url)
    logging.debug('Headers returned:\n%s', response.info())

    # N.B. urllib2 will follow any 302 redirects.
    # print(response.getcode())
    if response.getcode() == 204:
        # 204 = no content, e.g. for activities without GPS coordinates there is no GPX download.
        # Write an empty file to prevent redownloading it.
        logging.info('Got 204 for %s, returning empty response', url)
        return b''
    if response.getcode() != 200:
        raise GarminException(f'Bad return code ({response.getcode()}) for: {url}')

    return response.read()


def http_req_as_string(url, post=None, headers=None):
    """Helper function that makes the HTTP requests, returning a string instead of bytes."""
    return http_req(url, post, headers).decode()


# idea stolen from https://stackoverflow.com/a/31852401/3686
def load_properties(multiline, separator='=', comment_char='#', keys=None):
    """
    Read a multiline string of properties (key/value pair separated by *separator*) into a dict

    :param multiline:    input string of properties
    :param separator:    separator between key and value
    :param comment_char: lines starting with this char are considered comments, not key/value pairs
    :param keys:         list to append the keys to
    :return:
    """
    props = {}
    for line in multiline.splitlines():
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith(comment_char):
            key_value = stripped_line.split(separator)
            key = key_value[0].strip()
            value = separator.join(key_value[1:]).strip().strip('"')
            props[key] = value
            if keys is not None:
                keys.append(key)
    return props


def value_if_found_else_key(some_dict, key):
    """Lookup a value in some_dict and use the key itself as fallback"""
    return some_dict.get(key, key)


def present(element, act):
    """Return True if act[element] is valid and not None"""
    if not act:
        return False
    if element not in act:
        return False
    return act[element]


def absent_or_null(element, act):
    """Return False only if act[element] is valid and not None"""
    if not act:
        return True
    if element not in act:
        return True
    if act[element]:
        return False
    return True


def from_activities_or_detail(element, act, detail, detail_container):
    """Return detail[detail_container][element] if valid and act[element] (or None) otherwise"""
    if absent_or_null(detail_container, detail) or absent_or_null(element, detail[detail_container]):
        return None if absent_or_null(element, act) else act[element]
    return detail[detail_container][element]


def trunc6(some_float):
    """Return the given float as string formatted with six digit precision"""
    return f'{floor(some_float * 1000000) / 1000000:12.6f}'.lstrip()


# A class building tzinfo objects for fixed-offset time zones.
# (copied from https://docs.python.org/2/library/datetime.html)
class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset, name):
        super().__init__()
        self.__offset = timedelta(minutes=offset)
        self.__name = name

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return self.__name

    def dst(self, dt):
        return timedelta(0)


def offset_date_time(time_local, time_gmt):
    """
    Build an 'aware' datetime from two 'naive' datetime objects (that is timestamps
    as present in the activitylist-service.json), using the time difference as offset.
    """
    local_dt = datetime_from_iso(time_local)
    gmt_dt = datetime_from_iso(time_gmt)
    offset = local_dt - gmt_dt
    offset_tz = FixedOffset(offset.seconds // 60, "LCL")
    return local_dt.replace(tzinfo=offset_tz)


def datetime_from_iso(iso_date_time):
    """
    Call 'datetime.strptime' supporting different ISO time formats
    (with or without 'T' between date and time, with or without microseconds,
    but without offset)
    :param iso_date_time: timestamp string in ISO format
    :return: a 'naive` datetime
    """
    pattern = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?")
    match = pattern.match(iso_date_time)
    if not match:
        raise GarminException(f'Invalid ISO timestamp {iso_date_time}.')
    micros = match.group(3) if match.group(3) else ".0"
    iso_with_micros = f'{match.group(1)} {match.group(2)}{micros}'
    return datetime.strptime(iso_with_micros, "%Y-%m-%d %H:%M:%S.%f")


def epoch_seconds_from_summary(summary):
    """
    Determine the start time in epoch seconds (seconds since 1970-01-01)

    :param summary: summary dict
    :return: epoch seconds as integer
    """
    if present('beginTimestamp', summary):
        return summary['beginTimestamp'] // 1000
    if present('startTimeLocal', summary) and present('startTimeGMT', summary):
        date_time = offset_date_time(summary['startTimeLocal'], summary['startTimeGMT'])
        return int(date_time.timestamp())
    logging.info('No timestamp found in activity %s', summary['activityId'])
    return None


def pace_or_speed_raw(type_id, parent_type_id, mps):
    """Convert speed (m/s) to speed (km/h) or pace (min/km) depending on type and parent type"""
    kmh = 3.6 * mps
    if (type_id in USES_PACE) or (parent_type_id in USES_PACE):
        return 60 / kmh
    return kmh


def pace_or_speed_formatted(type_id, parent_type_id, mps):
    """
    Convert speed (m/s) to string: speed (km/h as x.x) or
    pace (min/km as MM:SS), depending on type and parent type
    """
    kmh = 3.6 * mps
    if (type_id in USES_PACE) or (parent_type_id in USES_PACE):
        # format seconds per kilometer as MM:SS, see https://stackoverflow.com/a/27751293
        div_mod = divmod(int(round(3600 / kmh)), 60)
        return f'{div_mod[0]:02d}:{div_mod[1]:02d}'
    return f'{round(kmh, 1):.1f}'


class CsvFilter:
    """Collects, filters and writes CSV."""

    def __init__(self, csv_file, csv_header_properties):
        self.__csv_file = csv_file
        with open(csv_header_properties, 'r', encoding='utf-8') as prop:
            csv_header_props = prop.read()
        self.__csv_columns = []
        self.__csv_headers = load_properties(csv_header_props, keys=self.__csv_columns)
        self.__csv_field_names = []
        for column in self.__csv_columns:
            self.__csv_field_names.append(self.__csv_headers[column])
        self.__writer = csv.DictWriter(self.__csv_file, fieldnames=self.__csv_field_names, quoting=csv.QUOTE_ALL)
        self.__current_row = {}

    def write_header(self):
        """Write the active column names as CSV header"""
        self.__writer.writeheader()

    def write_row(self):
        """Write the prepared CSV record"""
        self.__writer.writerow(self.__current_row)
        self.__current_row = {}

    def set_column(self, name, value):
        """
        Store a column value (if the column is active) into
        the record prepared for the next write_row call
        """
        if value and name in self.__csv_columns:
            self.__current_row[self.__csv_headers[name]] = value

    def is_column_active(self, name):
        """Return True if the column is present in the header template"""
        return name in self.__csv_columns


def parse_arguments(argv):
    """
    Setup the argument parser and parse the command line arguments.
    """
    current_date = datetime.now().strftime('%Y-%m-%d')
    activities_directory = f'./{current_date}_garmin_connect_export'

    parser = argparse.ArgumentParser(description='Garmin Connect Exporter')

    # fmt: off
    parser.add_argument('--version', action='version', version='%(prog)s ' + SCRIPT_VERSION,
        help='print version and exit')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
        help='increase output and log verbosity, save more intermediate files')
    parser.add_argument('--username',
        help='your Garmin Connect username or email address (otherwise, you will be prompted)')
    parser.add_argument('--password',
        help='your Garmin Connect password (otherwise, you will be prompted)')
    parser.add_argument('-c', '--count', default='1',
        help='number of recent activities to download, or \'all\' (default: 1)')
    parser.add_argument('-sd', '--start_date', default='',
        help='the start date to get activities from (inclusive). Format example: 2023-07-31')
    parser.add_argument('-ed', '--end_date', default='',
        help='the end date to get activities to (inclusive). Format example: 2023-07-31')
    parser.add_argument('-e', '--external',
        help='path to external program to pass CSV file too')
    parser.add_argument('-a', '--args',
        help='additional arguments to pass to external program')
    parser.add_argument('-f', '--format', choices=['gpx', 'tcx', 'original', 'json'], default='gpx',
        help="export format; can be 'gpx', 'tcx', 'original' or 'json' (default: 'gpx')")
    parser.add_argument('-d', '--directory', default=activities_directory,
        help='the directory to export to (default: \'./YYYY-MM-DD_garmin_connect_export\')')
    parser.add_argument('-s', '--subdir',
        help='the subdirectory for activity files (tcx, gpx etc.), supported placeholders are {YYYY} and {MM} (default: export directory)')
    parser.add_argument('-lp', '--logpath',
        help='the directory to store logfiles (default: same as for --directory)')
    parser.add_argument('-u', '--unzip', action='store_true',
        help='if downloading ZIP files (format: \'original\'), unzip the file and remove the ZIP file')
    parser.add_argument('-ot', '--originaltime', action='store_true',
        help='will set downloaded (and possibly unzipped) file time to the activity start time')
    parser.add_argument('--desc', type=int, nargs='?', const=0, default=None,
        help='append the activity\'s description to the file name of the download; limit size if number is given')
    parser.add_argument('-t', '--template', default=CSV_TEMPLATE,
        help='template file with desired columns for CSV output')
    parser.add_argument('-fp', '--fileprefix', action='count', default=0,
        help='set the local time as activity file name prefix')
    parser.add_argument('-sa', '--start_activity_no', type=int, default=1,
        help='give index for first activity to import, i.e. skipping the newest activities')
    parser.add_argument('-ex', '--exclude', metavar='FILE',
        help='JSON file with array of activity IDs to exclude from download. Format example: {"ids": ["6176888711"]}')
    parser.add_argument('-tf', '--type_filter',
        help='comma-separated list of activity type IDs to allow. Format example: 3,9')
    parser.add_argument('-ss', '--session', metavar='DIRECTORY',
        help='enable loading and storing SSO information from/to given directory')
    # fmt: on

    return parser.parse_args(argv[1:])


def login_to_garmin_connect(args):
    """
    Perform all HTTP requests to login to Garmin Connect.
    """
    garth_session_directory = args.session if args.session else None

    print('Authenticating...', end='')
    try:
        login_required = False

        # try to load data if a session directory is given
        if garth_session_directory:
            try:
                garth.resume(garth_session_directory)
            except GarthException as ex:
                logging.debug("Could not resume session, error: %s", ex)
                login_required = True
            except FileNotFoundError as ex:
                logging.debug("Could not resume session, (non-garth) error: %s", ex)
                login_required = True
            try:
                garth.client.username
            except GarthException as ex:
                logging.debug("Session expired, error: %s", ex)
                login_required = True
            except AssertionError as ex:
                logging.debug("Token not found, (non-garth) error: %s", ex)
                login_required = True
            logging.info("Authenticating using OAuth token from %s", garth_session_directory)
        else:
            login_required = True

        if login_required:
            username = args.username if args.username else input('Username: ')
            password = args.password if args.password else getpass()
            garth.login(username, password)

            # try to store data if a session directory was given
            if garth_session_directory:
                try:
                    garth.save(garth_session_directory)
                except GarthException as ex:
                    logging.warning("Unable to store session data to %s, error: %s", garth_session_directory, ex)

    except Exception as ex:
        raise GarminException(f'Authentication failure ({ex}). Did you enter correct credentials?') from ex
    print(' Done.')


def csv_write_record(csv_filter, extract, actvty, details, activity_type_name, event_type_name):
    """
    Write out the given data for one activity as a CSV record

    :param csv_filter:         object encapsulating CSV file access
    :param extract:            dict with fields not found in 'actvty' or 'details'
    :param actvty:             dict for the given activity from the activities list endpoint
    :param details:            dict for the given activity from the individual activity endpoint
    :param activity_type_name: lookup table for activity type descriptions
    :param event_type_name:    lookup table for event type descriptions
    """

    type_id = 4 if absent_or_null('activityType', actvty) else actvty['activityType']['typeId']
    parent_type_id = 4 if absent_or_null('activityType', actvty) else actvty['activityType']['parentTypeId']
    if present(parent_type_id, PARENT_TYPE_ID):
        parent_type_key = PARENT_TYPE_ID[parent_type_id]
    else:
        parent_type_key = None
        logging.warning("Unknown parentType %s in %s, please tell script author", str(parent_type_id), str(actvty['activityId']))

    # get some values from detail if present, from actvty otherwise
    start_latitude = from_activities_or_detail('startLatitude', actvty, details, 'summaryDTO')
    start_longitude = from_activities_or_detail('startLongitude', actvty, details, 'summaryDTO')
    end_latitude = from_activities_or_detail('endLatitude', actvty, details, 'summaryDTO')
    end_longitude = from_activities_or_detail('endLongitude', actvty, details, 'summaryDTO')

    # fmt: off
    csv_filter.set_column('id', str(actvty['activityId']))
    csv_filter.set_column('url', f'{GARMIN_BASE_URL}/modern/activity/' + str(actvty['activityId']))
    csv_filter.set_column('activityName', actvty['activityName'] if present('activityName', actvty) else None)
    csv_filter.set_column('description', actvty['description'] if present('description', actvty) else None)
    csv_filter.set_column('startTimeIso', extract['start_time_with_offset'].isoformat())
    csv_filter.set_column('startTime1123', extract['start_time_with_offset'].strftime(ALMOST_RFC_1123))
    csv_filter.set_column('startTimeMillis', str(actvty['beginTimestamp']) if present('beginTimestamp', actvty) else None)
    csv_filter.set_column('startTimeRaw', details['summaryDTO']['startTimeLocal'] if present('startTimeLocal', details['summaryDTO']) else None)
    csv_filter.set_column('endTimeIso', extract['end_time_with_offset'].isoformat() if extract['end_time_with_offset'] else None)
    csv_filter.set_column('endTime1123', extract['end_time_with_offset'].strftime(ALMOST_RFC_1123) if extract['end_time_with_offset'] else None)
    csv_filter.set_column('endTimeMillis', str(actvty['beginTimestamp'] + extract['elapsed_seconds'] * 1000) if present('beginTimestamp', actvty) else None)
    csv_filter.set_column('durationRaw', str(round(actvty['duration'], 3)) if present('duration', actvty) else None)
    csv_filter.set_column('duration', hhmmss_from_seconds(round(actvty['duration'])) if present('duration', actvty) else None)
    csv_filter.set_column('elapsedDurationRaw', str(round(extract['elapsed_duration'], 3)) if extract['elapsed_duration'] else None)
    csv_filter.set_column('elapsedDuration', hhmmss_from_seconds(round(extract['elapsed_duration'])) if extract['elapsed_duration'] else None)
    csv_filter.set_column('movingDurationRaw', str(round(details['summaryDTO']['movingDuration'], 3)) if present('movingDuration', details['summaryDTO']) else None)
    csv_filter.set_column('movingDuration', hhmmss_from_seconds(round(details['summaryDTO']['movingDuration'])) if present('movingDuration', details['summaryDTO']) else None)
    csv_filter.set_column('distanceRaw', f"{actvty['distance'] / 1000:.5f}" if present('distance', actvty) else None)
    csv_filter.set_column('averageSpeedRaw', kmh_from_mps(details['summaryDTO']['averageSpeed']) if present('averageSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('averageSpeedPaceRaw', trunc6(pace_or_speed_raw(type_id, parent_type_id, actvty['averageSpeed'])) if present('averageSpeed', actvty) else None)
    csv_filter.set_column('averageSpeedPace', pace_or_speed_formatted(type_id, parent_type_id, actvty['averageSpeed']) if present('averageSpeed', actvty) else None)
    csv_filter.set_column('averageMovingSpeedRaw', kmh_from_mps(details['summaryDTO']['averageMovingSpeed']) if present('averageMovingSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('averageMovingSpeedPaceRaw', trunc6(pace_or_speed_raw(type_id, parent_type_id, details['summaryDTO']['averageMovingSpeed'])) if present('averageMovingSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('averageMovingSpeedPace', pace_or_speed_formatted(type_id, parent_type_id, details['summaryDTO']['averageMovingSpeed']) if present('averageMovingSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('maxSpeedRaw', kmh_from_mps(details['summaryDTO']['maxSpeed']) if present('maxSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('maxSpeedPaceRaw', trunc6(pace_or_speed_raw(type_id, parent_type_id, details['summaryDTO']['maxSpeed'])) if present('maxSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('maxSpeedPace', pace_or_speed_formatted(type_id, parent_type_id, details['summaryDTO']['maxSpeed']) if present('maxSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLoss', str(round(details['summaryDTO']['elevationLoss'], 2)) if present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLossUncorr', str(round(details['summaryDTO']['elevationLoss'], 2)) if absent_or_null('elevationCorrected', actvty) and present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLossCorr', str(round(details['summaryDTO']['elevationLoss'], 2)) if present('elevationCorrected', actvty) and present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGain', str(round(details['summaryDTO']['elevationGain'], 2)) if present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGainUncorr', str(round(details['summaryDTO']['elevationGain'], 2)) if absent_or_null('elevationCorrected', actvty) and present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGainCorr', str(round(details['summaryDTO']['elevationGain'], 2)) if present('elevationCorrected', actvty) and present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('minElevation', str(round(details['summaryDTO']['minElevation'], 2)) if present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('minElevationUncorr', str(round(details['summaryDTO']['minElevation'], 2)) if absent_or_null('elevationCorrected', actvty) and present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('minElevationCorr', str(round(details['summaryDTO']['minElevation'], 2)) if present('elevationCorrected', actvty) and present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevation', str(round(details['summaryDTO']['maxElevation'], 2)) if present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevationUncorr', str(round(details['summaryDTO']['maxElevation'], 2)) if absent_or_null('elevationCorrected', actvty) and present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevationCorr', str(round(details['summaryDTO']['maxElevation'], 2)) if present('elevationCorrected', actvty) and present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('elevationCorrected', 'true' if present('elevationCorrected', actvty) else 'false')
    # csv_record += empty_record  # no minimum heart rate in JSON
    csv_filter.set_column('maxHRRaw', str(details['summaryDTO']['maxHR']) if present('maxHR', details['summaryDTO']) else None)
    csv_filter.set_column('maxHR', f"{actvty['maxHR']:.0f}" if present('maxHR', actvty) else None)
    csv_filter.set_column('averageHRRaw', str(details['summaryDTO']['averageHR']) if present('averageHR', details['summaryDTO']) else None)
    csv_filter.set_column('averageHR', f"{actvty['averageHR']:.0f}" if present('averageHR', actvty) else None)
    csv_filter.set_column('caloriesRaw', str(details['summaryDTO']['calories']) if present('calories', details['summaryDTO']) else None)
    csv_filter.set_column('calories', f"{details['summaryDTO']['calories']:.0f}" if present('calories', details['summaryDTO']) else None)
    csv_filter.set_column('vo2max', str(actvty['vO2MaxValue']) if present('vO2MaxValue', actvty) else None)
    csv_filter.set_column('aerobicEffect', str(round(details['summaryDTO']['trainingEffect'], 2)) if present('trainingEffect', details['summaryDTO']) else None)
    csv_filter.set_column('anaerobicEffect', str(round(details['summaryDTO']['anaerobicTrainingEffect'], 2)) if present('anaerobicTrainingEffect', details['summaryDTO']) else None)
    csv_filter.set_column('hrZone1Low', str(extract['hrZones'][0]['zoneLowBoundary']) if present('zoneLowBoundary', extract['hrZones'][0]) else None)
    csv_filter.set_column('hrZone1Seconds', f"{extract['hrZones'][0]['secsInZone']:.0f}" if present('secsInZone', extract['hrZones'][0]) else None)
    csv_filter.set_column('hrZone2Low', str(extract['hrZones'][1]['zoneLowBoundary']) if present('zoneLowBoundary', extract['hrZones'][1]) else None)
    csv_filter.set_column('hrZone2Seconds', f"{extract['hrZones'][1]['secsInZone']:.0f}" if present('secsInZone', extract['hrZones'][1]) else None)
    csv_filter.set_column('hrZone3Low', str(extract['hrZones'][2]['zoneLowBoundary']) if present('zoneLowBoundary', extract['hrZones'][2]) else None)
    csv_filter.set_column('hrZone3Seconds', f"{extract['hrZones'][2]['secsInZone']:.0f}" if present('secsInZone', extract['hrZones'][2]) else None)
    csv_filter.set_column('hrZone4Low', str(extract['hrZones'][3]['zoneLowBoundary']) if present('zoneLowBoundary', extract['hrZones'][3]) else None)
    csv_filter.set_column('hrZone4Seconds', f"{extract['hrZones'][3]['secsInZone']:.0f}" if present('secsInZone', extract['hrZones'][3]) else None)
    csv_filter.set_column('hrZone5Low', str(extract['hrZones'][4]['zoneLowBoundary']) if present('zoneLowBoundary', extract['hrZones'][4]) else None)
    csv_filter.set_column('hrZone5Seconds', f"{extract['hrZones'][4]['secsInZone']:.0f}" if present('secsInZone', extract['hrZones'][4]) else None)
    csv_filter.set_column('averageRunCadence', str(round(details['summaryDTO']['averageRunCadence'], 2)) if present('averageRunCadence', details['summaryDTO']) else None)
    csv_filter.set_column('maxRunCadence', str(details['summaryDTO']['maxRunCadence']) if present('maxRunCadence', details['summaryDTO']) else None)
    csv_filter.set_column('strideLength', str(round(details['summaryDTO']['strideLength'], 2)) if present('strideLength', details['summaryDTO']) else None)
    csv_filter.set_column('steps', str(actvty['steps']) if present('steps', actvty) else None)
    csv_filter.set_column('averageCadence', str(actvty['averageBikingCadenceInRevPerMinute']) if present('averageBikingCadenceInRevPerMinute', actvty) else None)
    csv_filter.set_column('maxCadence', str(actvty['maxBikingCadenceInRevPerMinute']) if present('maxBikingCadenceInRevPerMinute', actvty) else None)
    csv_filter.set_column('strokes', str(actvty['strokes']) if present('strokes', actvty) else None)
    csv_filter.set_column('averageTemperature', str(details['summaryDTO']['averageTemperature']) if present('averageTemperature', details['summaryDTO']) else None)
    csv_filter.set_column('minTemperature', str(details['summaryDTO']['minTemperature']) if present('minTemperature', details['summaryDTO']) else None)
    csv_filter.set_column('maxTemperature', str(details['summaryDTO']['maxTemperature']) if present('maxTemperature', details['summaryDTO']) else None)
    csv_filter.set_column('device', extract['device'] if extract['device'] else None)
    csv_filter.set_column('gear', extract['gear'] if extract['gear'] else None)
    csv_filter.set_column('activityTypeKey', actvty['activityType']['typeKey'].title() if present('typeKey', actvty['activityType']) else None)
    csv_filter.set_column('activityType', value_if_found_else_key(activity_type_name, 'activity_type_' + actvty['activityType']['typeKey']) if present('activityType', actvty) else None)
    csv_filter.set_column('activityParent', value_if_found_else_key(activity_type_name, 'activity_type_' + parent_type_key) if parent_type_key else None)
    csv_filter.set_column('eventTypeKey', actvty['eventType']['typeKey'].title() if present('typeKey', actvty['eventType']) else None)
    csv_filter.set_column('eventType', value_if_found_else_key(event_type_name, actvty['eventType']['typeKey']) if present('eventType', actvty) else None)
    csv_filter.set_column('privacy', details['accessControlRuleDTO']['typeKey'] if present('typeKey', details['accessControlRuleDTO']) else None)
    csv_filter.set_column('fileFormat', details['metadataDTO']['fileFormat']['formatKey'] if present('fileFormat', details['metadataDTO']) and present('formatKey', details['metadataDTO']['fileFormat']) else None)
    csv_filter.set_column('tz', details['timeZoneUnitDTO']['timeZone'] if present('timeZone', details['timeZoneUnitDTO']) else None)
    csv_filter.set_column('tzOffset', extract['start_time_with_offset'].isoformat()[-6:])
    csv_filter.set_column('locationName', details['locationName'] if present('locationName', details) else None)
    csv_filter.set_column('startLatitudeRaw', str(start_latitude) if start_latitude else None)
    csv_filter.set_column('startLatitude', trunc6(start_latitude) if start_latitude else None)
    csv_filter.set_column('startLongitudeRaw', str(start_longitude) if start_longitude else None)
    csv_filter.set_column('startLongitude', trunc6(start_longitude) if start_longitude else None)
    csv_filter.set_column('endLatitudeRaw', str(end_latitude) if end_latitude else None)
    csv_filter.set_column('endLatitude', trunc6(end_latitude) if end_latitude else None)
    csv_filter.set_column('endLongitudeRaw', str(end_longitude) if end_longitude else None)
    csv_filter.set_column('endLongitude', trunc6(end_longitude) if end_longitude else None)
    csv_filter.set_column('sampleCount', str(extract['samples']['metricsCount']) if present('metricsCount', extract['samples']) else None)
    # fmt: on

    csv_filter.write_row()


def extract_device(device_dict, details, start_time_seconds, args, http_caller, file_writer):
    """
    Try to get the device details (and cache them, as they're used for multiple activities)

    :param device_dict:        cache (dict) of already known devices
    :param details:            dict with the details of an activity, should contain a device ID
    :param start_time_seconds: if given use as timestamp for the file written (in seconds since 1970-01-01)
    :param args:               command-line arguments (for the file_writer callback)
    :param http_caller:        callback to perform the HTTP call for downloading the device details
    :param file_writer:        callback that saves the device details in a file
    :return: string with the device name
    """
    if not present('metadataDTO', details):
        logging.warning("no metadataDTO")
        return None

    metadata = details['metadataDTO']
    device_app_inst_id = (
        metadata['deviceApplicationInstallationId'] if present('deviceApplicationInstallationId', metadata) else None
    )
    if device_app_inst_id:
        if device_app_inst_id not in device_dict:
            # observed from my stock of activities:
            # details['metadataDTO']['deviceMetaDataDTO']['deviceId'] == null -> device unknown
            # details['metadataDTO']['deviceMetaDataDTO']['deviceId'] == '0' -> device unknown
            # details['metadataDTO']['deviceMetaDataDTO']['deviceId'] == 'someid' -> device known
            device_dict[device_app_inst_id] = None
            device_meta = metadata['deviceMetaDataDTO'] if present('deviceMetaDataDTO', metadata) else {}
            device_id = device_meta['deviceId'] if present('deviceId', device_meta) else None
            if 'deviceId' not in device_meta or device_id and device_id != '0':
                device_json = http_caller(URL_GC_DEVICE + str(device_app_inst_id))
                file_writer(os.path.join(args.directory, f'device_{device_app_inst_id}.json'), device_json, 'w', start_time_seconds)
                if not device_json:
                    logging.warning("Device Details %s are empty", device_app_inst_id)
                    device_dict[device_app_inst_id] = "device-id:" + str(device_app_inst_id)
                else:
                    device_details = json.loads(device_json)
                    if present('productDisplayName', device_details):
                        device_dict[device_app_inst_id] = (
                            device_details['productDisplayName'] + ' ' + device_details['versionString']
                        )
                    else:
                        logging.warning("Device details %s incomplete", device_app_inst_id)
        return device_dict[device_app_inst_id]
    return None


def load_zones(activity_id, start_time_seconds, args, http_caller, file_writer):
    """
    Try to get the heart rate zones

    :param activity_id:        ID of the activity (as string)
    :param start_time_seconds: if given use as timestamp for the file written (in seconds since 1970-01-01)
    :param args:               command-line arguments (for the file_writer callback)
    :param http_caller:        callback to perform the HTTP call for downloading the device details
    :param file_writer:        callback that saves the device details in a file
    :return: array with the heart rate zones
    """
    zones = HR_ZONES_EMPTY
    zones_json = http_caller(f'{URL_GC_ACTIVITY}{activity_id}/hrTimeInZones')
    file_writer(os.path.join(args.directory, f'activity_{activity_id}_zones.json'), zones_json, 'w', start_time_seconds)
    zones_raw = json.loads(zones_json)
    if not zones_raw:
        logging.warning("HR Zones %s are empty", activity_id)
    else:
        for raw_zone in zones_raw:
            if present('zoneNumber', raw_zone):
                index = raw_zone['zoneNumber'] - 1
                zones[index] = {}
                zones[index]['secsInZone'] = raw_zone['secsInZone']
                zones[index]['zoneLowBoundary'] = raw_zone['zoneLowBoundary']
    return zones


def load_gear(activity_id, args):
    """Retrieve the gear/equipment for an activity"""
    try:
        gear_json = http_req_as_string(URL_GC_GEAR + activity_id)
        gear = json.loads(gear_json)
        if gear:
            if args.verbosity > 0:
                write_to_file(os.path.join(args.directory, f'activity_{activity_id}-gear.json'), gear_json, 'w')
            gear_display_name = gear[0]['displayName'] if present('displayName', gear[0]) else None
            gear_model = gear[0]['customMakeModel'] if present('customMakeModel', gear[0]) else None
            logging.debug("Gear for %s = %s/%s", activity_id, gear_display_name, gear_model)
            return gear_display_name if gear_display_name else gear_model
        return None
    except HTTPError as ex:
        logging.info("Unable to get gear for %d, error: %s", activity_id, ex)
        # logging.exception(ex)
        return None


def export_data_file(activity_id, activity_details, args, file_time, append_desc, date_time):
    """
    Write the data of the activity to a file, depending on the chosen data format

    The default filename is 'activity_' + activity_id, but this can be modified
    by the '--fileprefix' option and the 'append_desc' parameter; the directory
    to write the file into can be modified by the '--subdir' option.

    :param activity_id:      ID of the activity (as string)
    :param activity_details: details of the activity (for format 'json')
    :param args:             command-line arguments
    :param file_time:        if given the desired time stamp for the activity file (in seconds since 1970-01-01)
    :param append_desc:      suffix to the default filename
    :param date_time:        datetime in ISO format used for '--fileprefix' and '--subdir' options
    :return:                 True if the file was written, False if the file existed already
    """
    # Time dependent subdirectory for activity files, e.g. '{YYYY}'
    if args.subdir is not None:
        directory = resolve_path(args.directory, args.subdir, date_time)
    # export activities to root directory
    else:
        directory = args.directory

    if not os.path.isdir(directory):
        os.makedirs(directory)

    # timestamp as prefix for filename
    if args.fileprefix > 0:
        prefix = f'{date_time.replace("-", "").replace(":", "").replace(" ", "-")}-'
    else:
        prefix = ""

    original_basename = None
    if args.format == 'gpx':
        data_filename = os.path.join(directory, f'{prefix}activity_{activity_id}{append_desc}.gpx')
        download_url = f'{URL_GC_GPX_ACTIVITY}{activity_id}?full=true'
        file_mode = 'w'
    elif args.format == 'tcx':
        data_filename = os.path.join(directory, f'{prefix}activity_{activity_id}{append_desc}.tcx')
        download_url = f'{URL_GC_TCX_ACTIVITY}{activity_id}?full=true'
        file_mode = 'w'
    elif args.format == 'original':
        data_filename = os.path.join(directory, f'{prefix}activity_{activity_id}{append_desc}.zip')
        # not all 'original' files are in FIT format, some are GPX or TCX...
        original_basename = os.path.join(directory, f'{prefix}activity_{activity_id}{append_desc}')
        download_url = URL_GC_ORIGINAL_ACTIVITY + activity_id
        file_mode = 'wb'
    elif args.format == 'json':
        data_filename = os.path.join(directory, f'{prefix}activity_{activity_id}{append_desc}.json')
        download_url = None
        file_mode = 'w'
    else:
        raise ValueError('Unrecognized format.')

    if os.path.isfile(data_filename):
        logging.debug('Data file for %s already exists', activity_id)
        print('\tData file already exists; skipping...')
        # Inform the main program that the file already exists
        return False

    # Regardless of unzip setting, don't redownload if the ZIP or FIT/GPX/TCX original file exists.
    if args.format == 'original' and (
        os.path.isfile(original_basename + '.fit')
        or os.path.isfile(original_basename + '.gpx')
        or os.path.isfile(original_basename + '.tcx')
    ):
        logging.debug('Original data file for %s already exists', activity_id)
        print('\tOriginal data file already exists; skipping...')
        # Inform the main program that the file already exists
        return False

    if args.format != 'json':
        # Download the data file from Garmin Connect. If the download fails (e.g., due to timeout),
        # this script will die, but nothing will have been written to disk about this activity, so
        # just running it again should pick up where it left off.

        try:
            data = http_req(download_url)
        except HTTPError as ex:
            # Handle expected (though unfortunate) error codes; die on unexpected ones.
            if ex.code == 500 and args.format == 'tcx':
                # Garmin will give an internal server error (HTTP 500) when downloading TCX files
                # if the original was a manual GPX upload. Writing an empty file prevents this file
                # from being redownloaded, similar to the way GPX files are saved even when there
                # are no tracks. One could be generated here, but that's a bit much. Use the GPX
                # format if you want actual data in every file, as I believe Garmin provides a GPX
                # file for every activity.
                logging.info('Writing empty file since Garmin did not generate a TCX file for this activity...')
                data = ''
            elif ex.code == 404 and args.format == 'original':
                # For manual activities (i.e., entered in online without a file upload), there is
                # no original file. # Write an empty file to prevent redownloading it.
                logging.info('Writing empty file since there was no original activity data...')
                data = ''
            else:
                logging.info('Got %s for %s', ex.code, download_url)
                raise GarminException(f'Failed. Got an HTTP error {ex.code} for {download_url}') from ex
    else:
        data = activity_details

    # Persist file
    write_to_file(data_filename, data, file_mode, file_time)

    # Success: Add activity ID to downloaded_ids.json
    update_download_stats(activity_id, args.directory)

    if args.format == 'original':
        # Even manual upload of a GPX file is zipped, but we'll validate the extension.
        if args.unzip and data_filename[-3:].lower() == 'zip':
            logging.debug('Unzipping and removing original file, size is %s', os.stat(data_filename).st_size)
            if os.stat(data_filename).st_size > 0:
                with open(data_filename, 'rb') as zip_file, zipfile.ZipFile(zip_file) as zip_obj:
                    for name in zip_obj.namelist():
                        unzipped_name = zip_obj.extract(name, directory)
                        # prepend 'activity_' and append the description to the base name
                        name_base, name_ext = os.path.splitext(name)
                        # sometimes in 2020 Garmin added '_ACTIVITY' to the name in the ZIP. Remove it...
                        # note that 'new_name' should match 'original_basename' elsewhere in this script to
                        # avoid downloading the same files again
                        name_base = name_base.replace('_ACTIVITY', '')
                        new_name = os.path.join(directory, f'{prefix}activity_{name_base}{append_desc}{name_ext}')
                        logging.debug('renaming %s to %s', unzipped_name, new_name)
                        os.rename(unzipped_name, new_name)
                        if file_time:
                            os.utime(new_name, (file_time, file_time))
            else:
                print('\tSkipping 0Kb zip file.')
            os.remove(data_filename)

    # Inform the main program that the file is new
    return True


def setup_logging(args):
    """Setup logging"""
    logpath = args.logpath if args.logpath else args.directory
    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    logging.basicConfig(
        filename=os.path.join(logpath, 'gcexport.log'), level=logging.DEBUG, format='%(asctime)s [%(levelname)-7.7s] %(message)s'
    )

    # set up logging to console
    console = logging.StreamHandler()
    console.setLevel(logging.WARN)
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)


def logging_verbosity(verbosity):
    """Adapt logging verbosity, separately for logfile and console output"""
    logger = logging.getLogger()
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            # this is the logfile handler
            level = logging.DEBUG if verbosity > 0 else logging.INFO
            handler.setLevel(level)
            logging.info('New logfile level: %s', logging.getLevelName(level))
        elif isinstance(handler, logging.StreamHandler):
            # this is the console handler
            level = logging.DEBUG if verbosity > 1 else (logging.INFO if verbosity > 0 else logging.WARN)
            handler.setLevel(level)
            logging.debug('New console log level: %s', logging.getLevelName(level))


def fetch_userstats(args):
    """
    Http request for getting user statistic like total number of activities. The json will be saved as file
    'userstats.json'
    :param args:    command-line arguments (for args.directory etc)
    :return:        json with user statistics
    """
    print('Getting display name...', end='')
    logging.info('Profile page %s', URL_GC_USER)
    profile_page = http_req_as_string(URL_GC_USER)
    if args.verbosity > 0:
        write_to_file(os.path.join(args.directory, 'user.json'), profile_page, 'w')

    display_name = json.loads(profile_page)['displayName']
    print(' Done. displayName=', display_name, sep='')

    print('Fetching user stats...', end='')
    logging.info('Userstats page %s', URL_GC_USERSTATS + display_name)
    result = http_req_as_string(URL_GC_USERSTATS + display_name)
    print(' Done.')

    # Persist JSON
    write_to_file(os.path.join(args.directory, 'userstats.json'), result, 'w')

    return json.loads(result)


def fetch_activity_list(args, total_to_download):
    """
    Fetch the first 'total_to_download' activity summaries; as a side effect save them in json format.
    :param args:              command-line arguments (for args.directory etc)
    :param total_to_download: number of activities to download
    :return:                  List of activity summaries
    """

    # This while loop will download data from the server in multiple chunks, if necessary.
    activities = []

    total_downloaded = 0
    while total_downloaded < total_to_download:
        # Maximum chunk size 'LIMIT_MAXIMUM' ... 400 return status if over maximum.  So download
        # maximum or whatever remains if less than maximum.
        # As of 2018-03-06 I get return status 500 if over maximum
        if total_to_download - total_downloaded > LIMIT_MAXIMUM:
            num_to_download = LIMIT_MAXIMUM
        else:
            num_to_download = total_to_download - total_downloaded

        chunk = fetch_activity_chunk(args, num_to_download, total_downloaded)
        activities.extend(chunk)
        total_downloaded += num_to_download

    # it seems that parent multisport activities are not counted in userstats
    if len(activities) != total_to_download:
        logging.info('Expected %s activities, got %s.', total_to_download, len(activities))
    return activities


def annotate_activity_list(activities, start, exclude_list, type_filter):
    """
    Creates an action list with a tuple per activity summary

    The tuple per activity contains three values:
    - index:    the index of the activity summary in the activities argument
                (the first gets index 0, the second index 1 etc)
    - activity  the activity summary from the activites argument
    - action    the action to take for this activity (d=download, s=skip, e=exclude)

    :param activities:    List of activity summaries
    :param start:         One-based index of the first non-skipped activity
                          (i.e. with 1 no activity gets skipped, with 2 the first activity gets skipped etc)
    :param exclude_list:  List of activity ids that have to be skipped explicitly
    :param type_filter:   list of activity types to include in the output
    :return:              List of action tuples
    """

    action_list = []
    for index, activity in enumerate(activities):
        if index < (start - 1):
            action = 's'
        elif str(activity['activityId']) in exclude_list:
            action = 'e'
        else:
            activity_type = activity['activityType']
            if (
                type_filter is not None
                and str(activity_type['typeId']) not in type_filter
                and activity_type['typeKey'] not in type_filter
            ):
                action = 'f'
            else:
                action = 'd'

        action_list.append({"index": index, "action": action, "activity": activity})

    return action_list


def fetch_activity_chunk(args, num_to_download, total_downloaded):
    """
    Fetch a chunk of activity summaries; as a side effect save them in json format.
    :param args:              command-line arguments (for args.directory etc)
    :param num_to_download:   number of summaries to download in this chunk
    :param total_downloaded:  number of already downloaded summaries in previous chunks
    :return:                  List of activity summaries
    """

    search_params = {'start': total_downloaded, 'limit': num_to_download}
    if args.start_date != "":
        search_params['startDate'] = args.start_date
    if args.end_date != "":
        search_params['endDate'] = args.end_date

    # Query Garmin Connect
    print('Querying list of activities ', total_downloaded + 1, '..', total_downloaded + num_to_download, '...', sep='', end='')
    logging.info('Activity list URL %s', URL_GC_LIST + urlencode(search_params))
    result = http_req_as_string(URL_GC_LIST + urlencode(search_params))
    print(' Done.')

    # Persist JSON activities list
    current_index = total_downloaded + 1
    activities_list_filename = f'activities-{current_index}-{total_downloaded+num_to_download}.json'
    write_to_file(os.path.join(args.directory, activities_list_filename), result, 'w')
    activity_summaries = json.loads(result)
    fetch_multisports(activity_summaries, http_req_as_string, args)
    return activity_summaries


def fetch_multisports(activity_summaries, http_caller, args):
    """
    Search 'activity_summaries' for multisport activities and then
    fetch the information for the activity parts (child activities)
    and insert them into the 'activity_summaries' just after the multisport
    activity
    :param activity_summaries: list of activity summaries, will be modified in-place
    :param http_caller:        callback to perform the HTTP call for downloading the activity details
    :param args:               command-line arguments (for args.directory etc)
    """
    for idx, child_summary in enumerate(activity_summaries):
        type_key = None if absent_or_null('activityType', child_summary) else child_summary['activityType']['typeKey']
        if type_key == 'multi_sport':
            _, details = fetch_details(child_summary['activityId'], http_caller)

            child_ids = (
                details['metadataDTO']['childIds'] if 'metadataDTO' in details and 'childIds' in details['metadataDTO'] else None
            )
            # insert the children in reversed order always at the same index to get
            # the correct order in activity_summaries
            for child_id in reversed(child_ids):
                child_string, child_details = fetch_details(child_id, http_caller)
                if args.verbosity > 0:
                    write_to_file(os.path.join(args.directory, f'child_{child_id}.json'), child_string, 'w')
                child_summary = {}
                copy_details_to_summary(child_summary, child_details)
                activity_summaries.insert(idx + 1, child_summary)


def fetch_details(activity_id, http_caller):
    """
    Try to get the activity details for an activity

    :param activity_id:  id of the activity to fetch
    :param http_caller:  callback to perform the HTTP call for downloading the activity details
    :return details_as_string, details_as_json_dict:
    """
    activity_details = None
    details = None
    tries = MAX_TRIES
    while tries > 0:
        activity_details = http_caller(f'{URL_GC_ACTIVITY}{activity_id}')
        details = json.loads(activity_details)
        # I observed a failure to get a complete JSON detail in about 5-10 calls out of 1000
        # retrying then statistically gets a better JSON ;-)
        if details['summaryDTO']:
            tries = 0
        else:
            logging.info("Retrying activity details download %s", URL_GC_ACTIVITY + str(activity_id))
            tries -= 1
            if tries == 0:
                raise GarminException(f'Didn\'t get "summaryDTO" after {MAX_TRIES} tries for {activity_id}')
    return activity_details, details


def copy_details_to_summary(summary, details):
    """
    Add some activity properties from the 'details' dict to the 'summary' dict

    The choice of which properties are copied is determined by the properties
    used by the 'csv_write_record' method.

    This particularly useful for children of multisport activities, as I don't
    know how to get these activity summaries otherwise
    :param summary: summary dict, will be modified in-place
    :param details: details dict
    """
    # fmt: off
    summary['activityId'] = details['activityId']
    summary['activityName'] = details['activityName']
    summary['description'] = details['description'] if present('description', details) else None
    summary['activityType'] = {}
    summary['activityType']['typeId'] = details['activityTypeDTO']['typeId'] if 'activityTypeDTO' in details and present('typeId', details['activityTypeDTO']) else None
    summary['activityType']['typeKey'] = details['activityTypeDTO']['typeKey'] if 'activityTypeDTO' in details and present('typeKey', details['activityTypeDTO']) else None
    summary['activityType']['parentTypeId'] = details['activityTypeDTO']['parentTypeId'] if 'activityTypeDTO' in details and present('parentTypeId', details['activityTypeDTO']) else None
    summary['eventType'] = {}
    summary['eventType']['typeKey'] = details['eventType']['typeKey'] if 'eventType' in details and present('typeKey', details['eventType']) else None
    summary['startTimeLocal'] = details['summaryDTO']['startTimeLocal'] if 'summaryDTO' in details and 'startTimeLocal' in details['summaryDTO'] else None
    summary['startTimeGMT'] = details['summaryDTO']['startTimeGMT'] if 'summaryDTO' in details and 'startTimeGMT' in details['summaryDTO'] else None
    summary['duration'] = details['summaryDTO']['duration'] if 'summaryDTO' in details and 'duration' in details['summaryDTO'] else None
    summary['distance'] = details['summaryDTO']['distance'] if 'summaryDTO' in details and 'distance' in details['summaryDTO'] else None
    summary['averageSpeed'] = details['summaryDTO']['averageSpeed'] if 'summaryDTO' in details and 'averageSpeed' in details['summaryDTO'] else None
    summary['maxHR'] = details['summaryDTO']['maxHR'] if 'summaryDTO' in details and 'maxHR' in details['summaryDTO'] else None
    summary['averageHR'] = details['summaryDTO']['averageHR'] if 'summaryDTO' in details and 'averageHR' in details['summaryDTO'] else None
    summary['elevationCorrected'] = details['metadataDTO']['elevationCorrected'] if 'metadataDTO' in details and 'elevationCorrected' in details['metadataDTO'] else None
    # fmt: on


def process_activity_item(item, number_of_items, device_dict, type_filter, activity_type_name, event_type_name, csv_filter, args):
    """
    Process one activity item: download the data, parse it and write a line to the CSV file

    :param item:               activity item tuple, see `annotate_activity_list()`
    :param number_of_items:    total number of items (for progress output)
    :param device_dict:        cache (dict) of already known devices
    :param type_filter:        list of activity types to include in the output
    :param activity_type_name: lookup table for activity type descriptions
    :param event_type_name:    lookup table for event type descriptions
    :param csv_filter:         object encapsulating CSV file access
    :param args:               command-line arguments
    """
    current_index = item['index'] + 1
    actvty = item['activity']
    action = item['action']

    # Action: skipping
    if action == 's':
        # Display which entry we're skipping.
        print('Skipping   : Garmin Connect activity ', end='')
        print(f"({current_index}/{number_of_items}) [{actvty['activityId']}]")
        return

    # Action: excluding
    if action == 'e':
        # Display which entry we're skipping.
        print('Excluding  : Garmin Connect activity ', end='')
        print(f"({current_index}/{number_of_items}) [{actvty['activityId']}]")
        return

    # Action: Filtered out by typeId
    if action == 'f':
        # Display which entry we're skipping.
        activity_type = actvty['activityType']
        print(
            f"Filtering out due to type {activity_type['typeKey']} (ID {activity_type['typeId']}) not in {type_filter}: Garmin Connect activity ",
            end='',
        )
        print(f"({current_index}/{number_of_items}) [{actvty['activityId']}]")
        return

    # Action: download
    # Display which entry we're working on.
    print('Downloading: Garmin Connect activity ', end='')
    activity_name = actvty['activityName'] if present('activityName', actvty) else ""
    print(f"({current_index}/{number_of_items}) [{actvty['activityId']}] {activity_name}")

    # Retrieve also the detail data from the activity (the one displayed on
    # the https://connect.garmin.com/modern/activity/xxx page), because some
    # data are missing from 'actvty' (or are even different, e.g. for my activities
    # 86497297 or 86516281)
    activity_details, details = fetch_details(actvty['activityId'], http_req_as_string)

    extract = {}
    extract['start_time_with_offset'] = offset_date_time(actvty['startTimeLocal'], actvty['startTimeGMT'])
    if 'summaryDTO' in details and 'elapsedDuration' in details['summaryDTO']:
        elapsed_duration = details['summaryDTO']['elapsedDuration']
    else:
        elapsed_duration = None
    extract['elapsed_duration'] = elapsed_duration if elapsed_duration else actvty['duration']
    extract['elapsed_seconds'] = int(round(extract['elapsed_duration']))
    extract['end_time_with_offset'] = extract['start_time_with_offset'] + timedelta(seconds=extract['elapsed_seconds'])

    print('\t', extract['start_time_with_offset'].isoformat(), ', ', sep='', end='')
    print(hhmmss_from_seconds(extract['elapsed_seconds']), ', ', sep='', end='')
    if 'distance' in actvty and isinstance(actvty['distance'], float):
        print(f"{actvty['distance'] / 1000:.3f} km")
    else:
        print('0.000 km')

    if args.desc is not None:
        append_desc = '_' + sanitize_filename(activity_name, args.desc)
    else:
        append_desc = ''

    if args.originaltime:
        start_time_seconds = epoch_seconds_from_summary(actvty)
    else:
        start_time_seconds = None

    extract['device'] = extract_device(device_dict, details, start_time_seconds, args, http_req_as_string, write_to_file)

    # try to get the JSON with all the samples (not all activities have it...),
    # but only if it's really needed for the CSV output
    extract['samples'] = None
    if csv_filter.is_column_active('sampleCount'):
        try:
            # TODO implement retries here, I have observed temporary failures
            activity_measurements = http_req_as_string(f"{URL_GC_ACTIVITY}{actvty['activityId']}/details")
            write_to_file(
                os.path.join(args.directory, f"activity_{actvty['activityId']}_samples.json"),
                activity_measurements,
                'w',
                start_time_seconds,
            )
            samples = json.loads(activity_measurements)
            extract['samples'] = samples
        except HTTPError as ex:
            logging.info("Unable to get samples for %d", actvty['activityId'])
            logging.exception(ex)

    extract['gear'] = None
    if csv_filter.is_column_active('gear'):
        extract['gear'] = load_gear(str(actvty['activityId']), args)

    extract['hrZones'] = HR_ZONES_EMPTY
    if csv_filter.is_column_active('hrZone1Low') or csv_filter.is_column_active('hrZone1Seconds'):
        extract['hrZones'] = load_zones(str(actvty['activityId']), start_time_seconds, args, http_req_as_string, write_to_file)

    # Save the file and inform if it already existed. If the file already existed, do not append the record to the csv
    if export_data_file(
        str(actvty['activityId']), activity_details, args, start_time_seconds, append_desc, actvty['startTimeLocal']
    ):
        # Write stats to CSV.
        csv_write_record(csv_filter, extract, actvty, details, activity_type_name, event_type_name)


def main(argv):
    """
    Main entry point for gcexport.py
    """
    args = parse_arguments(argv)
    setup_logging(args)
    logging.info("Starting %s version %s, using Python version %s", argv[0], SCRIPT_VERSION, python_version())
    logging_verbosity(args.verbosity)

    print('Welcome to Garmin Connect Exporter!')

    if sys.version_info < MINIMUM_PYTHON_VERSION:
        logging.warning(
            "Python version %s is older than %s.%s.x, results might be unexpected",
            python_version(),
            MINIMUM_PYTHON_VERSION[0],
            MINIMUM_PYTHON_VERSION[1],
        )

    # Get filter list with IDs to exclude
    if args.exclude is not None:
        exclude_list = read_exclude(args.exclude)
        if exclude_list is None:
            sys.exit(1)
    else:
        exclude_list = []

    # Create directory for data files.
    if os.path.isdir(args.directory):
        logging.warning(
            'Output directory %s already exists. Will skip already-downloaded files and append to the CSV file.', args.directory
        )
    else:
        os.mkdir(args.directory)

    login_to_garmin_connect(args)

    # Query the userstats (activities totals on the profile page). Needed for
    # filtering and for downloading 'all' to know how many activities are available
    userstats_json = fetch_userstats(args)

    if args.count == 'all':
        total_to_download = int(userstats_json['userMetrics'][0]['totalActivities'])
    else:
        total_to_download = int(args.count)

    # Load some dictionaries with lookup data from REST services
    activity_type_props = http_req_as_string(URL_GC_ACT_PROPS)
    if args.verbosity > 0:
        write_to_file(os.path.join(args.directory, 'activity_types.properties'), activity_type_props, 'w')
    activity_type_name = load_properties(activity_type_props)
    event_type_props = http_req_as_string(URL_GC_EVT_PROPS)
    if args.verbosity > 0:
        write_to_file(os.path.join(args.directory, 'event_types.properties'), event_type_props, 'w')
    event_type_name = load_properties(event_type_props)

    activities = fetch_activity_list(args, total_to_download)

    type_filter = args.type_filter.split(',') if args.type_filter is not None else None

    action_list = annotate_activity_list(activities, args.start_activity_no, exclude_list, type_filter)

    csv_filename = os.path.join(args.directory, 'activities.csv')
    csv_existed = os.path.isfile(csv_filename)

    device_dict = {}
    with open(csv_filename, mode='a', encoding='utf-8') as csv_file:
        csv_filter = CsvFilter(csv_file, args.template)

        # Write header to CSV file
        if not csv_existed:
            csv_filter.write_header()

        # Process each activity.
        for item in action_list:
            try:
                process_activity_item(
                    item, len(action_list), device_dict, type_filter, activity_type_name, event_type_name, csv_filter, args
                )
            except Exception as ex_item:
                activity_id = (
                    item['activity']['activityId']
                    if present('activity', item) and present('activityId', item['activity'])
                    else "(unknown id)"
                )
                logging.error("Error during processing of activity '%s': %s/%s", activity_id, type(ex_item), ex_item)
                raise

    logging.info('CSV file written.')

    if args.external:
        print('Open CSV output.')
        print(csv_filename)
        call([args.external, "--" + args.args, csv_filename])

    print('Done!')


if __name__ == "__main__":
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print('Interrupted')
        sys.exit(0)
    except Exception as abort_exception:  # pylint: disable=broad-except
        logging.error("Processing aborted.")
        logging.exception(abort_exception)
