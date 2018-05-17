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
import json
import re
import sys
import urllib2
import zipfile

SCRIPT_VERSION = '2.0.0'

COOKIE_JAR = cookielib.CookieJar()
OPENER = urllib2.build_opener(urllib2.HTTPCookieProcessor(COOKIE_JAR))


# print cookie_jar

def hhmmss_from_seconds(sec):
    """Helper function that converts seconds to HH:MM:SS time format."""
    if isinstance(sec, (float)):
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
def load_properties(multiline, sep='=', comment_char='#'):
    """
    Read a multiline string of properties (key/value pair separated by *sep*) into a dict

    :param multiline: input string of properties
    :param sep:       separator between key and value
    :param comment_char: lines starting with this chara are considered comments, not key/value pairs
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
    return props


def value_if_found_else_key(some_dict, key):
    """Lookup a value in some_dict and use the key itself as fallback"""
    return some_dict.get(key, key)


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
    17: 'any activity type',
    26: 'swimming',
    29: 'fitness equipment',
    71: 'motorcycling',
    83: 'transition',
    144: 'diving',
    149: 'yoga'
}

# typeId values using pace instead of speed
USES_PACE = Set([1, 3, 9])  # running, hiking, walking


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


def main(argv):
    current_date = datetime.now().strftime('%Y-%m-%d')
    activities_directory = './' + current_date + '_garmin_connect_export'

    parser = argparse.ArgumentParser()

    # TODO: Implement verbose and/or quiet options.
    # parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
    parser.add_argument('--version', help="print version and exit", action="store_true")
    parser.add_argument('--username', help="your Garmin Connect username (otherwise, you will be \
        prompted)", nargs='?')
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

    args = parser.parse_args(argv[1:])

    if args.version:
        print(argv[0] + ", version " + SCRIPT_VERSION)
        exit(0)

    print('Welcome to Garmin Connect Exporter!')

    # Create directory for data files.
    if isdir(args.directory):
        print('Warning: Output directory already exists. Will skip already-downloaded files and \
            append to the CSV file.')

    username = args.username if args.username else input('Username: ')
    password = args.password if args.password else getpass()

    # Maximum number of activities you can request at once.
    # Used to be 100 and enforced by Garmin for older endpoints; for the current endpoint 'URL_GC_LIST'
    # the limit is not known (I have less than 1000 activities and could get them all in one go)
    LIMIT_MAXIMUM = 1000

    MAX_TRIES = 3

    WEBHOST = "https://connect.garmin.com"
    REDIRECT = "https://connect.garmin.com/post-auth/login"
    BASE_URL = "http://connect.garmin.com/en-US/signin"
    GAUTH = "http://connect.garmin.com/gauth/hostname"
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

    print(urlencode(DATA))

    # URLs for various services.
    URL_GC_LOGIN = 'https://sso.garmin.com/sso/login?' + urlencode(DATA)
    URL_GC_POST_AUTH = 'https://connect.garmin.com/modern/activities?'
    URL_GC_SEARCH = 'https://connect.garmin.com/proxy/activity-search-service-1.2/json/activities?start=0&limit=1'
    URL_GC_LIST = \
        'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
    URL_GC_ACTIVITY = 'https://connect.garmin.com/modern/proxy/activity-service/activity/'
    url_gc_device = 'https://connect.garmin.com/modern/proxy/device-service/deviceservice/app-info/'
    url_gc_act_props = 'https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties'
    url_gc_evt_props = 'https://connect.garmin.com/modern/main/js/properties/event_types/event_types.properties'
    URL_GC_GPX_ACTIVITY = \
        'https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/'
    URL_GC_TCX_ACTIVITY = \
        'https://connect.garmin.com/modern/proxy/download-service/export/tcx/activity/'
    URL_GC_ORIGINAL_ACTIVITY = 'http://connect.garmin.com/proxy/download-service/files/activity/'

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

    # We should be logged in now.
    if not isdir(args.directory):
        mkdir(args.directory)

    csv_filename = args.directory + '/activities.csv'
    csv_existed = isfile(csv_filename)

    csv_file = open(csv_filename, 'a')

    # Write header to CSV file
    if not csv_existed:
        csv_file.write('Activity name,\
    Description,\
    Begin timestamp,\
    Duration (h:m:s),\
    Moving duration (h:m:s),\
    Distance (km),\
    Average speed (km/h or min/km),\
    Average moving speed (km/h or min/km),\
    Max. speed (km/h or min/km),\
    Elevation loss uncorrected (m),\
    Elevation gain uncorrected (m),\
    Elevation min. uncorrected (m),\
    Elevation max. uncorrected (m),\
    Min. heart rate (bpm),\
    Max. heart rate (bpm),\
    Average heart rate (bpm),\
    Calories,\
    Avg. cadence (rpm),\
    Max. cadence (rpm),\
    Strokes,\
    Avg. temp (°C),\
    Min. temp (°C),\
    Max. temp (°C),\
    Map,\
    End timestamp,\
    Begin timestamp (ms),\
    End timestamp (ms),\
    Device,\
    Activity type,\
    Event type,\
    Time zone,\
    Begin latitude (°DD),\
    Begin longitude (°DD),\
    End latitude (°DD),\
    End longitude (°DD),\
    Elevation gain corrected (m),\
    Elevation loss corrected (m),\
    Elevation max. corrected (m),\
    Elevation min. corrected (m),\
    Sample count\n')

    if args.count == 'all':
        # If the user wants to download all activities, first download one,
        # then the result of that request will tell us how many are available
        # so we will modify the variables then.
        print("Making result summary request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(URL_GC_SEARCH)
        result = http_req(URL_GC_SEARCH)
        print("Finished result summary request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        # Persist JSON
        write_to_file(args.directory + '/activities-summary.json', result, 'a')

        # Modify total_to_download based on how many activities the server reports.
        json_results = json.loads(result)  # TODO: Catch possible exceptions here.
        total_to_download = int(json_results['results']['totalFound'])
    else:
        total_to_download = int(args.count)
    total_downloaded = 0

    device_dict = dict()

    # load some dictionaries with lookup data from REST services
    activityTypeProps = http_req(url_gc_act_props)
    # write_to_file(args.directory + '/activity_types.properties', activityTypeProps, 'a')
    activityTypeName = load_properties(activityTypeProps)
    eventTypeProps = http_req(url_gc_evt_props)
    # write_to_file(args.directory + '/event_types.properties', eventTypeProps, 'a')
    eventTypeName = load_properties(eventTypeProps)

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

            parentTypeId = 4 if absent_or_null('activityType', a) else a['activityType']['parentTypeId']
            typeId = 4 if absent_or_null('activityType', a) else a['activityType']['typeId']

            startTimeWithOffset = offset_date_time(a['startTimeLocal'], a['startTimeGMT'])
            elapsedDuration = details['summaryDTO']['elapsedDuration'] if 'summaryDTO' in details and 'elapsedDuration' in details['summaryDTO'] else None
            duration = elapsedDuration if elapsedDuration else a['duration']
            durationSeconds = int(round(duration))
            endTimeWithOffset = startTimeWithOffset + timedelta(seconds=durationSeconds) if duration else None

            # get some values from detail if present, from a otherwise
            startLatitude = from_activities_or_detail('startLatitude', a, details, 'summaryDTO')
            startLongitude = from_activities_or_detail('startLongitude', a, details, 'summaryDTO')
            endLatitude = from_activities_or_detail('endLatitude', a, details, 'summaryDTO')
            endLongitude = from_activities_or_detail('endLongitude', a, details, 'summaryDTO')

            print('\t' + startTimeWithOffset.isoformat() + ', ', end='')
            if 'duration' in a:
                print(hhmmss_from_seconds(a['duration']) + ', ', end='')
            else:
                print('??:??:??, ', end='')
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
                    device_details = http_req(url_gc_device + str(device_app_inst_id))
                    write_to_file(args.directory + '/device_' + str(device_app_inst_id) + '.json', device_details, 'a')
                    device_dict[device_app_inst_id] = None if not device_details else json.loads(device_details)
                device = device_dict[device_app_inst_id]

            if args.format == 'gpx':
                data_filename = args.directory + '/activity_' + str(a['activityId']) + '.gpx'
                download_url = URL_GC_GPX_ACTIVITY + str(a['activityId']) + '?full=true'
                # download_url = URL_GC_GPX_ACTIVITY + str(a['activityId']) + '?full=true' + '&original=true'
                print(download_url)
                file_mode = 'w'
            elif args.format == 'tcx':
                data_filename = args.directory + '/activity_' + str(a['activityId']) + '.tcx'
                download_url = URL_GC_TCX_ACTIVITY + str(a['activityId']) + '?full=true'
                file_mode = 'w'
            elif args.format == 'original':
                data_filename = args.directory + '/activity_' + str(a['activityId']) + '.zip'
                fit_filename = args.directory + '/' + str(a['activityId']) + '.fit'
                download_url = URL_GC_ORIGINAL_ACTIVITY + str(a['activityId'])
                file_mode = 'wb'
            elif args.format == 'json':
                data_filename = args.directory + '/activity_' + str(a['activityId']) + '.json'
                file_mode = 'w'
            else:
                raise Exception('Unrecognized format.')

            if isfile(data_filename):
                print('\tData file already exists; skipping...')
                continue
            # Regardless of unzip setting, don't redownload if the ZIP or FIT file exists.
            if args.format == 'original' and isfile(fit_filename):
                print('\tFIT data file already exists; skipping...')
                continue

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

            # Write stats to CSV.
            empty_record = '"",'
            csv_record = ''

            csv_record += empty_record if absent_or_null('activityName', a) else '"' + a['activityName'].replace('"', '""') + '",'
            csv_record += empty_record if absent_or_null('description', a) else '"' + a['description'].replace('"', '""') + '",'
            csv_record += '"' + startTimeWithOffset.strftime(ALMOST_RFC_1123) + '",'
            # csv_record += '"' + startTimeWithOffset.isoformat() + '",'
            csv_record += empty_record if not duration else hhmmss_from_seconds(round(duration)) + ','
            csv_record += empty_record if absent_or_null('movingDuration', details['summaryDTO']) else hhmmss_from_seconds(details['summaryDTO']['movingDuration']) + ','
            csv_record += empty_record if absent_or_null('distance', a) else '"' + "{0:.5f}".format(a['distance']/1000) + '",'
            csv_record += empty_record if absent_or_null('averageSpeed', a) else '"' + trunc6(pace_or_speed_raw(typeId, parentTypeId, a['averageSpeed'])) + '",'
            csv_record += empty_record if absent_or_null('averageMovingSpeed', details['summaryDTO']) else '"' + trunc6(pace_or_speed_raw(typeId, parentTypeId, details['summaryDTO']['averageMovingSpeed'])) + '",'
            csv_record += empty_record if absent_or_null('maxSpeed', details['summaryDTO']) else '"' + trunc6(pace_or_speed_raw(typeId, parentTypeId, details['summaryDTO']['maxSpeed'])) + '",'
            csv_record += empty_record if a['elevationCorrected'] or absent_or_null('elevationLoss', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['elevationLoss'], 2)) + '",'
            csv_record += empty_record if a['elevationCorrected'] or absent_or_null('elevationGain', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['elevationGain'], 2)) + '",'
            csv_record += empty_record if a['elevationCorrected'] or absent_or_null('minElevation', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['minElevation'], 2)) + '",'
            csv_record += empty_record if a['elevationCorrected'] or absent_or_null('maxElevation', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['maxElevation'], 2)) + '",'
            csv_record += empty_record  # no minimum heart rate in JSON
            csv_record += empty_record if absent_or_null('maxHR', a) else '"' + "{0:.0f}".format(a['maxHR']) + '",'
            csv_record += empty_record if absent_or_null('averageHR', a) else '"' + "{0:.0f}".format(a['averageHR']) + '",'
            csv_record += empty_record if absent_or_null('calories', details['summaryDTO']) else '"' + str(details['summaryDTO']['calories']) + '",'
            csv_record += empty_record if absent_or_null('averageBikingCadenceInRevPerMinute', a) else '"' + str(a['averageBikingCadenceInRevPerMinute']) + '",'
            csv_record += empty_record if absent_or_null('maxBikingCadenceInRevPerMinute', a) else '"' + str(a['maxBikingCadenceInRevPerMinute']) + '",'
            csv_record += empty_record if absent_or_null('strokes', a) else '"' + str(a['strokes']) + '",'
            csv_record += empty_record if absent_or_null('averageTemperature', details['summaryDTO']) else '"' + str(details['summaryDTO']['averageTemperature']) + '",'
            csv_record += empty_record if absent_or_null('minTemperature', details['summaryDTO']) else '"' + str(details['summaryDTO']['minTemperature']) + '",'
            csv_record += empty_record if absent_or_null('maxTemperature', details['summaryDTO']) else '"' + str(details['summaryDTO']['maxTemperature']) + '",'
            csv_record += '"https://connect.garmin.com/modern/activity/' + str(a['activityId']) + '",'
            csv_record += empty_record if not endTimeWithOffset else '"' + endTimeWithOffset.strftime(ALMOST_RFC_1123) + '",'
            csv_record += empty_record if not startTimeWithOffset else '"' + startTimeWithOffset.isoformat() + '",'
            # csv_record += empty_record if absent_or_null('beginTimestamp', a) else '"' + str(a['beginTimestamp']) + '",'
            csv_record += empty_record if not endTimeWithOffset else '"' + endTimeWithOffset.isoformat() + '",'
            # csv_record += empty_record if absent_or_null('beginTimestamp', a) else '"' + str(a['beginTimestamp']+durationSeconds*1000) + '",'
            csv_record += empty_record if absent_or_null('productDisplayName', device) else '"' + device['productDisplayName'].replace('"', '""') + ' ' + device['versionString'] + '",'
            csv_record += empty_record if absent_or_null('activityType', a) else '"' + value_if_found_else_key(activityTypeName, 'activity_type_' + a['activityType']['typeKey']) + '",'
            csv_record += empty_record if absent_or_null('eventType', a) else '"' + value_if_found_else_key(eventTypeName, a['eventType']['typeKey']) + '",'
            csv_record += '"' + startTimeWithOffset.isoformat()[-6:] + '",'
            csv_record += empty_record if not startLatitude else '"' + trunc6(startLatitude) + '",'
            csv_record += empty_record if not startLongitude else '"' + trunc6(startLongitude) + '",'
            csv_record += empty_record if not endLatitude else '"' + trunc6(endLatitude) + '",'
            csv_record += empty_record if not endLongitude else '"' + trunc6(endLongitude) + '",'
            csv_record += empty_record if not a['elevationCorrected'] or absent_or_null('elevationGain', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['elevationGain'], 2)) + '",'
            csv_record += empty_record if not a['elevationCorrected'] or absent_or_null('elevationLoss', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['elevationLoss'], 2)) + '",'
            csv_record += empty_record if not a['elevationCorrected'] or absent_or_null('maxElevation', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['maxElevation'], 2)) + '",'
            csv_record += empty_record if not a['elevationCorrected'] or absent_or_null('minElevation', details['summaryDTO']) else '"' + str(round(details['summaryDTO']['minElevation'], 2)) + '",'
            csv_record += '""'  # no Sample Count in JSON
            csv_record += '\n'

            csv_file.write(csv_record.encode('utf8'))

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
