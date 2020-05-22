#!/usr/bin/python
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

# this avoids different pylint behaviour for python 2 and 3
from __future__ import print_function

from datetime import datetime, timedelta, tzinfo
from getpass import getpass
from math import floor
from platform import python_version
from subprocess import call
from timeit import default_timer as timer

import argparse
import csv
import io
import json
import logging
import os
import os.path
import re
import string
import sys
import unicodedata
import zipfile

python3 = sys.version_info.major == 3
if python3:
    import http.cookiejar
    import urllib.error
    import urllib.parse
    import urllib.request
    import urllib
    from urllib.parse import urlencode
    from urllib.request import Request, HTTPError, URLError
    COOKIE_JAR = http.cookiejar.CookieJar()
    OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR), urllib.request.HTTPSHandler(debuglevel=0))
else:
    import cookielib
    import urllib2
    from urllib import urlencode
    from urllib2 import Request, HTTPError, URLError
    COOKIE_JAR = cookielib.CookieJar()
    OPENER = urllib2.build_opener(urllib2.HTTPCookieProcessor(COOKIE_JAR), urllib2.HTTPSHandler(debuglevel=0))

SCRIPT_VERSION = '3.0.0'

# this is almost the datetime format Garmin used in the activity-search-service
# JSON 'display' fields (Garmin didn't zero-pad the date and the hour, but %d and %H do)
ALMOST_RFC_1123 = "%a, %d %b %Y %H:%M"

# used by sanitize_filename()
VALID_FILENAME_CHARS = "-_.() %s%s" % (string.ascii_letters, string.digits)

# map the numeric parentTypeId to its name for the CSV output
PARENT_TYPE_ID = {
    1: 'running',
    2: 'cycling',
    3: 'hiking',
    4: 'other',
    9: 'walking',
    17: 'any',
    26: 'swimming',
    29: 'fitness_equipment',
    71: 'motorcycling',
    83: 'transition',
    144: 'diving',
    149: 'yoga',
    165: 'winter_sports'
}

# typeId values using pace instead of speed
USES_PACE = {1, 3, 9}  # running, hiking, walking

# Maximum number of activities you can request at once.
# Used to be 100 and enforced by Garmin for older endpoints; for the current endpoint 'URL_GC_LIST'
# the limit is not known (I have less than 1000 activities and could get them all in one go)
LIMIT_MAXIMUM = 1000

MAX_TRIES = 3

CSV_TEMPLATE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "csv_header_default.properties")

WEBHOST = "https://connect.garmin.com"
REDIRECT = "https://connect.garmin.com/modern/"
BASE_URL = "https://connect.garmin.com/en-US/signin"
SSO = "https://sso.garmin.com/sso"
CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.2-min.css"

DATA = {
    'service': REDIRECT,
    'webhost': WEBHOST,
    'source': BASE_URL,
    'redirectAfterAccountLoginUrl': REDIRECT,
    'redirectAfterAccountCreationUrl': REDIRECT,
    'gauthHost': SSO,
    'locale': 'en_US',
    'id': 'gauth-widget',
    'cssUrl': CSS,
    'clientId': 'GarminConnect',
    'rememberMeShown': 'true',
    'rememberMeChecked': 'false',
    'createAccountShown': 'true',
    'openCreateAccount': 'false',
    'displayNameShown': 'false',
    'consumeServiceTicket': 'false',
    'initialFocus': 'true',
    'embedWidget': 'false',
    'generateExtraServiceTicket': 'true',
    'generateTwoExtraServiceTickets': 'false',
    'generateNoServiceTicket': 'false',
    'globalOptInShown': 'true',
    'globalOptInChecked': 'false',
    'mobile': 'false',
    'connectLegalTerms': 'true',
    'locationPromptShown': 'true',
    'showPassword': 'true'
}

# URLs for various services.

URL_GC_LOGIN = 'https://sso.garmin.com/sso/signin?' + urlencode(DATA)
URL_GC_POST_AUTH = 'https://connect.garmin.com/modern/activities?'
URL_GC_PROFILE = 'https://connect.garmin.com/modern/profile'
URL_GC_USERSTATS = 'https://connect.garmin.com/modern/proxy/userstats-service/statistics/'
URL_GC_LIST = 'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
URL_GC_ACTIVITY = 'https://connect.garmin.com/modern/proxy/activity-service/activity/'
URL_GC_DEVICE = 'https://connect.garmin.com/modern/proxy/device-service/deviceservice/app-info/'
URL_GC_GEAR = 'https://connect.garmin.com/modern/proxy/gear-service/gear/filterGear?activityId='
URL_GC_ACT_PROPS = 'https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties'
URL_GC_EVT_PROPS = 'https://connect.garmin.com/modern/main/js/properties/event_types/event_types.properties'
URL_GC_GPX_ACTIVITY = 'https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/'
URL_GC_TCX_ACTIVITY = 'https://connect.garmin.com/modern/proxy/download-service/export/tcx/activity/'
URL_GC_ORIGINAL_ACTIVITY = 'http://connect.garmin.com/proxy/download-service/files/activity/'


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
    :param content:      content to write; with Python 2 always of type 'str',
                         with Python 3 it can be 'bytes' or 'str'. If it's
                         'bytes' and the mode 'w', it will be converted/decoded
    :param mode:         'w' or 'wb'
    :param file_time:    if given use as timestamp for the file written
    """
    if mode == 'w':
        write_file = io.open(filename, mode, encoding="utf-8")
        if isinstance(content, bytes):
            content = content.decode("utf-8")
    elif mode == 'wb':
        write_file = io.open(filename, mode)
    else:
        raise Exception('Unsupported file mode: ', mode)
    write_file.write(content)
    write_file.close()
    if file_time:
        os.utime(filename, (file_time, file_time))


def http_req(url, post=None, headers=None):
    """
    Helper function that makes the HTTP requests.

    :param url:          URL for the request
    :param post:         dictionary of POST parameters
    :param headers:      dictionary of headers
    :return: response body (type 'str' with Python 2, type 'bytes' with Python 3
    """
    request = Request(url)
    # Tell Garmin we're some supported browser.
    request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, \
        like Gecko) Chrome/54.0.2816.0 Safari/537.36')
    if headers:
        if python3:
            for header_key, header_value in headers.items():
                request.add_header(header_key, header_value)
        else:
            for header_key, header_value in headers.iteritems():
                request.add_header(header_key, header_value)
    if post:
        post = urlencode(post)  # Convert dictionary to POST parameter string.
        if python3:
            post = post.encode("utf-8")
    start_time = timer()
    try:
        response = OPENER.open(request, data=post)
    except URLError as ex:
        if hasattr(ex, 'reason'):
            logging.error('Failed to reach url %s, error: %s', url, ex)
            raise
        else:
            raise
    logging.debug('Got %s in %s s from %s', response.getcode(), timer() - start_time, url)

    # N.B. urllib2 will follow any 302 redirects.
    # print(response.getcode())
    if response.getcode() == 204:
        # 204 = no content, e.g. for activities without GPS coordinates there is no GPX download.
        # Write an empty file to prevent redownloading it.
        logging.info('Got 204 for %s, returning empty response', url)
        return b''
    elif response.getcode() != 200:
        raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

    return response.read()

def http_req_as_string(url, post=None, headers=None):
    """Helper function that makes the HTTP requests, returning a string instead of bytes."""
    if python3:
        return http_req(url, post, headers).decode()
    else:
        return http_req(url, post, headers)


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
            if keys != None:
                keys.append(key)
    return props


def value_if_found_else_key(some_dict, key):
    """Lookup a value in some_dict and use the key itself as fallback"""
    return some_dict.get(key, key)


def present(element, act):
    """Return True if act[element] is valid and not None"""
    if not act:
        return False
    elif element not in act:
        return False
    return act[element]


def absent_or_null(element, act):
    """Return False only if act[element] is valid and not None"""
    if not act:
        return True
    elif element not in act:
        return True
    elif act[element]:
        return False
    return True


def from_activities_or_detail(element, act, detail, detail_container):
    """Return detail[detail_container][element] if valid and act[element] (or None) otherwise"""
    if absent_or_null(detail_container, detail) or absent_or_null(element, detail[detail_container]):
        return None if absent_or_null(element, act) else act[element]
    return detail[detail_container][element]


def trunc6(some_float):
    """Return the given float as string formatted with six digit precision"""
    return "{0:12.6f}".format(floor(some_float * 1000000) / 1000000).lstrip()


# A class building tzinfo objects for fixed-offset time zones.
# (copied from https://docs.python.org/2/library/datetime.html)
class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset, name):
        super(FixedOffset, self).__init__()
        self.__offset = timedelta(minutes=offset)
        self.__name = name

    def utcoffset(self, dt):
        del dt # unused
        return self.__offset

    def tzname(self, dt):
        del dt # unused
        return self.__name

    def dst(self, dt):
        del dt # unused
        return timedelta(0)


def offset_date_time(time_local, time_gmt):
    """
    Build an 'aware' datetime from two 'naive' datetime objects (that is timestamps
    as present in the activitylist-service.json), using the time difference as offset.
    """
    local_dt = datetime.strptime(time_local, "%Y-%m-%d %H:%M:%S")
    gmt_dt = datetime.strptime(time_gmt, "%Y-%m-%d %H:%M:%S")
    offset = local_dt - gmt_dt
    offset_tz = FixedOffset(offset.seconds // 60, "LCL")
    return local_dt.replace(tzinfo=offset_tz)


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
        return '{0:02d}:{1:02d}'.format(*divmod(int(round(3600 / kmh)), 60))
    return "{0:.1f}".format(round(kmh, 1))


class CsvFilter(object):
    """Collects, filters and writes CSV."""

    def __init__(self, csv_file, csv_header_properties):
        self.__csv_file = csv_file
        with open(csv_header_properties, 'r') as prop:
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
            if python3:
                self.__current_row[self.__csv_headers[name]] = value
            else:
                # must encode in UTF-8 because the Python 2 'csv' module doesn't support unicode
                self.__current_row[self.__csv_headers[name]] = value.encode('utf8')

    def is_column_active(self, name):
        """Return True if the column is present in the header template"""
        return name in self.__csv_columns


def parse_arguments(argv):
    """
    Setup the argument parser and parse the command line arguments.
    """
    current_date = datetime.now().strftime('%Y-%m-%d')
    activities_directory = './' + current_date + '_garmin_connect_export'

    parser = argparse.ArgumentParser(description='Garmin Connect Exporter')

    parser.add_argument('--version', action='version', version='%(prog)s ' + SCRIPT_VERSION,
        help='print version and exit')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
        help='increase output verbosity')
    parser.add_argument('--username',
        help='your Garmin Connect username or email address (otherwise, you will be prompted)')
    parser.add_argument('--password',
        help='your Garmin Connect password (otherwise, you will be prompted)')
    parser.add_argument('-c', '--count', default='1',
        help='number of recent activities to download, or \'all\' (default: 1)')
    parser.add_argument('-e', '--external',
        help='path to external program to pass CSV file too')
    parser.add_argument('-a', '--args',
        help='additional arguments to pass to external program')
    parser.add_argument('-f', '--format', choices=['gpx', 'tcx', 'original', 'json'], default='gpx',
        help="export format; can be 'gpx', 'tcx', 'original' or 'json' (default: 'gpx')")
    parser.add_argument('-d', '--directory', default=activities_directory,
        help='the directory to export to (default: \'./YYYY-MM-DD_garmin_connect_export\')')
    parser.add_argument('-s', "--subdir",
        help="the subdirectory for activity files (tcx, gpx etc.), supported placeholders are {YYYY} and {MM}"
                        " (default: export directory)" )
    parser.add_argument('-u', '--unzip', action='store_true',
        help='if downloading ZIP files (format: \'original\'), unzip the file and remove the ZIP file')
    parser.add_argument('-ot', '--originaltime', action='store_true',
        help='will set downloaded (and possibly unzipped) file time to the activity start time')
    parser.add_argument('--desc', type=int, nargs='?', const=0, default=None,
        help='append the activity\'s description to the file name of the download; limit size if number is given')
    parser.add_argument('-t', '--template', default=CSV_TEMPLATE,
        help='template file with desired columns for CSV output')
    parser.add_argument('-fp', '--fileprefix', action='count', default=0,
        help="set the local time as activity file name prefix")
    parser.add_argument('-sa', '--start_activity_no', type=int, default=1,
        help="give index for first activity to import, i.e. skipping the newest activites")

    return parser.parse_args(argv[1:])


def login_to_garmin_connect(args):
    """
    Perform all HTTP requests to login to Garmin Connect.
    """
    if python3:
        username = args.username if args.username else input('Username: ')
    else:
        username = args.username if args.username else raw_input('Username: ')
    password = args.password if args.password else getpass()

    logging.debug("Login params: %s", urlencode(DATA))

    # Initially, we need to get a valid session cookie, so we pull the login page.
    print('Connecting to Garmin Connect...', end='')
    logging.info('Connecting to %s', URL_GC_LOGIN)
    connect_response = http_req_as_string(URL_GC_LOGIN)
    # write_to_file('connect_response.html', connect_response, 'w')
    for cookie in COOKIE_JAR:
        logging.debug("Cookie %s : %s", cookie.name, cookie.value)
    print(' Done.')

    # Now we'll actually login.
    # Fields that are passed in a typical Garmin login.
    post_data = {
        'username': username,
        'password': password,
        'embed': 'false',
        'rememberme': 'on'
    }

    headers = {
        'referer': URL_GC_LOGIN
    }

    print('Requesting Login ticket...', end='')
    login_response = http_req_as_string(URL_GC_LOGIN + '#', post_data, headers)
    
    for cookie in COOKIE_JAR:
        logging.debug("Cookie %s : %s", cookie.name, cookie.value)
    # write_to_file('login-response.html', login_response, 'w')

    # extract the ticket from the login response
    pattern = re.compile(r".*\?ticket=([-\w]+)\";.*", re.MULTILINE | re.DOTALL)
    match = pattern.match(login_response)
    if not match:
        raise Exception('Couldn\'t find ticket in the login response. Cannot log in. '
                        'Did you enter the correct username and password?')
    login_ticket = match.group(1)
    print(' Done. Ticket=', login_ticket, sep='')

    print("Authenticating...", end='')
    logging.info('Authentication URL %s', URL_GC_POST_AUTH + 'ticket=' + login_ticket)
    http_req(URL_GC_POST_AUTH + 'ticket=' + login_ticket)
    print(' Done.')


def csv_write_record(csv_filter, extract, actvty, details, activity_type_name, event_type_name):
    """
    Write out the given data as a CSV record
    """

    type_id = 4 if absent_or_null('activityType', actvty) else actvty['activityType']['typeId']
    parent_type_id = 4 if absent_or_null('activityType', actvty) else actvty['activityType']['parentTypeId']
    if present(parent_type_id, PARENT_TYPE_ID):
        parent_type_key = PARENT_TYPE_ID[parent_type_id]
    else:
        parent_type_key = None
        logging.warning("Unknown parentType %s, please tell script author", str(parent_type_id))

    # get some values from detail if present, from a otherwise
    start_latitude = from_activities_or_detail('startLatitude', actvty, details, 'summaryDTO')
    start_longitude = from_activities_or_detail('startLongitude', actvty, details, 'summaryDTO')
    end_latitude = from_activities_or_detail('endLatitude', actvty, details, 'summaryDTO')
    end_longitude = from_activities_or_detail('endLongitude', actvty, details, 'summaryDTO')

    csv_filter.set_column('id', str(actvty['activityId']))
    csv_filter.set_column('url', 'https://connect.garmin.com/modern/activity/' + str(actvty['activityId']))
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
    csv_filter.set_column('distanceRaw', "{0:.5f}".format(actvty['distance'] / 1000) if present('distance', actvty) else None)
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
    csv_filter.set_column('elevationLossUncorr', str(round(details['summaryDTO']['elevationLoss'], 2)) if not actvty['elevationCorrected'] and present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLossCorr', str(round(details['summaryDTO']['elevationLoss'], 2)) if actvty['elevationCorrected'] and present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGain', str(round(details['summaryDTO']['elevationGain'], 2)) if present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGainUncorr', str(round(details['summaryDTO']['elevationGain'], 2)) if not actvty['elevationCorrected'] and present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGainCorr', str(round(details['summaryDTO']['elevationGain'], 2)) if actvty['elevationCorrected'] and present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('minElevation', str(round(details['summaryDTO']['minElevation'], 2)) if present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('minElevationUncorr', str(round(details['summaryDTO']['minElevation'], 2)) if not actvty['elevationCorrected'] and present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('minElevationCorr', str(round(details['summaryDTO']['minElevation'], 2)) if actvty['elevationCorrected'] and present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevation', str(round(details['summaryDTO']['maxElevation'], 2)) if present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevationUncorr', str(round(details['summaryDTO']['maxElevation'], 2)) if not actvty['elevationCorrected'] and present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevationCorr', str(round(details['summaryDTO']['maxElevation'], 2)) if actvty['elevationCorrected'] and present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('elevationCorrected', 'true' if actvty['elevationCorrected'] else 'false')
    # csv_record += empty_record  # no minimum heart rate in JSON
    csv_filter.set_column('maxHRRaw', str(details['summaryDTO']['maxHR']) if present('maxHR', details['summaryDTO']) else None)
    csv_filter.set_column('maxHR', "{0:.0f}".format(actvty['maxHR']) if present('maxHR', actvty) else None)
    csv_filter.set_column('averageHRRaw', str(details['summaryDTO']['averageHR']) if present('averageHR', details['summaryDTO']) else None)
    csv_filter.set_column('averageHR', "{0:.0f}".format(actvty['averageHR']) if present('averageHR', actvty) else None)
    csv_filter.set_column('caloriesRaw', str(details['summaryDTO']['calories']) if present('calories', details['summaryDTO']) else None)
    csv_filter.set_column('calories', "{0:.0f}".format(details['summaryDTO']['calories']) if present('calories', details['summaryDTO']) else None)
    csv_filter.set_column('vo2max', str(actvty['vO2MaxValue']) if present('vO2MaxValue', actvty) else None)
    csv_filter.set_column('aerobicEffect', str(round(details['summaryDTO']['trainingEffect'], 2)) if present('trainingEffect', details['summaryDTO']) else None)
    csv_filter.set_column('anaerobicEffect', str(round(details['summaryDTO']['anaerobicTrainingEffect'], 2)) if present('anaerobicTrainingEffect', details['summaryDTO']) else None)
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

    csv_filter.write_row()


def extract_device(device_dict, details, start_time_seconds, args, http_caller, file_writer):
    """
    Try to get the device details (and cache them, as they're used for multiple activities)

    :param device_dict:  cache (dict) of already known devices
    :param details:      dict with the details of an activity, should contain a device ID
    :param args:         command-line arguments (for the file_writer callback)
    :param http_caller:  callback to perform the HTTP call for downloading the device details
    :param file_writer:  callback that saves the device details in a file
    :return: string with the device name
    """
    if not present('metadataDTO', details):
        logging.warning("no metadataDTO")
        return None

    metadata = details['metadataDTO']
    device_app_inst_id = metadata['deviceApplicationInstallationId'] if present('deviceApplicationInstallationId', metadata) else None
    if device_app_inst_id:
        if device_app_inst_id not in device_dict:
            # observed from my stock of activities:
            # details['metadataDTO']['deviceMetaDataDTO']['deviceId'] == null -> device unknown
            # details['metadataDTO']['deviceMetaDataDTO']['deviceId'] == '0' -> device unknown
            # details['metadataDTO']['deviceMetaDataDTO']['deviceId'] == 'someid' -> device known
            device_dict[device_app_inst_id] = None
            device_meta = metadata['deviceMetaDataDTO'] if present('deviceMetaDataDTO', metadata) else None
            device_id = device_meta['deviceId'] if present('deviceId', device_meta) else None
            if 'deviceId' not in device_meta or device_id and device_id != '0':
                device_json = http_caller(URL_GC_DEVICE + str(device_app_inst_id))
                file_writer(os.path.join(args.directory, 'device_' + str(device_app_inst_id) + '.json'),
                            device_json, 'w',
                            start_time_seconds)
                if not device_json:
                    logging.warning("Device Details %s are empty", device_app_inst_id)
                    device_dict[device_app_inst_id] = "device-id:" + str(device_app_inst_id)
                else:
                    device_details = json.loads(device_json)
                    if present('productDisplayName', device_details):
                        device_dict[device_app_inst_id] = device_details['productDisplayName'] + ' ' \
                                                          + device_details['versionString']
                    else:
                        logging.warning("Device details %s incomplete", device_app_inst_id)
        return device_dict[device_app_inst_id]
    return None


def load_gear(activity_id, args):
    """Retrieve the gear/equipment for an activity"""
    try:
        gear_json = http_req_as_string(URL_GC_GEAR + activity_id)
        gear = json.loads(gear_json)
        if gear:
            del args # keep 'args' argument in case you need to uncomment write_to_file
            # write_to_file(join(args.directory, 'activity_' + activity_id + '-gear.json'),
            #               gear_json, 'w')
            gear_display_name = gear[0]['displayName'] if present('displayName', gear[0]) else None
            gear_model = gear[0]['customMakeModel'] if present('customMakeModel', gear[0]) else None
            logging.debug("Gear for %s = %s/%s", activity_id, gear_display_name, gear_model)
            return gear_display_name if gear_display_name else gear_model
        return None
    except HTTPError:
        pass  # don't abort just for missing gear...
        # logging.info("Unable to get gear for %d", activity_id)
        # logging.exception(e)


def export_data_file(activity_id, activity_details, args, file_time, append_desc, start_time_locale):
    """
    Write the data of the activity to a file, depending on the chosen data format
    """
    # Time dependent subdirectory for activity files, e.g. '{YYYY}
    if not args.subdir is None:
        directory = resolve_path(args.directory, args.subdir, start_time_locale)
    # export activities to root directory
    else:
        directory = args.directory

    if not os.path.isdir(directory):
        os.makedirs(directory)

    # timestamp as prefix for filename
    if args.fileprefix > 0:
        prefix = "{}-".format(start_time_locale.replace("-", "").replace(":", "").replace(" ", "-"))
    else:
        prefix = ""

    fit_filename = None
    if args.format == 'gpx':
        data_filename = os.path.join(directory, prefix + 'activity_' + activity_id + append_desc + '.gpx')
        download_url = URL_GC_GPX_ACTIVITY + activity_id + '?full=true'
        file_mode = 'w'
    elif args.format == 'tcx':
        data_filename = os.path.join(directory, prefix + 'activity_' + activity_id + append_desc + '.tcx')
        download_url = URL_GC_TCX_ACTIVITY + activity_id + '?full=true'
        file_mode = 'w'
    elif args.format == 'original':
        data_filename = os.path.join(directory, prefix + 'activity_' + activity_id + append_desc + '.zip')
        # TODO not all 'original' files are in FIT format, some are GPX or TCX...
        fit_filename = os.path.join(directory, prefix + 'activity_' + activity_id + append_desc + '.fit')
        download_url = URL_GC_ORIGINAL_ACTIVITY + activity_id
        file_mode = 'wb'
    elif args.format == 'json':
        data_filename = os.path.join(directory, prefix + 'activity_' + activity_id + append_desc + '.json')
        file_mode = 'w'
    else:
        raise Exception('Unrecognized format.')

    if os.path.isfile(data_filename):
        logging.debug('Data file for %s already exists', activity_id)
        print('\tData file already exists; skipping...')
        return

    # Regardless of unzip setting, don't redownload if the ZIP or FIT file exists.
    if args.format == 'original' and os.path.isfile(fit_filename):
        logging.debug('Original data file for %s already exists', activity_id)
        print('\tFIT data file already exists; skipping...')
        return

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
                logging.info('Writing empty file since Garmin did not generate a TCX file for this \
                             activity...')
                data = ''
            elif ex.code == 404 and args.format == 'original':
                # For manual activities (i.e., entered in online without a file upload), there is
                # no original file. # Write an empty file to prevent redownloading it.
                logging.info('Writing empty file since there was no original activity data...')
                data = ''
            else:
                logging.info('Got %s for %s', ex.code, download_url)
                raise Exception('Failed. Got an HTTP error ' + str(ex.code) + ' for ' + download_url)
    else:
        data = activity_details

    # Persist file
    write_to_file(data_filename, data, file_mode, file_time)
    if args.format == 'original':
        # Even manual upload of a GPX file is zipped, but we'll validate the extension.
        if args.unzip and data_filename[-3:].lower() == 'zip':
            logging.debug('Unzipping and removing original file, size is %s', os.stat(data_filename).st_size)
            if os.stat(data_filename).st_size > 0:
                zip_file = open(data_filename, 'rb')
                zip_obj = zipfile.ZipFile(zip_file)
                for name in zip_obj.namelist():
                    unzipped_name = zip_obj.extract(name, directory)
                    # prepend 'activity_' and append the description to the base name
                    name_base, name_ext = os.path.splitext(name)
                    new_name = os.path.join(directory, prefix + 'activity_' + name_base + append_desc + name_ext)
                    logging.debug('renaming %s to %s', unzipped_name, new_name)
                    os.rename(unzipped_name, new_name)
                    if file_time:
                        os.utime(new_name, (file_time, file_time))
                zip_file.close()
            else:
                print('\tSkipping 0Kb zip file.')
            os.remove(data_filename)


def setup_logging():
    """Setup logging"""
    logging.basicConfig(
        filename='gcexport.log',
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)-7.7s] %(message)s'
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


def main(argv):
    """
    Main entry point for gcexport.py
    """
    setup_logging()
    logging.info("Starting %s version %s, using Python version %s", argv[0], SCRIPT_VERSION, python_version())
    args = parse_arguments(argv)
    logging_verbosity(args.verbosity)

    print('Welcome to Garmin Connect Exporter!')

    # Create directory for data files.
    if os.path.isdir(args.directory):
        logging.warning("Output directory %s already exists. "
                        "Will skip already-downloaded files and append to the CSV file.",
                        args.directory)

    login_to_garmin_connect(args)

    # We should be logged in now.
    if not os.path.isdir(args.directory):
        os.mkdir(args.directory)

    csv_filename = args.directory + '/activities.csv'
    csv_existed = os.path.isfile(csv_filename)

    if python3:
        csv_file = open(csv_filename, mode='a', encoding='utf-8')
    else:
        csv_file = open(csv_filename, 'a')
    csv_filter = CsvFilter(csv_file, args.template)

    # Write header to CSV file
    if not csv_existed:
        csv_filter.write_header()

    if args.count == 'all':
        # If the user wants to download all activities, query the userstats
        # on the profile page to know how many are available
        print('Getting display name...', end='')
        logging.info('Profile page %s', URL_GC_PROFILE)
        profile_page = http_req_as_string(URL_GC_PROFILE)
        # write_to_file(args.directory + '/profile.html', profile_page, 'a')

        # extract the display name from the profile page, it should be in there as
        # \"displayName\":\"John.Doe\"
        pattern = re.compile(r".*\\\"displayName\\\":\\\"([-.\w]+)\\\".*", re.MULTILINE | re.DOTALL)
        match = pattern.match(profile_page)
        if not match:
            raise Exception('Did not find the display name in the profile page.')
        display_name = match.group(1)
        print(' Done. displayName=', display_name, sep='')

        print('Fetching user stats...', end='')
        logging.info('Userstats page %s', URL_GC_USERSTATS + display_name)
        result = http_req_as_string(URL_GC_USERSTATS + display_name)
        print(' Done.')

        # Persist JSON
        write_to_file(args.directory + '/userstats.json', result, 'w')

        # Modify total_to_download based on how many activities the server reports.
        json_results = json.loads(result)
        total_to_download = int(json_results['userMetrics'][0]['totalActivities'])
    else:
        total_to_download = int(args.count)
    total_downloaded = 0

    device_dict = dict()

    # load some dictionaries with lookup data from REST services
    activity_type_props = http_req_as_string(URL_GC_ACT_PROPS)
    # write_to_file(args.directory + '/activity_types.properties', activity_type_props, 'a')
    activity_type_name = load_properties(activity_type_props)
    event_type_props = http_req_as_string(URL_GC_EVT_PROPS)
    # write_to_file(args.directory + '/event_types.properties', event_type_props, 'a')
    event_type_name = load_properties(event_type_props)

    # This while loop will download data from the server in multiple chunks, if necessary.
    while total_downloaded < total_to_download:
        # Maximum chunk size 'LIMIT_MAXIMUM' ... 400 return status if over maximum.  So download
        # maximum or whatever remains if less than maximum.
        # As of 2018-03-06 I get return status 500 if over maximum
        if total_to_download - total_downloaded > LIMIT_MAXIMUM:
            num_to_download = LIMIT_MAXIMUM
        else:
            num_to_download = total_to_download - total_downloaded

        search_params = {'start': total_downloaded, 'limit': num_to_download}
        # Query Garmin Connect
        print('Querying list of activities ', total_downloaded + 1,
              '..', total_downloaded + num_to_download,
              '...', sep='', end='')
        
        logging.info('Activity list URL %s', URL_GC_LIST + urlencode(search_params))
        result = http_req_as_string(URL_GC_LIST + urlencode(search_params))

        print(' Done.')

        # Persist JSON activities list
        current_index = total_downloaded + 1
        activities_list_filename = '/activities-' \
            + str(current_index) + '-' \
            + str(total_downloaded + num_to_download) + '.json'
        write_to_file(args.directory + activities_list_filename, result, 'w')

        activities = json.loads(result)
        if len(activities) != num_to_download:
            logging.warning('Expected %s activities, got %s.', num_to_download, len(activities))

        # Process each activity.
        for actvty in activities:
            if args.start_activity_no and current_index < args.start_activity_no:
                pass
                # Display which entry we're skipping.
                print('Skipping Garmin Connect activity ', end='')
                print('(', current_index, '/', total_to_download, ') ', sep='', end='')
                print('[', actvty['activityId'], ']', sep='')
            else:
                # Display which entry we're working on.
                print('Garmin Connect activity ', end='')
                print('(', current_index, '/', total_to_download, ') ', sep='', end='')
                print('[', actvty['activityId'], '] ', sep='', end='')
                print(actvty['activityName'])

                # Retrieve also the detail data from the activity (the one displayed on
                # the https://connect.garmin.com/modern/activity/xxx page), because some
                # data are missing from 'a' (or are even different, e.g. for my activities
                # 86497297 or 86516281)
                activity_details = None
                details = None
                tries = MAX_TRIES
                while tries > 0:
                    activity_details = http_req_as_string(URL_GC_ACTIVITY + str(actvty['activityId']))
                    details = json.loads(activity_details)
                    # I observed a failure to get a complete JSON detail in about 5-10 calls out of 1000
                    # retrying then statistically gets a better JSON ;-)
                    if details['summaryDTO']:
                        tries = 0
                    else:
                        logging.info("Retrying activity details download %s", URL_GC_ACTIVITY + str(actvty['activityId']))
                        tries -= 1
                        if tries == 0:
                            raise Exception('Didn\'t get "summaryDTO" after ' + str(MAX_TRIES) + ' tries for ' + str(actvty['activityId']))

                extract = {}
                extract['start_time_with_offset'] = offset_date_time(actvty['startTimeLocal'], actvty['startTimeGMT'])
                elapsed_duration = details['summaryDTO']['elapsedDuration'] if 'summaryDTO' in details and 'elapsedDuration' in details['summaryDTO'] else None
                extract['elapsed_duration'] = elapsed_duration if elapsed_duration else actvty['duration']
                extract['elapsed_seconds'] = int(round(extract['elapsed_duration']))
                extract['end_time_with_offset'] = extract['start_time_with_offset'] + timedelta(seconds=extract['elapsed_seconds'])

                print('\t', extract['start_time_with_offset'].isoformat(), ', ', sep='', end='')
                print(hhmmss_from_seconds(extract['elapsed_seconds']), ', ', sep='', end='')
                if 'distance' in actvty and isinstance(actvty['distance'], (float)):
                    print("{0:.3f}".format(actvty['distance'] / 1000), 'km', sep='')
                else:
                    print('0.000 km')

                if args.desc != None:
                    append_desc = '_' + sanitize_filename(actvty['activityName'], args.desc)
                else:
                    append_desc = ''

                if args.originaltime:
                    start_time_seconds = actvty['beginTimestamp'] // 1000 if present('beginTimestamp', actvty) else None
                else:
                    start_time_seconds = None

                extract['device'] = extract_device(device_dict, details, start_time_seconds, args, http_req_as_string, write_to_file)

                # try to get the JSON with all the samples (not all activities have it...),
                # but only if it's really needed for the CSV output
                extract['samples'] = None
                if csv_filter.is_column_active('sampleCount'):
                    try:
                        # TODO implement retries here, I have observed temporary failures
                        activity_measurements = http_req_as_string(URL_GC_ACTIVITY + str(actvty['activityId']) + "/details")
                        write_to_file(args.directory + '/activity_' + str(actvty['activityId']) + '_samples.json',
                                      activity_measurements, 'w',
                                      start_time_seconds)
                        samples = json.loads(activity_measurements)
                        extract['samples'] = samples
                    except HTTPError:
                        pass # don't abort just for missing samples...
                        # logging.info("Unable to get samples for %d", actvty['activityId'])
                        # logging.exception(e)

                extract['gear'] = None
                if csv_filter.is_column_active('gear'):
                    extract['gear'] = load_gear(str(actvty['activityId']), args)

                # Write stats to CSV.
                csv_write_record(csv_filter, extract, actvty, details, activity_type_name, event_type_name)

                export_data_file(str(actvty['activityId']), activity_details, args, start_time_seconds, append_desc,
                                 actvty['startTimeLocal'])

            current_index += 1
        # End for loop for activities of chunk
        total_downloaded += num_to_download
    # End while loop for multiple chunks.

    csv_file.close()

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
