#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
File: gcexport.py
Original author: Kyle Krafka (https://github.com/kjkjava/)
Date: April 28, 2015
Fork author: Michael P (https://github.com/moderation/)
Date: February 21, 2016

Description:    Use this script to export your fitness data from Garmin Connect.
                See README.md for more information.

Activity & event types:
    https://connect.garmin.com/modern/main/js/properties/event_types/event_types.properties
    https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties
"""

# this avoids different pylint behaviour for python 2 and 3
from __future__ import print_function

from math import floor
from sets import Set
from urllib import urlencode
from datetime import datetime, timedelta, tzinfo
from getpass import getpass
from os import mkdir, remove, stat
from os.path import isdir, isfile
from xml.dom.minidom import parseString

import argparse
import cookielib
import csv
import json
import re
import sys
import urllib2
import zipfile

SCRIPT_VERSION = '2.0.3'

COOKIE_JAR = cookielib.CookieJar()
OPENER = urllib2.build_opener(urllib2.HTTPCookieProcessor(COOKIE_JAR))

# this is almost the datetime format Garmin used in the activity-search-service
# JSON 'display' fields (Garmin didn't zero-pad the date and the hour, but %d and %H do)
ALMOST_RFC_1123 = "%a, %d %b %Y %H:%M"

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
    149: 'yoga'
}

# typeId values using pace instead of speed
USES_PACE = Set([1, 3, 9])  # running, hiking, walking

# Maximum number of activities you can request at once.
# Used to be 100 and enforced by Garmin for older endpoints; for the current endpoint 'URL_GC_LIST'
# the limit is not known (I have less than 1000 activities and could get them all in one go)
LIMIT_MAXIMUM = 1000

MAX_TRIES = 3

CSV_TEMPLATE = "csv_header_default.properties"

WEBHOST = "https://connect.garmin.com"
REDIRECT = "https://connect.garmin.com/post-auth/login"
BASE_URL = "http://connect.garmin.com/en-US/signin"
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
    'usernameShown': 'false',
    'displayNameShown': 'false',
    'consumeServiceTicket': 'false',
    'initialFocus': 'true',
    'embedWidget': 'false',
    'generateExtraServiceTicket': 'false'
}

# URLs for various services.
URL_GC_LOGIN = 'https://sso.garmin.com/sso/login?' + urlencode(DATA)
URL_GC_POST_AUTH = 'https://connect.garmin.com/modern/activities?'
URL_GC_PROFILE = 'https://connect.garmin.com/modern/profile'
URL_GC_USERSTATS = 'https://connect.garmin.com/modern/proxy/userstats-service/statistics/'
URL_GC_LIST = \
    'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
URL_GC_ACTIVITY = 'https://connect.garmin.com/modern/proxy/activity-service/activity/'
URL_GC_ACTIVITY_DETAIL = 'https://connect.garmin.com/modern/proxy/activity-service-1.3/json/activityDetails/'
URL_GC_DEVICE = 'https://connect.garmin.com/modern/proxy/device-service/deviceservice/app-info/'
URL_GC_ACT_PROPS = 'https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties'
URL_GC_EVT_PROPS = 'https://connect.garmin.com/modern/main/js/properties/event_types/event_types.properties'
URL_GC_GPX_ACTIVITY = \
    'https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/'
URL_GC_TCX_ACTIVITY = \
    'https://connect.garmin.com/modern/proxy/download-service/export/tcx/activity/'
URL_GC_ORIGINAL_ACTIVITY = 'http://connect.garmin.com/proxy/download-service/files/activity/'



def hhmmss_from_seconds(sec):
    """Helper function that converts seconds to HH:MM:SS time format."""
    if isinstance(sec, (float)) or isinstance(sec, (int)):
        formatted_time = str(timedelta(seconds=int(sec))).zfill(8)
    else:
        formatted_time = "0.000"
    return formatted_time


def kmh_from_mps(mps):
    """Helper function that converts meters per second (mps) to km/h."""
    return str(mps * 3.6)


def write_to_file(filename, content, mode):
    """Helper function that persists content to file."""
    write_file = open(filename, mode)
    write_file.write(content)
    write_file.close()


# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers={}):
    """Helper function that makes the HTTP requests."""
    request = urllib2.Request(url)
    # Tell Garmin we're some supported browser.
    request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, \
        like Gecko) Chrome/54.0.2816.0 Safari/537.36')
    for header_key, header_value in headers.iteritems():
        request.add_header(header_key, header_value)
    if post:
        # print "POSTING"
        post = urlencode(post)  # Convert dictionary to POST parameter string.
    # print(request.headers)
    # print(COOKIE_JAR)
    # print(post)
    # print(request)
    response = OPENER.open(request, data=post)  # This line may throw a urllib2.HTTPError.

    # N.B. urllib2 will follow any 302 redirects. Also, the "open" call above may throw a
    # urllib2.HTTPError which is checked for below.
    # print(response.getcode())
    if response.getcode() == 204:
        # For activities without GPS coordinates, there is no GPX download (204 = no content).
        # Write an empty file to prevent redownloading it.
        print('Writing empty file since there was no GPX activity data...')
        return ''
    elif response.getcode() != 200:
        raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

    return response.read()


# idea stolen from https://stackoverflow.com/a/31852401/3686
def load_properties(multiline, sep='=', comment_char='#', keys=[]):
    """
    Read a multiline string of properties (key/value pair separated by *sep*) into a dict

    :param multiline:    input string of properties
    :param sep:          separator between key and value
    :param comment_char: lines starting with this char are considered comments, not key/value pairs
    :param keys:         list to append the keys to
    :return:
    """
    props = {}
    for line in multiline.splitlines():
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith(comment_char):
            key_value = stripped_line.split(sep)
            key = key_value[0].strip()
            value = sep.join(key_value[1:]).strip().strip('"')
            props[key] = value
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
    else:
        return act[element]


def absent_or_null(element, act):
    """Return False only if act[element] is valid and not None"""
    if not act:
        return True
    elif element not in act:
        return True
    elif act[element]:
        return False
    else:
        return True


def from_activities_or_detail(element, act, detail, detail_container):
    """Return detail[detail_container][element] if valid and act[element] (or None) otherwise"""
    if absent_or_null(detail_container, detail) or absent_or_null(element, detail[detail_container]):
        return None if absent_or_null(element, act) else act[element]
    else:
        return detail[detail_container][element]


def trunc6(some_float):
    """Return the given float as string formatted with six digit precision"""
    return "{0:12.6f}".format(floor(some_float * 1000000) / 1000000).lstrip()


# A class building tzinfo objects for fixed-offset time zones.
# (copied from https://docs.python.org/2/library/datetime.html)
class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset, name):
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
    local_dt = datetime.strptime(time_local, "%Y-%m-%d %H:%M:%S")
    gmt_dt = datetime.strptime(time_gmt, "%Y-%m-%d %H:%M:%S")
    offset = local_dt - gmt_dt
    offset_tz = FixedOffset(offset.seconds / 60, "LCL")
    return local_dt.replace(tzinfo=offset_tz)


def pace_or_speed_raw(type_id, parent_type_id, mps):
    kmh = 3.6 * mps
    if (type_id in USES_PACE) or (parent_type_id in USES_PACE):
        return 60 / kmh
    else:
        return kmh


def pace_or_speed_formatted(type_id, parent_type_id, mps):
    kmh = 3.6 * mps
    if (type_id in USES_PACE) or (parent_type_id in USES_PACE):
        # format seconds per kilometer as MM:SS, see https://stackoverflow.com/a/27751293
        return '{0:02d}:{1:02d}'.format(*divmod(int(round(3600 / kmh)), 60))
    else:
        return "{0:.1f}".format(round(kmh, 1))


class CsvFilter():
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
        self.__writer.writeheader()

    def write_row(self):
        self.__writer.writerow(self.__current_row)
        self.__current_row = {}

    def set_column(self, name, value):
        if value and name in self.__csv_columns:
            # must encode in UTF-8 because the Python 'csv' module doesn't support unicode
            self.__current_row[self.__csv_headers[name]] = value.encode('utf8')



def parse_arguments(argv):
    """
    Setup the argument parser and parse the command line arguments.
    """
    current_date = datetime.now().strftime('%Y-%m-%d')
    activities_directory = './' + current_date + '_garmin_connect_export'

    parser = argparse.ArgumentParser()

    # TODO: Implement verbose and/or quiet options.
    # parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
    parser.add_argument('--version', help="print version and exit", action="store_true")
    parser.add_argument('--username', help="your Garmin Connect username or email address \
        (otherwise, you will be prompted)", nargs='?')
    parser.add_argument('--password', help="your Garmin Connect password (otherwise, you will be \
        prompted)", nargs='?')
    parser.add_argument('-c', '--count', nargs='?', default="1", help="number of recent activities to \
        download, or 'all' (default: 1)")
    parser.add_argument('-f', '--format', nargs='?', choices=['gpx', 'tcx', 'original', 'json'], default="gpx",
        help="export format; can be 'gpx', 'tcx', 'original' or 'json' (default: 'gpx')")
    parser.add_argument('-d', '--directory', nargs='?', default=activities_directory, help="the \
        directory to export to (default: './YYYY-MM-DD_garmin_connect_export')")
    parser.add_argument('-u', '--unzip', help="if downloading ZIP files (format: 'original'), unzip \
        the file and removes the ZIP file", action="store_true")
    parser.add_argument('-t', '--template', nargs='?', default=CSV_TEMPLATE, help="template \
        file with desired columns for CSV output")

    return parser.parse_args(argv[1:])


def login_to_garmin_connect(args):
    """
    Perform all HTTP requests to login to Garmin Connect.
    """
    username = args.username if args.username else raw_input('Username: ')
    password = args.password if args.password else getpass()

    print(urlencode(DATA))

    # Initially, we need to get a valid session cookie, so we pull the login page.
    print('Request login page')
    http_req(URL_GC_LOGIN)
    print('Finish login page')

    # Now we'll actually login.
    # Fields that are passed in a typical Garmin login.
    post_data = {
        'username': username,
        'password': password,
        'embed': 'true',
        'lt': 'e1s1',
        '_eventId': 'submit',
        'displayNameRequired': 'false'
    }

    print('Post login data')
    login_response = http_req(URL_GC_LOGIN, post_data)
    # write_to_file(args.directory + '/login-response.html', login_response, 'w')
    print('Finish login post')

    # extract the ticket from the login response
    pattern = re.compile(r".*\?ticket=([-\w]+)\";.*", re.MULTILINE | re.DOTALL)
    match = pattern.match(login_response)
    if not match:
        raise Exception('Did not get a ticket in the login response. Cannot log in. Did \
    you enter the correct username and password?')
    login_ticket = match.group(1)
    print('login ticket=' + login_ticket)

    print("Request authentication URL: " + URL_GC_POST_AUTH + 'ticket=' + login_ticket)
    http_req(URL_GC_POST_AUTH + 'ticket=' + login_ticket)
    print('Finished authentication')


def csv_write_record(csv_filter, extract, a, details, activity_type_name, event_type_name, device):

    type_id = 4 if absent_or_null('activityType', a) else a['activityType']['typeId']
    parent_type_id = 4 if absent_or_null('activityType', a) else a['activityType']['parentTypeId']
    if present(parent_type_id, PARENT_TYPE_ID):
        parent_type_key = PARENT_TYPE_ID[parent_type_id]
    else:
        parent_type_key = None
        print('Unknown parentType ' + str(parent_type_id) + ', please tell script author')

    # get some values from detail if present, from a otherwise
    start_latitude = from_activities_or_detail('startLatitude', a, details, 'summaryDTO')
    start_longitude = from_activities_or_detail('startLongitude', a, details, 'summaryDTO')
    end_latitude = from_activities_or_detail('endLatitude', a, details, 'summaryDTO')
    end_longitude = from_activities_or_detail('endLongitude', a, details, 'summaryDTO')

    csv_filter.set_column('id', str(a['activityId']))
    csv_filter.set_column('url', 'https://connect.garmin.com/modern/activity/' + str(a['activityId']))
    csv_filter.set_column('activityName', a['activityName'].replace('"', '""') if present('activityName', a) else None)
    csv_filter.set_column('description', a['description'].replace('"', '""') if present('description', a) else None)
    csv_filter.set_column('startTimeIso', extract['start_time_with_offset'].isoformat())
    csv_filter.set_column('startTime1123', extract['start_time_with_offset'].strftime(ALMOST_RFC_1123))
    csv_filter.set_column('startTimeMillis', str(a['beginTimestamp']) if present('beginTimestamp', a) else None)
    csv_filter.set_column('startTimeRaw', details['summaryDTO']['startTimeLocal'] if present('startTimeLocal', details['summaryDTO']) else None)
    csv_filter.set_column('endTimeIso', extract['end_time_with_offset'].isoformat() if extract['end_time_with_offset'] else None)
    csv_filter.set_column('endTime1123', extract['end_time_with_offset'].strftime(ALMOST_RFC_1123) if extract['end_time_with_offset'] else None)
    csv_filter.set_column('endTimeMillis', str(a['beginTimestamp']+extract['elapsed_seconds']*1000) if present('beginTimestamp', a) else None)
    csv_filter.set_column('durationRaw', str(a['duration']) if present('duration', a) else None)
    csv_filter.set_column('duration', hhmmss_from_seconds(a['duration']) if present('duration', a) else None)
    csv_filter.set_column('elapsedDurationRaw', str(round(extract['elapsed_duration'], 3)) if extract['elapsed_duration'] else None)
    csv_filter.set_column('elapsedDuration', hhmmss_from_seconds(round(extract['elapsed_duration'])) if extract['elapsed_duration'] else None)
    csv_filter.set_column('movingDurationRaw', str(details['summaryDTO']['movingDuration']) if present('movingDuration', details['summaryDTO']) else None)
    csv_filter.set_column('movingDuration', hhmmss_from_seconds(details['summaryDTO']['movingDuration']) if present('movingDuration', details['summaryDTO']) else None)
    csv_filter.set_column('distanceRaw', "{0:.5f}".format(a['distance'] / 1000) if present('distance', a) else None)
    csv_filter.set_column('averageSpeedRaw', kmh_from_mps(details['summaryDTO']['averageSpeed']) if present('averageSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('averageSpeedPaceRaw', trunc6(pace_or_speed_raw(type_id, parent_type_id, a['averageSpeed'])) if present('averageSpeed', a) else None)
    csv_filter.set_column('averageSpeedPace', pace_or_speed_formatted(type_id, parent_type_id, a['averageSpeed']) if present('averageSpeed', a) else None)
    csv_filter.set_column('averageMovingSpeedRaw', kmh_from_mps(details['summaryDTO']['averageMovingSpeed']) if present('averageMovingSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('averageMovingSpeedPaceRaw', trunc6(pace_or_speed_raw(type_id, parent_type_id, details['summaryDTO']['averageMovingSpeed'])) if present('averageMovingSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('averageMovingSpeedPace', pace_or_speed_formatted(type_id, parent_type_id, details['summaryDTO']['averageMovingSpeed']) if present('averageMovingSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('maxSpeedRaw', kmh_from_mps(details['summaryDTO']['maxSpeed']) if present('maxSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('maxSpeedPaceRaw', trunc6(pace_or_speed_raw(type_id, parent_type_id, details['summaryDTO']['maxSpeed'])) if present('maxSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('maxSpeedPace', pace_or_speed_formatted(type_id, parent_type_id, details['summaryDTO']['maxSpeed']) if present('maxSpeed', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLoss', str(round(details['summaryDTO']['elevationLoss'], 2)) if present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLossUncorr', str(round(details['summaryDTO']['elevationLoss'], 2)) if not a['elevationCorrected'] and present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationLossCorr', str(round(details['summaryDTO']['elevationLoss'], 2)) if a['elevationCorrected'] and present('elevationLoss', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGain', str(round(details['summaryDTO']['elevationGain'], 2)) if present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGainUncorr', str(round(details['summaryDTO']['elevationGain'], 2)) if not a['elevationCorrected'] and present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('elevationGainCorr', str(round(details['summaryDTO']['elevationGain'], 2)) if a['elevationCorrected'] and present('elevationGain', details['summaryDTO']) else None)
    csv_filter.set_column('minElevation', str(round(details['summaryDTO']['minElevation'], 2)) if present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('minElevationUncorr', str(round(details['summaryDTO']['minElevation'], 2)) if not a['elevationCorrected'] and present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('minElevationCorr', str(round(details['summaryDTO']['minElevation'], 2)) if a['elevationCorrected'] and present('minElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevation', str(round(details['summaryDTO']['maxElevation'], 2)) if present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevationUncorr', str(round(details['summaryDTO']['maxElevation'], 2)) if not a['elevationCorrected'] and present('maxElevation', details['summaryDTO']) else None)
    csv_filter.set_column('maxElevationCorr', str(round(details['summaryDTO']['maxElevation'], 2)) if a['elevationCorrected'] and present('maxElevation', details['summaryDTO']) else None)
    # csv_record += empty_record  # no minimum heart rate in JSON
    csv_filter.set_column('maxHRRaw', str(details['summaryDTO']['maxHR']) if present('maxHR', details['summaryDTO']) else None)
    csv_filter.set_column('maxHR', "{0:.0f}".format(a['maxHR']) if present('maxHR', a) else None)
    csv_filter.set_column('averageHRRaw', str(details['summaryDTO']['averageHR']) if present('averageHR', details['summaryDTO']) else None)
    csv_filter.set_column('averageHR', "{0:.0f}".format(a['averageHR']) if present('averageHR', a) else None)
    csv_filter.set_column('caloriesRaw', str(details['summaryDTO']['calories']) if present('calories', details['summaryDTO']) else None)
    csv_filter.set_column('calories', "{0:.0f}".format(details['summaryDTO']['calories']) if present('calories', details['summaryDTO']) else None)
    csv_filter.set_column('averageCadence', str(a['averageBikingCadenceInRevPerMinute']) if present('averageBikingCadenceInRevPerMinute', a) else None)
    csv_filter.set_column('maxCadence', str(a['maxBikingCadenceInRevPerMinute']) if present('maxBikingCadenceInRevPerMinute', a) else None)
    csv_filter.set_column('strokes', str(a['strokes']) if present('strokes', a) else None)
    csv_filter.set_column('averageTemperature', str(details['summaryDTO']['averageTemperature']) if present('averageTemperature', details['summaryDTO']) else None)
    csv_filter.set_column('minTemperature', str(details['summaryDTO']['minTemperature']) if present('minTemperature', details['summaryDTO']) else None)
    csv_filter.set_column('maxTemperature', str(details['summaryDTO']['maxTemperature']) if present('maxTemperature', details['summaryDTO']) else None)
    csv_filter.set_column('device', device['productDisplayName'].replace('"', '""') + ' ' + device['versionString'] if present('productDisplayName', device) else None)
    csv_filter.set_column('activityTypeKey', a['activityType']['typeKey'].title() if present('typeKey', a['activityType']) else None)
    csv_filter.set_column('activityType', value_if_found_else_key(activity_type_name, 'activity_type_' + a['activityType']['typeKey']) if present('activityType', a) else None)
    csv_filter.set_column('activityParent', value_if_found_else_key(activity_type_name, 'activity_type_' + parent_type_key) if parent_type_key else None)
    csv_filter.set_column('eventTypeKey', a['eventType']['typeKey'].title() if present('typeKey', a['eventType']) else None)
    csv_filter.set_column('eventType', value_if_found_else_key(event_type_name, a['eventType']['typeKey']) if present('eventType', a) else None)
    csv_filter.set_column('tz', details['timeZoneUnitDTO']['timeZone'] if present('timeZone', details['timeZoneUnitDTO']) else None)
    csv_filter.set_column('tzOffset', extract['start_time_with_offset'].isoformat()[-6:])
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


def export_data_file(activity_id, activity_details, args):
    if args.format == 'gpx':
        data_filename = args.directory + '/activity_' + activity_id + '.gpx'
        download_url = URL_GC_GPX_ACTIVITY + activity_id + '?full=true'
        # download_url = URL_GC_GPX_ACTIVITY + activity_id + '?full=true' + '&original=true'
        print(download_url)
        file_mode = 'w'
    elif args.format == 'tcx':
        data_filename = args.directory + '/activity_' + activity_id + '.tcx'
        download_url = URL_GC_TCX_ACTIVITY + activity_id + '?full=true'
        file_mode = 'w'
    elif args.format == 'original':
        data_filename = args.directory + '/activity_' + activity_id + '.zip'
        fit_filename = args.directory + '/' + activity_id + '.fit'
        download_url = URL_GC_ORIGINAL_ACTIVITY + activity_id
        file_mode = 'wb'
    elif args.format == 'json':
        data_filename = args.directory + '/activity_' + activity_id + '.json'
        file_mode = 'w'
    else:
        raise Exception('Unrecognized format.')

    if isfile(data_filename):
        print('\tData file already exists; skipping...')
        return

    # Regardless of unzip setting, don't redownload if the ZIP or FIT file exists.
    if args.format == 'original' and isfile(fit_filename):
        print('\tFIT data file already exists; skipping...')
        return

    if args.format != 'json':
        # Download the data file from Garmin Connect. If the download fails (e.g., due to timeout),
        # this script will die, but nothing will have been written to disk about this activity, so
        # just running it again should pick up where it left off.
        print('\tDownloading file...')

        try:
            data = http_req(download_url)
        except urllib2.HTTPError as e:
            # Handle expected (though unfortunate) error codes; die on unexpected ones.
            if e.code == 500 and args.format == 'tcx':
                # Garmin will give an internal server error (HTTP 500) when downloading TCX files
                # if the original was a manual GPX upload. Writing an empty file prevents this file
                # from being redownloaded, similar to the way GPX files are saved even when there
                # are no tracks. One could be generated here, but that's a bit much. Use the GPX
                # format if you want actual data in every file, as I believe Garmin provides a GPX
                # file for every activity.
                print('Writing empty file since Garmin did not generate a TCX file for this \
                            activity...')
                data = ''
            elif e.code == 404 and args.format == 'original':
                # For manual activities (i.e., entered in online without a file upload), there is
                # no original file. # Write an empty file to prevent redownloading it.
                print('Writing empty file since there was no original activity data...')
                data = ''
            else:
                raise Exception('Failed. Got an unexpected HTTP error (' + str(e.code) + download_url + ').')
    else:
        data = activity_details

    # Persist file
    write_to_file(data_filename, data, file_mode)
    if args.format == 'gpx' and data:
        # Validate GPX data. If we have an activity without GPS data (e.g., running on a
        # treadmill). Garmin Connect still kicks out a GPX (sometimes), but there is only activity
        # information, no GPS data. N.B. You can omit the XML parse (and the associated log
        # messages) to speed things up.
        gpx = parseString(data)
        gpx_data_exists = len(gpx.getElementsByTagName('trkpt')) > 0

        if gpx_data_exists:
            print('Done. GPX data saved.')
        else:
            print('Done. No track points found.')
    elif args.format == 'original':
        # Even manual upload of a GPX file is zipped, but we'll validate the extension.
        if args.unzip and data_filename[-3:].lower() == 'zip':
            print("Unzipping and removing original files...")
            print('Filesize is: ' + str(stat(data_filename).st_size))
            if stat(data_filename).st_size > 0:
                zip_file = open(data_filename, 'rb')
                z = zipfile.ZipFile(zip_file)
                for name in z.namelist():
                    z.extract(name, args.directory)
                zip_file.close()
            else:
                print('Skipping 0Kb zip file.')
            remove(data_filename)
        print('Done.')
    elif args.format == 'json':
        # print nothing here
        pass
    else:
        # TODO: Consider validating other formats.
        print('Done.')


def main(argv):
    """
    Main entry point for gcexport.py
    """
    args = parse_arguments(argv)
    if args.version:
        print(argv[0] + ", version " + SCRIPT_VERSION)
        exit(0)

    print('Welcome to Garmin Connect Exporter!')

    # Create directory for data files.
    if isdir(args.directory):
        print('Warning: Output directory already exists. Will skip already-downloaded files and \
            append to the CSV file.')

    login_to_garmin_connect(args)

    # We should be logged in now.
    if not isdir(args.directory):
        mkdir(args.directory)

    csv_filename = args.directory + '/activities.csv'
    csv_existed = isfile(csv_filename)

    csv_file = open(csv_filename, 'a')
    csv_filter = CsvFilter(csv_file, args.template)

    # Write header to CSV file
    if not csv_existed:
        csv_filter.write_header()

    if args.count == 'all':
        # If the user wants to download all activities, query the userstats
        # on the profile page to know how many are available
        print("Getting display name and user stats ~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(URL_GC_PROFILE)
        profile_page = http_req(URL_GC_PROFILE)
        # write_to_file(args.directory + '/profile.html', profile_page, 'a')

        # extract the display name from the profile page, it should be in there as
        # \"displayName\":\"John.Doe\"
        pattern = re.compile(r".*\\\"displayName\\\":\\\"([-.\w]+)\\\".*", re.MULTILINE | re.DOTALL)
        match = pattern.match(profile_page)
        if not match:
            raise Exception('Did not find the display name in the profile page.')
        display_name = match.group(1)
        print('displayName=' + display_name)

        print(URL_GC_USERSTATS + display_name)
        result = http_req(URL_GC_USERSTATS + display_name)
        print("Finished display name and user stats ~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        # Persist JSON
        write_to_file(args.directory + '/userstats.json', result, 'w')

        # Modify total_to_download based on how many activities the server reports.
        json_results = json.loads(result)  # TODO: Catch possible exceptions here.
        total_to_download = int(json_results['userMetrics'][0]['totalActivities'])
    else:
        total_to_download = int(args.count)
    total_downloaded = 0

    device_dict = dict()

    # load some dictionaries with lookup data from REST services
    activity_type_props = http_req(URL_GC_ACT_PROPS)
    # write_to_file(args.directory + '/activity_types.properties', activity_type_props, 'a')
    activity_type_name = load_properties(activity_type_props)
    event_type_props = http_req(URL_GC_EVT_PROPS)
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
        print("Making activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(URL_GC_LIST + urlencode(search_params))
        result = http_req(URL_GC_LIST + urlencode(search_params))
        print("Finished activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        # Persist JSON
        write_to_file(args.directory + '/activities.json', result, 'a')

        json_results = json.loads(result)  # TODO: Catch possible exceptions here.

        # search = json_results['results']['search']

        # Pull out just the list of activities.
        activities = json_results

        # Process each activity.
        for a in activities:
            # Display which entry we're working on.
            print('Garmin Connect activity: [' + str(a['activityId']) + '] ', end='')
            print(a['activityName'])

            # Retrieve also the detail data from the activity (the one displayed on
            # the https://connect.garmin.com/modern/activity/xxx page), because some
            # data are missing from 'a' (or are even different, e.g. for my activities
            # 86497297 or 86516281)
            activity_details = None
            details = None
            tries = MAX_TRIES
            while tries > 0:
                activity_details = http_req(URL_GC_ACTIVITY + str(a['activityId']))
                details = json.loads(activity_details)
                # I observed a failure to get a complete JSON detail in about 5-10 calls out of 1000
                # retrying then statistically gets a better JSON ;-)
                if len(details['summaryDTO']) > 0:
                    tries = 0
                else:
                    print('retrying for ' + str(a['activityId']))
                    tries -= 1
                    if tries == 0:
                        raise Exception('Didn\'t get "summaryDTO" after ' + str(MAX_TRIES) + ' tries for ' + str(a['activityId']))

            extract = {}
            extract['start_time_with_offset'] = offset_date_time(a['startTimeLocal'], a['startTimeGMT'])
            elapsed_duration = details['summaryDTO']['elapsedDuration'] if 'summaryDTO' in details and 'elapsedDuration' in details['summaryDTO'] else None
            extract['elapsed_duration'] = elapsed_duration if elapsed_duration else a['duration']
            extract['elapsed_seconds'] = int(round(extract['elapsed_duration']))
            extract['end_time_with_offset'] = extract['start_time_with_offset'] + timedelta(seconds=extract['elapsed_seconds'])

            print('\t' + extract['start_time_with_offset'].isoformat() + ', ', end='')
            print(hhmmss_from_seconds(extract['elapsed_seconds']) + ', ', end='')
            if 'distance' in a and isinstance(a['distance'], (float)):
                print("{0:.3f}".format(a['distance'] / 1000) + 'km')
            else:
                print('0.000 km')

            # try to get the device details (and cache them, as they're used for multiple activities)
            device = None
            device_app_inst_id = None if absent_or_null('metadataDTO', details) else details['metadataDTO']['deviceApplicationInstallationId']
            if device_app_inst_id:
                if not device_dict.has_key(device_app_inst_id):
                    # print '\tGetting device details ' + str(device_app_inst_id)
                    device_details = http_req(URL_GC_DEVICE + str(device_app_inst_id))
                    write_to_file(args.directory + '/device_' + str(device_app_inst_id) + '.json', device_details, 'a')
                    device_dict[device_app_inst_id] = None if not device_details else json.loads(device_details)
                device = device_dict[device_app_inst_id]

            # try to get the JSON with all the samples (not all activities have it...)
            extract['samples'] = None
            try:
                activity_measurements = http_req(URL_GC_ACTIVITY_DETAIL + str(a['activityId']))
                write_to_file(args.directory + '/activity_' + str(a['activityId']) + '_samples.json', activity_measurements, 'w')
                samples = json.loads(activity_measurements)
                if present('com.garmin.activity.details.json.ActivityDetails', samples):
                    extract['samples'] = samples['com.garmin.activity.details.json.ActivityDetails']
            except Exception as e:
                print('Unable to get samples for ' + str(a['activityId']))

            # Write stats to CSV.
            csv_write_record(csv_filter, extract, a, details, activity_type_name, event_type_name, device)

            export_data_file(str(a['activityId']), activity_details, args)

        total_downloaded += num_to_download
    # End while loop for multiple chunks.

    csv_file.close()

    print('Open CSV output.')
    print(csv_filename)
    # open CSV file. Comment this line out if you don't want this behavior
    # call(["/usr/bin/libreoffice6.0", "--calc", csv_filename])

    print('Done!')


if __name__ == "__main__":
    main(sys.argv)
