#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
File: gcexport.py
Original author: Kyle Krafka (https://github.com/kjkjava/)
Date: April 28, 2015
Fork author: Michael P (https://github.com/moderation/)
Date: August 25, 2018

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
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SCRIPT_VERSION = "2.0.0"
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
ACTIVITIES_DIRECTORY = "./" + CURRENT_DATE + "_garmin_connect_export"

PARSER = argparse.ArgumentParser()

# TODO: Implement verbose and/or quiet options.
# PARSER.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
PARSER.add_argument("--version", help="print version and exit", action="store_true")
PARSER.add_argument(
    "--username",
    help="your Garmin Connect username (otherwise, you will be prompted)",
    nargs="?",
)
PARSER.add_argument(
    "--password",
    help="your Garmin Connect password (otherwise, you will be prompted)",
    nargs="?",
)
PARSER.add_argument(
    "-c",
    "--count",
    nargs="?",
    default="1",
    help="number of recent activities to download, or 'all' (default: 1)",
)
PARSER.add_argument(
    "-e",
    "--external",
    nargs="?",
    default="",
    help="path to external program to pass CSV file too (default: )",
)
PARSER.add_argument(
    "-a",
    "--args",
    nargs="?",
    default="",
    help="additional arguments to pass to external program (default: )",
)
PARSER.add_argument(
    "-f",
    "--format",
    nargs="?",
    choices=["gpx", "tcx", "original"],
    default="gpx",
    help="export format; can be 'gpx', 'tcx', or 'original' (default: 'gpx')",
)
PARSER.add_argument(
    "-d",
    "--directory",
    nargs="?",
    default=ACTIVITIES_DIRECTORY,
    help="the directory to export to (default: './YYYY-MM-DD_garmin_connect_export')",
)
PARSER.add_argument(
    "-u",
    "--unzip",
    help=(
        "if downloading ZIP files (format: 'original'), unzip the file and removes the"
        " ZIP file"
    ),
    action="store_true",
)

ARGS = PARSER.parse_args()

if ARGS.version:
    print(argv[0] + ", version " + SCRIPT_VERSION)
    exit(0)

COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))
# print(COOKIE_JAR)


def hhmmss_from_seconds(sec):
    """Helper function that converts seconds to HH:MM:SS time format."""
    if isinstance(sec, float):
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


def decoding_decider(data):
    """Helper function that decides if a decoding should happen or not."""
    if ARGS.format == "original":
        # An original file (ZIP file) is binary and not UTF-8 encoded
        data = data
    elif data:
        # GPX and TCX are textfiles and UTF-8 encoded
        data = data.decode()

    return data


# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers=None):
    """Helper function that makes the HTTP requests."""
    request = urllib.request.Request(url)
    # Tell Garmin we're some supported browser.
    request.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/54.0.2816.0 Safari/537.36",
    )
    if headers:
        for header_key, header_value in headers.items():
            request.add_header(header_key, header_value)
    if post:
        post = urllib.parse.urlencode(post)
        post = post.encode("utf-8")  # Convert dictionary to POST parameter string.
    # print("request.headers: " + str(request.headers) + " COOKIE_JAR: " + str(COOKIE_JAR))
    # print("post: " + str(post) + "request: " + str(request))
    response = OPENER.open(request, data=post)

    if response.getcode() == 204:
        # For activities without GPS coordinates, there is no GPX download (204 = no content).
        # Write an empty file to prevent redownloading it.
        print("Writing empty file since there was no GPX activity data...")
        return ""
    elif response.getcode() != 200:
        raise Exception("Bad return code (" + str(response.getcode()) + ") for: " + url)
    # print(response.getcode())

    return response.read()


print("Welcome to Garmin Connect Exporter!")

# Create directory for data files.
if isdir(ARGS.directory):
    print(
        "Warning: Output directory already exists. Will skip already-downloaded files"
        " and append to the CSV file."
    )

USERNAME = ARGS.username if ARGS.username else input("Username: ")
PASSWORD = ARGS.password if ARGS.password else getpass()

# Maximum number of activities you can request at once.  Set and enforced by Garmin.
LIMIT_MAXIMUM = 1000

WEBHOST = "https://connect.garmin.com"
REDIRECT = "https://connect.garmin.com/modern/"
BASE_URL = "https://connect.garmin.com/en-US/signin"
SSO = "https://sso.garmin.com/sso"
CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.2-min.css"

DATA = {
    "service": REDIRECT,
    "webhost": WEBHOST,
    "source": BASE_URL,
    "redirectAfterAccountLoginUrl": REDIRECT,
    "redirectAfterAccountCreationUrl": REDIRECT,
    "gauthHost": SSO,
    "locale": "en_US",
    "id": "gauth-widget",
    "cssUrl": CSS,
    "clientId": "GarminConnect",
    "rememberMeShown": "true",
    "rememberMeChecked": "false",
    "createAccountShown": "true",
    "openCreateAccount": "false",
    "displayNameShown": "false",
    "consumeServiceTicket": "false",
    "initialFocus": "true",
    "embedWidget": "false",
    "generateExtraServiceTicket": "true",
    "generateTwoExtraServiceTickets": "false",
    "generateNoServiceTicket": "false",
    "globalOptInShown": "true",
    "globalOptInChecked": "false",
    "mobile": "false",
    "connectLegalTerms": "true",
    "locationPromptShown": "true",
    "showPassword": "true",
}

print(urllib.parse.urlencode(DATA))

# URLs for various services.
URL_GC_LOGIN = "https://sso.garmin.com/sso/signin?" + urllib.parse.urlencode(DATA)
URL_GC_POST_AUTH = "https://connect.garmin.com/modern/activities?"
URL_GC_PROFILE = "https://connect.garmin.com/modern/profile"
URL_GC_USERSTATS = (
    "https://connect.garmin.com/modern/proxy/userstats-service/statistics/"
)
URL_GC_LIST = "https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?"
URL_GC_ACTIVITY = "https://connect.garmin.com/modern/proxy/activity-service/activity/"
URL_GC_GPX_ACTIVITY = (
    "https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/"
)
URL_GC_TCX_ACTIVITY = (
    "https://connect.garmin.com/modern/proxy/download-service/export/tcx/activity/"
)
URL_GC_ORIGINAL_ACTIVITY = (
    "http://connect.garmin.com/proxy/download-service/files/activity/"
)
URL_DEVICE_DETAIL = (
    "https://connect.garmin.com/modern/proxy/device-service/deviceservice/app-info/"
)
URL_GEAR_DETAIL = (
    "https://connect.garmin.com/modern/proxy/gear-service/gear/filterGear?"
)
# Initially, we need to get a valid session cookie, so we pull the login page.
print("Request login page")
http_req(URL_GC_LOGIN)
print("Finish login page")

# Now we'll actually login.
# Fields that are passed in a typical Garmin login.
POST_DATA = {
    "username": USERNAME,
    "password": PASSWORD,
    "embed": "false",
    "rememberme": "on",
}

HEADERS = {"referer": URL_GC_LOGIN}

print("Post login data")
LOGIN_RESPONSE = http_req(URL_GC_LOGIN + "#", POST_DATA, HEADERS).decode()
print("Finish login post")

# extract the ticket from the login response
PATTERN = re.compile(r".*\?ticket=([-\w]+)\";.*", re.MULTILINE | re.DOTALL)
MATCH = PATTERN.match(LOGIN_RESPONSE)
if not MATCH:
    raise Exception(
        "Did not get a ticket in the login response. Cannot log in. Did you enter the"
        " correct username and password?"
    )
LOGIN_TICKET = MATCH.group(1)
print("Login ticket=" + LOGIN_TICKET)

print("Request authentication URL: " + URL_GC_POST_AUTH + "ticket=" + LOGIN_TICKET)
http_req(URL_GC_POST_AUTH + "ticket=" + LOGIN_TICKET)
print("Finished authentication")

# We should be logged in now.
if not isdir(ARGS.directory):
    mkdir(ARGS.directory)

CSV_FILENAME = ARGS.directory + "/activities.csv"
CSV_EXISTED = isfile(CSV_FILENAME)

CSV_FILE = open(CSV_FILENAME, "a")

# Write header to CSV file
if not CSV_EXISTED:
    CSV_FILE.write(
        "Activity name,Description,Bike,Begin timestamp,Duration (h:m:s),Moving"
        " duration (h:m:s),Distance (km),Average speed (km/h),Average moving speed"
        " (km/h),Max. speed (km/h),Elevation loss uncorrected (m),Elevation gain"
        " uncorrected (m),Elevation min. uncorrected (m),Elevation max. uncorrected"
        " (m),Min. heart rate (bpm),Max. heart rate (bpm),Average heart rate"
        " (bpm),Calories,Avg. cadence (rpm),Max. cadence (rpm),Strokes,Avg. temp"
        " (°C),Min. temp (°C),Max. temp (°C),Map,End timestamp,Begin timestamp (ms),End"
        " timestamp (ms),Device,Activity type,Event type,Time zone,Begin latitude"
        " (°DD),Begin longitude (°DD),End latitude (°DD),End longitude (°DD),Elevation"
        " gain corrected (m),Elevation loss corrected (m),Elevation max. corrected"
        " (m),Elevation min. corrected (m),Sample count\n"
    )

DOWNLOAD_ALL = False
if ARGS.count == "all":
    # If the user wants to download all activities, query the userstats
    # on the profile page to know how many are available
    print("Getting display name and user stats via: " + URL_GC_PROFILE)
    PROFILE_PAGE = http_req(URL_GC_PROFILE).decode()
    # write_to_file(args.directory + '/profile.html', profile_page, 'a')

    # extract the display name from the profile page, it should be in there as
    # \"displayName\":\"eschep\"
    PATTERN = re.compile(
        r".*\\\"displayName\\\":\\\"([-.\w]+)\\\".*", re.MULTILINE | re.DOTALL
    )
    MATCH = PATTERN.match(PROFILE_PAGE)
    if not MATCH:
        raise Exception("Did not find the display name in the profile page.")
    DISPLAY_NAME = MATCH.group(1)
    print("displayName=" + DISPLAY_NAME)

    print(URL_GC_USERSTATS + DISPLAY_NAME)
    USER_STATS = http_req(URL_GC_USERSTATS + DISPLAY_NAME)
    print("Finished display name and user stats ~~~~~~~~~~~~~~~~~~~~~~~~~~~")

    # Persist JSON
    write_to_file(ARGS.directory + "/userstats.json", USER_STATS.decode(), "a")

    # Modify total_to_download based on how many activities the server reports.
    JSON_USER = json.loads(USER_STATS)
    TOTAL_TO_DOWNLOAD = int(JSON_USER["userMetrics"][0]["totalActivities"])
else:
    TOTAL_TO_DOWNLOAD = int(ARGS.count)

TOTAL_DOWNLOADED = 0
print("Total to download: " + str(TOTAL_TO_DOWNLOAD))

# This while loop will download data from the server in multiple chunks, if necessary.
while TOTAL_DOWNLOADED < TOTAL_TO_DOWNLOAD:
    # Maximum chunk size 'limit_maximum' ... 400 return status if over maximum.  So download
    # maximum or whatever remains if less than maximum.
    # As of 2018-03-06 I get return status 500 if over maximum
    if TOTAL_TO_DOWNLOAD - TOTAL_DOWNLOADED > LIMIT_MAXIMUM:
        NUM_TO_DOWNLOAD = LIMIT_MAXIMUM
    else:
        NUM_TO_DOWNLOAD = TOTAL_TO_DOWNLOAD - TOTAL_DOWNLOADED

    SEARCH_PARAMS = {"start": TOTAL_DOWNLOADED, "limit": NUM_TO_DOWNLOAD}

    # Query Garmin Connect
    print("Activity list URL: " + URL_GC_LIST + urllib.parse.urlencode(SEARCH_PARAMS))
    ACTIVITY_LIST = http_req(URL_GC_LIST + urllib.parse.urlencode(SEARCH_PARAMS))
    write_to_file(ARGS.directory + "/activity_list.json", ACTIVITY_LIST.decode(), "a")
    LIST = json.loads(ACTIVITY_LIST)
    # print(LIST)

    # Process each activity.
    for a in LIST:
        # Display which entry we're working on.
        print("Garmin Connect activity: [" + str(a["activityId"]) + "]", end=" ")
        print(a["activityName"])
        # print("\t" + a["uploadDate"]["display"] + ",", end=" ")
        if ARGS.format == "gpx":
            data_filename = (
                ARGS.directory + "/" + str(a["activityId"]) + "_activity.gpx"
            )
            download_url = URL_GC_GPX_ACTIVITY + str(a["activityId"]) + "?full=true"
            print(download_url)
            file_mode = "w"
        elif ARGS.format == "tcx":
            data_filename = (
                ARGS.directory + "/" + str(a["activityId"]) + "_activity.tcx"
            )
            download_url = URL_GC_TCX_ACTIVITY + str(a["activityId"]) + "?full=true"
            file_mode = "w"
        elif ARGS.format == "original":
            data_filename = (
                ARGS.directory + "/" + str(a["activityId"]) + "_activity.zip"
            )
            fit_filename = ARGS.directory + "/" + str(a["activityId"]) + "_activity.fit"
            download_url = URL_GC_ORIGINAL_ACTIVITY + str(a["activityId"])
            file_mode = "wb"
        else:
            raise Exception("Unrecognized format.")

        if isfile(data_filename):
            print("\tData file already exists; skipping...")
            continue
        # Regardless of unzip setting, don't redownload if the ZIP or FIT file exists.
        if ARGS.format == "original" and isfile(fit_filename):
            print("\tFIT data file already exists; skipping...")
            continue

        # Download the data file from Garmin Connect. If the download fails (e.g., due to timeout),
        # this script will die, but nothing will have been written to disk about this activity, so
        # just running it again should pick up where it left off.
        print("\tDownloading file...", end=" ")

        try:
            data = http_req(download_url)
        except urllib.error.HTTPError as errs:
            # Handle expected (though unfortunate) error codes; die on unexpected ones.
            if errs.code == 500 and ARGS.format == "tcx":
                # Garmin will give an internal server error (HTTP 500) when downloading TCX files
                # if the original was a manual GPX upload. Writing an empty file prevents this file
                # from being redownloaded, similar to the way GPX files are saved even when there
                # are no tracks. One could be generated here, but that's a bit much. Use the GPX
                # format if you want actual data in every file, as I believe Garmin provides a GPX
                # file for every activity.
                print(
                    "Writing empty file since Garmin did not generate a TCX file for"
                    " this activity...",
                    end=" ",
                )
                data = ""
            elif errs.code == 404 and ARGS.format == "original":
                # For manual activities (i.e., entered in online without a file upload), there is
                # no original file. # Write an empty file to prevent redownloading it.
                print(
                    "Writing empty file since there was no original activity data...",
                    end=" ",
                )
                data = ""
            else:
                raise Exception(
                    "Failed. Got an unexpected HTTP error ("
                    + str(errs.code)
                    + download_url
                    + ")."
                )

        # Persist file
        write_to_file(data_filename, decoding_decider(data), file_mode)

        print("Activity summary URL: " + URL_GC_ACTIVITY + str(a["activityId"]))
        ACTIVITY_SUMMARY = http_req(URL_GC_ACTIVITY + str(a["activityId"]))
        write_to_file(
            ARGS.directory + "/" + str(a["activityId"]) + "_activity_summary.json",
            ACTIVITY_SUMMARY.decode(),
            "a",
        )
        JSON_SUMMARY = json.loads(ACTIVITY_SUMMARY)
        # print(JSON_SUMMARY)

        print(
            "Device detail URL: "
            + URL_DEVICE_DETAIL
            + str(JSON_SUMMARY["metadataDTO"]["deviceApplicationInstallationId"])
        )
        DEVICE_DETAIL = http_req(
            URL_DEVICE_DETAIL
            + str(JSON_SUMMARY["metadataDTO"]["deviceApplicationInstallationId"])
        )
        if DEVICE_DETAIL:
            write_to_file(
                ARGS.directory + "/" + str(a["activityId"]) + "_app_info.json",
                DEVICE_DETAIL.decode(),
                "a",
            )
            JSON_DEVICE = json.loads(DEVICE_DETAIL)
            # print(JSON_DEVICE)
        else:
            print("Retrieving Device Details failed.")
            JSON_DEVICE = None

        print(
            "Activity details URL: "
            + URL_GC_ACTIVITY
            + str(a["activityId"])
            + "/details"
        )
        try:
            ACTIVITY_DETAIL = http_req(
                URL_GC_ACTIVITY + str(a["activityId"]) + "/details"
            )
            write_to_file(
                ARGS.directory + "/" + str(a["activityId"]) + "_activity_detail.json",
                ACTIVITY_DETAIL.decode(),
                "a",
            )
            JSON_DETAIL = json.loads(ACTIVITY_DETAIL)
            # print(JSON_DETAIL)
        except:
            print("Retrieving Activity Details failed.")
            JSON_DETAIL = None

        print(
            "Gear details URL: "
            + URL_GEAR_DETAIL
            + "activityId="
            + str(a["activityId"])
        )
        try:
            GEAR_DETAIL = http_req(
                URL_GEAR_DETAIL + "activityId=" + str(a["activityId"])
            )
            write_to_file(
                ARGS.directory + "/" + str(a["activityId"]) + "_gear_detail.json",
                GEAR_DETAIL.decode(),
                "a",
            )
            JSON_GEAR = json.loads(GEAR_DETAIL)
            # print(JSON_GEAR)
        except:
            print("Retrieving Gear Details failed.")
            # JSON_GEAR = None

        # Write stats to CSV.
        empty_record = ","
        csv_record = ""

        csv_record += (
            empty_record
            if "activityName" not in a or not a["activityName"]
            else '"' + a["activityName"].replace('"', '""') + '",'
        )

        # maybe a more elegant way of coding this but need to handle description as null
        if "description" not in a:
            csv_record += empty_record
        elif a["description"] is not None:
            csv_record += '"' + a["description"].replace('"', '""') + '",'
        else:
            csv_record += empty_record

        # Gear detail returned as an array so pick the first one
        csv_record += (
            empty_record
            if not JSON_GEAR or "customMakeModel" not in JSON_GEAR[0]
            else JSON_GEAR[0]["customMakeModel"] + ","
        )
        csv_record += (
            empty_record
            if "startTimeLocal" not in JSON_SUMMARY["summaryDTO"]
            else '"' + JSON_SUMMARY["summaryDTO"]["startTimeLocal"] + '",'
        )
        csv_record += (
            empty_record
            if "elapsedDuration" not in JSON_SUMMARY["summaryDTO"]
            else hhmmss_from_seconds(JSON_SUMMARY["summaryDTO"]["elapsedDuration"])
            + ","
        )
        csv_record += (
            empty_record
            if "movingDuration" not in JSON_SUMMARY["summaryDTO"]
            else hhmmss_from_seconds(JSON_SUMMARY["summaryDTO"]["movingDuration"]) + ","
        )
        csv_record += (
            empty_record
            if "distance" not in JSON_SUMMARY["summaryDTO"]
            else "{0:.5f}".format(JSON_SUMMARY["summaryDTO"]["distance"] / 1000) + ","
        )
        csv_record += (
            empty_record
            if "averageSpeed" not in JSON_SUMMARY["summaryDTO"]
            else kmh_from_mps(JSON_SUMMARY["summaryDTO"]["averageSpeed"]) + ","
        )
        csv_record += (
            empty_record
            if "averageMovingSpeed" not in JSON_SUMMARY["summaryDTO"]
            else kmh_from_mps(JSON_SUMMARY["summaryDTO"]["averageMovingSpeed"]) + ","
        )
        csv_record += (
            empty_record
            if "maxSpeed" not in JSON_SUMMARY["summaryDTO"]
            else kmh_from_mps(JSON_SUMMARY["summaryDTO"]["maxSpeed"]) + ","
        )
        csv_record += (
            empty_record
            if "elevationLoss" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["elevationLoss"]) + ","
        )
        csv_record += (
            empty_record
            if "elevationGain" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["elevationGain"]) + ","
        )
        csv_record += (
            empty_record
            if "minElevation" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["minElevation"]) + ","
        )
        csv_record += (
            empty_record
            if "maxElevation" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["maxElevation"]) + ","
        )
        csv_record += empty_record if "minHR" not in JSON_SUMMARY["summaryDTO"] else ","
        csv_record += (
            empty_record
            if "maxHR" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["maxHR"]) + ","
        )
        csv_record += (
            empty_record
            if "averageHR" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["averageHR"]) + ","
        )
        csv_record += (
            empty_record
            if "calories" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["calories"]) + ","
        )
        csv_record += (
            empty_record
            if "averageBikeCadence" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["averageBikeCadence"]) + ","
        )
        csv_record += (
            empty_record
            if "maxBikeCadence" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["maxBikeCadence"]) + ","
        )
        csv_record += (
            empty_record
            if "totalNumberOfStrokes" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["totalNumberOfStrokes"]) + ","
        )
        csv_record += (
            empty_record
            if "averageTemperature" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["averageTemperature"]) + ","
        )
        csv_record += (
            empty_record
            if "minTemperature" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["minTemperature"]) + ","
        )
        csv_record += (
            empty_record
            if "maxTemperature" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["maxTemperature"]) + ","
        )
        csv_record += (
            empty_record
            if "activityId" not in a
            else '"https://connect.garmin.com/modern/activity/'
            + str(a["activityId"])
            + '",'
        )
        csv_record += (
            empty_record if "endTimestamp" not in JSON_SUMMARY["summaryDTO"] else ","
        )
        csv_record += (
            empty_record if "beginTimestamp" not in JSON_SUMMARY["summaryDTO"] else ","
        )
        csv_record += (
            empty_record if "endTimestamp" not in JSON_SUMMARY["summaryDTO"] else ","
        )
        csv_record += (
            empty_record
            if not JSON_DEVICE or "productDisplayName" not in JSON_DEVICE
            else JSON_DEVICE["productDisplayName"]
            + " "
            + JSON_DEVICE["versionString"]
            + ","
        )
        csv_record += (
            empty_record
            if "activityType" not in a
            else a["activityType"]["typeKey"].title() + ","
        )
        csv_record += (
            empty_record
            if "eventType" not in a
            else a["eventType"]["typeKey"].title() + ","
        )
        csv_record += (
            empty_record
            if "timeZoneUnitDTO" not in JSON_SUMMARY
            else JSON_SUMMARY["timeZoneUnitDTO"]["timeZone"] + ","
        )
        csv_record += (
            empty_record
            if "startLatitude" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["startLatitude"]) + ","
        )
        csv_record += (
            empty_record
            if "startLongitude" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["startLongitude"]) + ","
        )
        csv_record += (
            empty_record
            if "endLatitude" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["endLatitude"]) + ","
        )
        csv_record += (
            empty_record
            if "endLongitude" not in JSON_SUMMARY["summaryDTO"]
            else str(JSON_SUMMARY["summaryDTO"]["endLongitude"]) + ","
        )
        csv_record += (
            empty_record
            if "gainCorrectedElevation" not in JSON_SUMMARY["summaryDTO"]
            else ","
        )
        csv_record += (
            empty_record
            if "lossCorrectedElevation" not in JSON_SUMMARY["summaryDTO"]
            else ","
        )
        csv_record += (
            empty_record
            if "maxCorrectedElevation" not in JSON_SUMMARY["summaryDTO"]
            else ","
        )
        csv_record += (
            empty_record
            if "minCorrectedElevation" not in JSON_SUMMARY["summaryDTO"]
            else ","
        )
        csv_record += (
            empty_record
            if not JSON_DETAIL or "metricsCount" not in JSON_DETAIL
            else str(JSON_DETAIL["metricsCount"]) + ","
        )
        csv_record += "\n"

        CSV_FILE.write(csv_record)

        if ARGS.format == "gpx" and data:
            # Validate GPX data. If we have an activity without GPS data (e.g., running on a
            # treadmill), Garmin Connect still kicks out a GPX (sometimes), but there is only
            # activity information, no GPS data. N.B. You can omit the XML parse (and the
            # associated log messages) to speed things up.
            gpx = parseString(data)
            if gpx.getElementsByTagName("trkpt"):
                print("Done. GPX data saved.")
            else:
                print("Done. No track points found.")
        elif ARGS.format == "original":
            # Even manual upload of a GPX file is zipped, but we'll validate the extension.
            if ARGS.unzip and data_filename[-3:].lower() == "zip":
                print("Unzipping and removing original files...", end=" ")
                print("Filesize is: " + str(stat(data_filename).st_size))
                if stat(data_filename).st_size > 0:
                    zip_file = open(data_filename, "rb")
                    z = zipfile.ZipFile(zip_file)
                    for name in z.namelist():
                        z.extract(name, ARGS.directory)
                    zip_file.close()
                else:
                    print("Skipping 0Kb zip file.")
                remove(data_filename)
            print("Done.")
        else:
            # TODO: Consider validating other formats.
            print("Done.")
    TOTAL_DOWNLOADED += NUM_TO_DOWNLOAD
# End while loop for multiple chunks.

CSV_FILE.close()

if len(ARGS.external):
    print("Open CSV output.")
    print(CSV_FILENAME)
    # open CSV file. Comment this line out if you don't want this behavior
    call([ARGS.external, "--" + ARGS.args, CSV_FILENAME])

print("Done!")
