#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
File: gcexport.py
Original author: Kyle Krafka (https://github.com/kjkjava/)
Date: April 28, 2015
Fork author: Michael P (https://github.com/moderation/)
Date: February 15, 2018

Description:    Use this script to export your fitness data from Garmin Connect.
                See README.md for more information.

Activity & event types:
    https://connect.garmin.com/modern/main/js/properties/event_types/event_types.properties
    https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties
"""

from datetime import datetime, timedelta
from getpass import getpass
from os import mkdir, remove, stat
from os.path import isdir, isfile
from subprocess import call
from sys import argv
from xml.dom.minidom import parseString

import argparse
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SCRIPT_VERSION = '1.0.0'
CURRENT_DATE = datetime.now().strftime('%Y-%m-%d')
ACTIVITIES_DIRECTORY = './' + CURRENT_DATE + '_garmin_connect_export'

PARSER = argparse.ArgumentParser()

# TODO: Implement verbose and/or quiet options.
# PARSER.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
PARSER.add_argument('--version', help="print version and exit", action="store_true")
PARSER.add_argument('--username', help="your Garmin Connect username (otherwise, you will be \
    prompted)", nargs='?')
PARSER.add_argument('--password', help="your Garmin Connect password (otherwise, you will be \
    prompted)", nargs='?')

PARSER.add_argument('-c', '--count', nargs='?', default="1", help="number of recent activities to \
    download, or 'all' (default: 1)")

PARSER.add_argument('-f', '--format', nargs='?', choices=['gpx', 'tcx', 'original'], default="gpx",
                    help="export format; can be 'gpx', 'tcx', or 'original' (default: 'gpx')")

PARSER.add_argument('-d', '--directory', nargs='?', default=ACTIVITIES_DIRECTORY, help="the \
    directory to export to (default: './YYYY-MM-DD_garmin_connect_export')")

PARSER.add_argument('-u', '--unzip', help="if downloading ZIP files (format: 'original'), unzip \
    the file and removes the ZIP file", action="store_true")

ARGS = PARSER.parse_args()

if ARGS.version:
    print(argv[0] + ", version " + SCRIPT_VERSION)
    exit(0)

COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))
# print(COOKIE_JAR)

def hhmmss_from_seconds(sec):
    """Helper function that converts seconds to HH:MM:SS time format."""
    return str(timedelta(seconds=int(sec))).zfill(8)

def kmh_from_mps(mps):
    """Helper function that converts meters per second (mps) to km/h."""
    return str(mps * 3.6)

def write_to_file(filename, content, mode):
    """Helper function that persists content to file."""
    write_file = open(filename, mode)
    write_file.write(content)
    write_file.close()

# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers=None):
    """Helper function that makes the HTTP requests."""
    request = urllib.request.Request(url)
    # Tell Garmin we're some supported browser.
    request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, \
        like Gecko) Chrome/54.0.2816.0 Safari/537.36')
    if headers:
        for header_key, header_value in headers.items():
            request.add_header(header_key, header_value)
    if post:
        # print('POSTING')
        post = urllib.parse.urlencode(post)
        post = post.encode('utf-8')  # Convert dictionary to POST parameter string.
    # print(request.headers)
    # print(COOKIE_JAR)
    # print(post)
    # print(request)
    response = OPENER.open(request, data=post)  # This line may throw a urllib2.HTTPError.

    # N.B. urllib2 will follow any 302 redirects. Also, the "open" call above may throw a
    # urllib2.HTTPError which is checked for below.
    # print(response.getcode())
    if response.getcode() != 200:
        raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

    return response.read()

print('Welcome to Garmin Connect Exporter!')

# Create directory for data files.
if isdir(ARGS.directory):
    print('Warning: Output directory already exists. Will skip already-downloaded files and \
        append to the CSV file.')

USERNAME = ARGS.username if ARGS.username else input('Username: ')
PASSWORD = ARGS.password if ARGS.password else getpass()

# Maximum number of activities you can request at once.  Set and enforced by Garmin.
LIMIT_MAXIMUM = 1000

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

print(urllib.parse.urlencode(DATA))

# URLs for various services.
URL_GC_LOGIN = 'https://sso.garmin.com/sso/login?' + urllib.parse.urlencode(DATA)
URL_GC_POST_AUTH = 'https://connect.garmin.com/modern/activities?'
URL_GC_SEARCH = 'https://connect.garmin.com/proxy/activity-search-service-1.2/json/activities?'
URL_GC_LIST = \
    'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
URL_GC_ACTIVITY = 'https://connect.garmin.com/modern/proxy/activity-service/activity/'
URL_GC_ACTIVITY_DETAIL = \
    'https://connect.garmin.com/modern/proxy/activity-service-1.3/json/activityDetails/'
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
POST_DATA = {
    'username': USERNAME,
    'password': PASSWORD,
    'embed': 'true',
    'lt': 'e1s1',
    '_eventId': 'submit',
    'displayNameRequired': 'false'
    }

print('Post login data')
http_req(URL_GC_LOGIN, POST_DATA)
print('Finish login post')

# Get the key.
# TODO: Can we do this without iterating?
LOGIN_TICKET = None
print("-------COOKIE")
for cookie in COOKIE_JAR:
    if cookie.name == 'CASTGC':
        print(cookie.name + ": " + cookie.value)
        LOGIN_TICKET = cookie.value
        break
print("-------COOKIE")

if not LOGIN_TICKET:
    raise Exception('Did not get a ticket cookie. Cannot log in. Did you enter the correct \
        username and password?')

# Chop of 'TGT-' off the beginning, prepend 'ST-0'.
LOGIN_TICKET = 'ST-0' + LOGIN_TICKET[4:]
# print(LOGIN_TICKET)

print('Request authentication')
# print(URL_GC_POST_AUTH + 'ticket=' + LOGIN_TICKET)
print("Request authentication URL: " + URL_GC_POST_AUTH + 'ticket=' + LOGIN_TICKET)
http_req(URL_GC_POST_AUTH + 'ticket=' + LOGIN_TICKET)
print('Finished authentication')

# We should be logged in now.
if not isdir(ARGS.directory):
    mkdir(ARGS.directory)

CSV_FILENAME = ARGS.directory + '/activities.csv'
CSV_EXISTED = isfile(CSV_FILENAME)

CSV_FILE = open(CSV_FILENAME, 'a')

# Write header to CSV file
if not CSV_EXISTED:
    CSV_FILE.write('Activity name,\
Description,\
Begin timestamp,\
Duration (h:m:s),\
Moving duration (h:m:s),\
Distance (km),\
Average speed (km/h),\
Average moving speed (km/h),\
Max. speed (km/h),\
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

DOWNLOAD_ALL = False
if ARGS.count == 'all':
    # If the user wants to download all activities, first download one,
    # then the result of that request will tell us how many are available
    # so we will modify the variables then.
    TOTAL_TO_DOWNLOAD = 1
    DOWNLOAD_ALL = True
else:
    TOTAL_TO_DOWNLOAD = int(ARGS.count)
TOTAL_DOWNLOADED = 0

# This while loop will download data from the server in multiple chunks, if necessary.
while TOTAL_DOWNLOADED < TOTAL_TO_DOWNLOAD:
    # Maximum chunk size 'limit_maximum' ... 400 return status if over maximum.  So download
    # maximum or whatever remains if less than maximum.
    # As of 2018-03-06 I get return status 500 if over maximum
    if TOTAL_TO_DOWNLOAD - TOTAL_DOWNLOADED > LIMIT_MAXIMUM:
        NUM_TO_DOWNLOAD = LIMIT_MAXIMUM
    else:
        NUM_TO_DOWNLOAD = TOTAL_TO_DOWNLOAD - TOTAL_DOWNLOADED

    SEARCH_PARAMS = {'start': TOTAL_DOWNLOADED, 'limit': NUM_TO_DOWNLOAD}
    # Query Garmin Connect
    print("Making activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print(URL_GC_SEARCH + urllib.parse.urlencode(SEARCH_PARAMS))
    RESULT = http_req(URL_GC_SEARCH + urllib.parse.urlencode(SEARCH_PARAMS))
    print("Finished activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

    # Persist JSON
    write_to_file(ARGS.directory + '/activities.json', RESULT.decode(), 'a')

    JSON_RESULTS = json.loads(RESULT)  # TODO: Catch possible exceptions here.

    if DOWNLOAD_ALL:
        # Modify TOTAL_TO_DOWNLOAD based on how many activities the server reports.
        TOTAL_TO_DOWNLOAD = int(JSON_RESULTS['results']['totalFound'])

        # Do it only once.
        DOWNLOAD_ALL = False

    # Pull out just the list of activities.
    ACTIVITIES = JSON_RESULTS['results']['activities']
    # print(ACTIVITIES)

    print("Activity list URL: " + URL_GC_LIST + urllib.parse.urlencode(SEARCH_PARAMS))
    ACTIVITY_LIST = http_req(URL_GC_LIST + urllib.parse.urlencode(SEARCH_PARAMS))
    write_to_file(ARGS.directory + '/activity_list.json', ACTIVITY_LIST.decode(), 'a')
    # LIST = json.loads(ACTIVITY_LIST)
    # print(LIST)

    # Process each activity.
    for a in ACTIVITIES:
        # Display which entry we're working on.
        print('Garmin Connect activity: [' + str(a['activity']['activityId']) + ']', end=' ')
        print(a['activity']['activityName'])
        print('\t' + a['activity']['uploadDate']['display'] + ',', end=' ')
        if ARGS.format == 'gpx':
            data_filename = ARGS.directory + '/' + str(a['activity']['activityId']) + \
                '_activity.gpx'
            download_url = URL_GC_GPX_ACTIVITY + str(a['activity']['activityId']) + '?full=true'
            print(download_url)
            file_mode = 'w'
        elif ARGS.format == 'tcx':
            data_filename = ARGS.directory + '/' + str(a['activity']['activityId']) + \
                '_activity.tcx'
            download_url = URL_GC_TCX_ACTIVITY + str(a['activity']['activityId']) + '?full=true'
            file_mode = 'w'
        elif ARGS.format == 'original':
            data_filename = ARGS.directory + '/' + str(a['activity']['activityId']) + \
                '_activity.zip'
            fit_filename = ARGS.directory + '/' + str(a['activity']['activityId']) + '_activity.fit'
            download_url = URL_GC_ORIGINAL_ACTIVITY + str(a['activity']['activityId'])
            file_mode = 'wb'
        else:
            raise Exception('Unrecognized format.')

        if isfile(data_filename):
            print('\tData file already exists; skipping...')
            continue
        # Regardless of unzip setting, don't redownload if the ZIP or FIT file exists.
        if ARGS.format == 'original' and isfile(fit_filename):
            print('\tFIT data file already exists; skipping...')
            continue

        # Download the data file from Garmin Connect. If the download fails (e.g., due to timeout),
        # this script will die, but nothing will have been written to disk about this activity, so
        # just running it again should pick up where it left off.
        print('\tDownloading file...', end=' ')

        try:
            data = http_req(download_url)
        except urllib.error.HTTPError as errs:
            # Handle expected (though unfortunate) error codes; die on unexpected ones.
            if errs.code == 500 and ARGS.format == 'tcx':
                # Garmin will give an internal server error (HTTP 500) when downloading TCX files
                # if the original was a manual GPX upload. Writing an empty file prevents this file
                # from being redownloaded, similar to the way GPX files are saved even when there
                # are no tracks. One could be generated here, but that's a bit much. Use the GPX
                # format if you want actual data in every file, as I believe Garmin provides a GPX
                # file for every activity.
                print('Writing empty file since Garmin did not generate a TCX file for this \
                    activity...', end=' ')
                data = ''
            elif errs.code == 404 and ARGS.format == 'original':
                # For manual activities (i.e., entered in online without a file upload), there is
                # no original file. # Write an empty file to prevent redownloading it.
                print('Writing empty file since there was no original activity data...', end=' ')
                data = ''
            else:
                raise Exception('Failed. Got an unexpected HTTP error (' + str(errs.code) + \
                    download_url +').')

        # Persist file
        write_to_file(data_filename, data.decode(), file_mode)

        print("Activity summary URL: " + URL_GC_ACTIVITY + str(a['activity']['activityId']))
        ACTIVITY_SUMMARY = http_req(URL_GC_ACTIVITY + str(a['activity']['activityId']))
        write_to_file(ARGS.directory + '/' + str(a['activity']['activityId']) + \
            '_activity_summary.json', ACTIVITY_SUMMARY.decode(), 'a')
        JSON_SUMMARY = json.loads(ACTIVITY_SUMMARY)
        # print(JSON_SUMMARY)

        print("Activity details URL: " + URL_GC_ACTIVITY_DETAIL + str(a['activity']['activityId']))
        ACTIVITY_DETAIL = http_req(URL_GC_ACTIVITY_DETAIL + str(a['activity']['activityId']))
        write_to_file(ARGS.directory + '/' + str(a['activity']['activityId']) + \
            '_activity_detail.json', ACTIVITY_DETAIL.decode(), 'a')
        JSON_DETAIL = json.loads(ACTIVITY_DETAIL)
        # print(JSON_DETAIL)

        # Write stats to CSV.
        empty_record = '"",'
        csv_record = ''

        csv_record += empty_record if 'activityName' not in a['activity'] else '"' + \
            a['activity']['activityName'].replace('"', '""') + '",'
        csv_record += empty_record if 'activityDescription' not in a['activity'] else '"' + \
            a['activity']['activityDescription'].replace('"', '""') + '",'
        csv_record += empty_record if 'startTimeLocal' not in JSON_SUMMARY['summaryDTO'] \
            else '"' + JSON_SUMMARY['summaryDTO']['startTimeLocal'] + '",'
        csv_record += empty_record if 'elapsedDuration' not in JSON_SUMMARY['summaryDTO'] \
            else hhmmss_from_seconds(JSON_SUMMARY['summaryDTO']['elapsedDuration']) + ','
        csv_record += empty_record if 'movingDuration' not in JSON_SUMMARY['summaryDTO'] \
            else hhmmss_from_seconds(JSON_SUMMARY['summaryDTO']['movingDuration']) + ','
        csv_record += empty_record if 'distance' not in JSON_SUMMARY['summaryDTO'] \
            else "{0:.5f}".format(JSON_SUMMARY['summaryDTO']['distance']/1000) + ','
        csv_record += empty_record if 'averageSpeed' not in JSON_SUMMARY['summaryDTO'] \
            else kmh_from_mps(JSON_SUMMARY['summaryDTO']['averageSpeed']) + ','
        csv_record += empty_record if 'averageMovingSpeed' not in JSON_SUMMARY['summaryDTO'] \
            else kmh_from_mps(JSON_SUMMARY['summaryDTO']['averageMovingSpeed']) + ','
        csv_record += empty_record if 'maxSpeed' not in JSON_SUMMARY['summaryDTO'] \
            else kmh_from_mps(JSON_SUMMARY['summaryDTO']['maxSpeed']) + ','
        csv_record += empty_record if 'elevationLoss' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['elevationLoss']) + ','
        csv_record += empty_record if 'elevationGain' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['elevationGain']) + ','
        csv_record += empty_record if 'minElevation' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['minElevation']) + ','
        csv_record += empty_record if 'maxElevation' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['maxElevation']) + ','
        csv_record += empty_record if 'minHR' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'maxHR' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['maxHR']) + ','
        csv_record += empty_record if 'averageHR' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['averageHR']) + ','
        csv_record += empty_record if 'calories' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['calories']) + ','
        csv_record += empty_record if 'averageBikeCadence' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['averageBikeCadence']) + ','
        csv_record += empty_record if 'maxBikeCadence' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['maxBikeCadence']) + ','
        csv_record += empty_record if 'totalNumberOfStrokes' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['totalNumberOfStrokes']) + ','
        csv_record += empty_record if 'averageTemperature' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['averageTemperature']) + ','
        csv_record += empty_record if 'minTemperature' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['minTemperature']) + ','
        csv_record += empty_record if 'maxTemperature' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['maxTemperature']) + ','
        csv_record += empty_record if 'activityId' not in a['activity'] else \
            '"https://connect.garmin.com/modern/activity/' + str(a['activity']['activityId']) + '",'
        csv_record += empty_record if 'endTimestamp' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'beginTimestamp' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'endTimestamp' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'device' not in a['activity'] else \
            a['activity']['device']['display'] + ' ' + a['activity']['device']['version'] + ','
        csv_record += empty_record if 'activityType' not in a['activity'] else \
            a['activity']['activityType']['display'] + ','
        csv_record += empty_record if 'eventType' not in a['activity'] else \
            a['activity']['eventType']['display'] + ','
        csv_record += empty_record if 'activityTimeZone' not in a['activity'] else \
            a['activity']['activityTimeZone']['display'] + ','
        csv_record += empty_record if 'startLatitude' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['startLatitude']) + ','
        csv_record += empty_record if 'startLongitude' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['startLongitude']) + ','
        csv_record += empty_record if 'endLatitude' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['endLatitude']) + ','
        csv_record += empty_record if 'endLongitude' not in JSON_SUMMARY['summaryDTO'] \
            else str(JSON_SUMMARY['summaryDTO']['endLongitude']) + ','
        csv_record += empty_record if 'gainCorrectedElevation' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'lossCorrectedElevation' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'maxCorrectedElevation' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'minCorrectedElevation' not in JSON_SUMMARY['summaryDTO'] \
            else ',' # no longer available in JSON
        csv_record += empty_record if 'metricsCount' not in \
            JSON_DETAIL['com.garmin.activity.details.json.ActivityDetails'] else \
            str(JSON_DETAIL['com.garmin.activity.details.json.ActivityDetails']['metricsCount']) \
            + ','
        csv_record += '\n'

        CSV_FILE.write(csv_record)

        if ARGS.format == 'gpx':
            # Validate GPX data. If we have an activity without GPS data (e.g., running on a
            # treadmill), Garmin Connect still kicks out a GPX, but there is only activity
            # information, no GPS data. N.B. You can omit the XML parse (and the associated log
            # messages) to speed things up.
            gpx = parseString(data)
            if gpx.getElementsByTagName('trkpt'):
                print('Done. GPX data saved.')
            else:
                print('Done. No track points found.')
        elif ARGS.format == 'original':
            # Even manual upload of a GPX file is zipped, but we'll validate the extension.
            if ARGS.unzip and data_filename[-3:].lower() == 'zip':
                print("Unzipping and removing original files...", end=' ')
                print('Filesize is: ' + str(stat(data_filename).st_size))
                if stat(data_filename).st_size > 0:
                    zip_file = open(data_filename, 'rb')
                    z = zipfile.ZipFile(zip_file)
                    for name in z.namelist():
                        z.extract(name, ARGS.directory)
                    zip_file.close()
                else:
                    print('Skipping 0Kb zip file.')
                remove(data_filename)
            print('Done.')
        else:
            # TODO: Consider validating other formats.
            print('Done.')
    TOTAL_DOWNLOADED += NUM_TO_DOWNLOAD
# End while loop for multiple chunks.

CSV_FILE.close()

print('Open CSV output.')
print(CSV_FILENAME)
# open CSV file. Comment this line out if you don't want this behavior
call(["/usr/bin/libreoffice6.0", "--calc", CSV_FILENAME])

print('Done!')
