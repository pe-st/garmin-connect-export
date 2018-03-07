#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
File: gcexport.py
Original author: Kyle Krafka (https://github.com/kjkjava/)
Date: April 28, 2015
Fork author: Michae P (https://github.com/moderation/)
Date: February 21, 2016

Description:	Use this script to export your fitness data from Garmin Connect.
				See README.md for more information.
"""

from urllib import urlencode
from datetime import datetime
from datetime import timedelta
from getpass import getpass
from sys import argv
from os.path import isdir
from os.path import isfile
from os import mkdir
from os import remove
from os import stat
from xml.dom.minidom import parseString
from subprocess import call

import urllib, urllib2, cookielib, json
from fileinput import filename

import argparse
import zipfile

script_version = '1.0.0'
current_date = datetime.now().strftime('%Y-%m-%d')
activities_directory = './' + current_date + '_garmin_connect_export'

parser = argparse.ArgumentParser()

# TODO: Implement verbose and/or quiet options.
# parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
parser.add_argument('--version', help="print version and exit", action="store_true")
parser.add_argument('--username', help="your Garmin Connect username (otherwise, you will be prompted)", nargs='?')
parser.add_argument('--password', help="your Garmin Connect password (otherwise, you will be prompted)", nargs='?')

parser.add_argument('-c', '--count', nargs='?', default="1",
	help="number of recent activities to download, or 'all' (default: 1)")

parser.add_argument('-f', '--format', nargs='?', choices=['gpx', 'tcx', 'original'], default="gpx",
	help="export format; can be 'gpx', 'tcx', or 'original' (default: 'gpx')")

parser.add_argument('-d', '--directory', nargs='?', default=activities_directory,
	help="the directory to export to (default: './YYYY-MM-DD_garmin_connect_export')")

parser.add_argument('-u', '--unzip',
	help="if downloading ZIP files (format: 'original'), unzip the file and removes the ZIP file",
	action="store_true")

args = parser.parse_args()

if args.version:
	print argv[0] + ", version " + script_version
	exit(0)

cookie_jar = cookielib.CookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))
# print cookie_jar

# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers={}):
	request = urllib2.Request(url)
	# request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1337 Safari/537.36')  # Tell Garmin we're some supported browser.
	request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2816.0 Safari/537.36')  # Tell Garmin we're some supported browser.
	for header_key, header_value in headers.iteritems():
		request.add_header(header_key, header_value)
	if post:
		# print "POSTING"
		post = urlencode(post)  # Convert dictionary to POST parameter string.
	# print request.headers
	# print cookie_jar
	# print post
	# print request
	response = opener.open(request, data=post)  # This line may throw a urllib2.HTTPError.

	# N.B. urllib2 will follow any 302 redirects. Also, the "open" call above may throw a urllib2.HTTPError which is checked for below.
	# print response.getcode()
	if response.getcode() != 200:
		raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

	return response.read()

print 'Welcome to Garmin Connect Exporter!'

# Create directory for data files.
if isdir(args.directory):
	print 'Warning: Output directory already exists. Will skip already-downloaded files and append to the CSV file.'

username = args.username if args.username else raw_input('Username: ')
password = args.password if args.password else getpass()

# Maximum number of activities you can request at once.  Set and enforced by Garmin.
limit_maximum = 19

hostname_url = http_req('http://connect.garmin.com/gauth/hostname')
# print hostname_url
hostname = json.loads(hostname_url)['host']

REDIRECT = "https://connect.garmin.com/post-auth/login"
BASE_URL = "http://connect.garmin.com/en-US/signin"
GAUTH = "http://connect.garmin.com/gauth/hostname"
SSO = "https://sso.garmin.com/sso"
CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.1-min.css"

data = {'service': REDIRECT,
    'webhost': hostname,
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
    'generateExtraServiceTicket': 'false'}

print urllib.urlencode(data)

# URLs for various services.
url_gc_login     = 'https://sso.garmin.com/sso/login?' + urllib.urlencode(data)
url_gc_post_auth = 'https://connect.garmin.com/post-auth/login?'
url_gc_summary    = 'http://connect.garmin.com/proxy/activity-search-service-1.2/json/activities?start=0&limit=1'
url_gc_search    = 'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
url_gc_gpx_activity = 'https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/'
url_gc_tcx_activity = 'https://connect.garmin.com/modern/proxy/download-service/export/tcx/activity/'
url_gc_original_activity = 'http://connect.garmin.com/proxy/download-service/files/activity/'

# Initially, we need to get a valid session cookie, so we pull the login page.
print 'Request login page'
http_req(url_gc_login)
print 'Finish login page'

# Now we'll actually login.
post_data = {'username': username, 'password': password, 'embed': 'true', 'lt': 'e1s1', '_eventId': 'submit', 'displayNameRequired': 'false'}  # Fields that are passed in a typical Garmin login.
print 'Post login data'
http_req(url_gc_login, post_data)
print 'Finish login post'

# Get the key.
# TODO: Can we do this without iterating?
login_ticket = None
print "-------COOKIE"
for cookie in cookie_jar:
	print cookie.name + ": " + cookie.value
	if cookie.name == 'CASTGC':
		login_ticket = cookie.value
		print login_ticket
		print cookie.value
		break
print "-------COOKIE"

if not login_ticket:
	raise Exception('Did not get a ticket cookie. Cannot log in. Did you enter the correct username and password?')

# Chop of 'TGT-' off the beginning, prepend 'ST-0'.
login_ticket = 'ST-0' + login_ticket[4:]
# print login_ticket

print 'Request authentication'
# print url_gc_post_auth + 'ticket=' + login_ticket
http_req(url_gc_post_auth + 'ticket=' + login_ticket)
print 'Finished authentication'

# https://github.com/kjkjava/garmin-connect-export/issues/18#issuecomment-243859319
print "Call modern"
http_req("http://connect.garmin.com/modern")
print "Finish modern"
print "Call legacy session"
http_req("https://connect.garmin.com/legacy/session")
print "Finish legacy session"

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


# Max. Elevation,\
# Average Moving Speed,\
# Max. Speed,\
# Calories,\
# Duration (Raw Seconds),\
# Moving Duration (Raw Seconds),\
# Average Speed,\
# Distance,\
# Min. Elevation,\
# Elevation Gain,\
# Elevation Loss,\
# Avg Cadence,\
# Max Cadence,\
# Avg Temp,\
# Min Temp,\
# Max Temp,\
# Min. elevation (m),\
# Max. elevation (m),\
# Activity parent,\

if args.count == 'all':
	# If the user wants to download all activities, first download one,
	# then the result of that request will tell us how many are available
	# so we will modify the variables then.
	print "Making result summary request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
	print url_gc_summary
	result = http_req(url_gc_summary)
	print "Finished result summary request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

	# Persist JSON
	json_filename = args.directory + '/activities-summary.json'
	json_file = open(json_filename, 'a')
	json_file.write(result)
	json_file.close()

	# Modify total_to_download based on how many activities the server reports.
	json_results = json.loads(result)  # TODO: Catch possible exceptions here.
	total_to_download = int(json_results['results']['totalFound'])
else:
	total_to_download = int(args.count)
total_downloaded = 0

# This while loop will download data from the server in multiple chunks, if necessary.
while total_downloaded < total_to_download:
	# Maximum chunk size 'limit_maximum' ... 400 return status if over maximum.  So download maximum or whatever remains if less than maximum.
	# As of 2018-03-06 I get return status 500 if over maximum
	if total_to_download - total_downloaded > limit_maximum:
		num_to_download = limit_maximum
	else:
		num_to_download = total_to_download - total_downloaded

	search_params = {'start': total_downloaded, 'limit': num_to_download}
	# Query Garmin Connect
	print "Making activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
	print url_gc_search + urlencode(search_params)
	result = http_req(url_gc_search + urlencode(search_params))
	print "Finished activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

	# Persist JSON
	json_filename = args.directory + '/activities.json'
	json_file = open(json_filename, 'a')
	json_file.write(result)
	json_file.close()

	json_results = json.loads(result)  # TODO: Catch possible exceptions here.

	# search = json_results['results']['search']

	# Pull out just the list of activities.
	activities = json_results

	# Process each activity.
	for a in activities:
		# Display which entry we're working on.
		print 'Garmin Connect activity: [' + str(a['activityId']) + ']',
		print a['activityName']
		print '\t' + a['startTimeLocal'] + ',',
		if 'duration' in a:
			print str(timedelta(seconds=a['duration'])) + ',',
		else:
			print '??:??:??,',
		if 'distance' in a:
			print a['distance']
		else:
			print '0.00 Miles'

		if args.format == 'gpx':
			data_filename = args.directory + '/activity_' + str(a['activityId']) + '.gpx'
			download_url = url_gc_gpx_activity + str(a['activityId']) + '?full=true'
			# download_url = url_gc_gpx_activity + str(a['activityId']) + '?full=true' + '&original=true'
			print download_url
			file_mode = 'w'
		elif args.format == 'tcx':
			data_filename = args.directory + '/activity_' + str(a['activityId']) + '.tcx'
			download_url = url_gc_tcx_activity + str(a['activityId']) + '?full=true'
			file_mode = 'w'
		elif args.format == 'original':
			data_filename = args.directory + '/activity_' + str(a['activityId']) + '.zip'
			fit_filename = args.directory + '/' + str(a['activityId']) + '.fit'
			download_url = url_gc_original_activity + str(a['activityId'])
			file_mode = 'wb'
		else:
			raise Exception('Unrecognized format.')

		if isfile(data_filename):
			print '\tData file already exists; skipping...'
			continue
		if args.format == 'original' and isfile(fit_filename):  # Regardless of unzip setting, don't redownload if the ZIP or FIT file exists.
			print '\tFIT data file already exists; skipping...'
			continue

		# Download the data file from Garmin Connect.
		# If the download fails (e.g., due to timeout), this script will die, but nothing
		# will have been written to disk about this activity, so just running it again
		# should pick up where it left off.
		print '\tDownloading file...',

		try:
			data = http_req(download_url)
		except urllib2.HTTPError as e:
			# Handle expected (though unfortunate) error codes; die on unexpected ones.
			if e.code == 500 and args.format == 'tcx':
				# Garmin will give an internal server error (HTTP 500) when downloading TCX files if the original was a manual GPX upload.
				# Writing an empty file prevents this file from being redownloaded, similar to the way GPX files are saved even when there are no tracks.
				# One could be generated here, but that's a bit much. Use the GPX format if you want actual data in every file,
				# as I believe Garmin provides a GPX file for every activity.
				print 'Writing empty file since Garmin did not generate a TCX file for this activity...',
				data = ''
			elif e.code == 404 and args.format == 'original':
				# For manual activities (i.e., entered in online without a file upload), there is no original file.
				# Write an empty file to prevent redownloading it.
				print 'Writing empty file since there was no original activity data...',
				data = ''
			else:
				raise Exception('Failed. Got an unexpected HTTP error (' + str(e.code) + download_url +').')

		save_file = open(data_filename, file_mode)
		save_file.write(data)
		save_file.close()

		# Write stats to CSV.
		empty_record = '"",'

		csv_record = ''

		csv_record += empty_record if 'activityName' not in a else '"' + a['activityName'].replace('"', '""') + '",'
#		csv_record += empty_record if 'activityDescription' not in a else '"' + a['activityDescription'].replace('"', '""') + '",'
#		csv_record += empty_record if 'BeginTimestamp' not in a['activitySummary'] else '"' + a['activitySummary']['BeginTimestamp']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'SumElapsedDuration' not in a['activitySummary'] else a['activitySummary']['SumElapsedDuration']['display'].replace('"', '""') + ','
#		csv_record += empty_record if 'SumMovingDuration' not in a['activitySummary'] else a['activitySummary']['SumMovingDuration']['display'].replace('"', '""') + ','
#		csv_record += empty_record if 'SumDistance' not in a['activitySummary'] else '"' + a['activitySummary']['SumDistance']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'WeightedMeanSpeed' not in a['activitySummary'] else '"' + a['activitySummary']['WeightedMeanSpeed']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'WeightedMeanMovingSpeed' not in a['activitySummary'] else '"' + a['activitySummary']['WeightedMeanMovingSpeed']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'MaxSpeed' not in a['activitySummary'] else '"' + a['activitySummary']['MaxSpeed']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'LossUncorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['LossUncorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'GainUncorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['GainUncorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'MinUncorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['MinUncorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'MaxUncorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['MaxUncorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'MinHeartRate' not in a['activitySummary'] else '"' + a['activitySummary']['MinHeartRate']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'MaxHeartRate' not in a['activitySummary'] else '"' + a['activitySummary']['MaxHeartRate']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'WeightedMeanHeartRate' not in a['activitySummary'] else '"' + a['activitySummary']['WeightedMeanHeartRate']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'SumEnergy' not in a['activitySummary'] else '"' + a['activitySummary']['SumEnergy']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'WeightedMeanBikeCadence' not in a['activitySummary'] else '"' + a['activitySummary']['WeightedMeanBikeCadence']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'MaxBikeCadence' not in a['activitySummary'] else '"' + a['activitySummary']['MaxBikeCadence']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'SumStrokes' not in a['activitySummary'] else '"' + a['activitySummary']['SumStrokes']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'WeightedMeanAirTemperature' not in a['activitySummary'] else '"' + a['activitySummary']['WeightedMeanAirTemperature']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'MinAirTemperature' not in a['activitySummary'] else '"' + a['activitySummary']['MinAirTemperature']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'MaxAirTemperature' not in a['activitySummary'] else '"' + a['activitySummary']['MaxAirTemperature']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'activityId' not in a else '"https://connect.garmin.com/modern/activity/' + str(a['activityId']).replace('"', '""') + '",'
#		csv_record += empty_record if 'EndTimestamp' not in a['activitySummary'] else '"' + a['activitySummary']['EndTimestamp']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'BeginTimestamp' not in a['activitySummary'] else '"' + a['activitySummary']['BeginTimestamp']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'EndTimestamp' not in a['activitySummary'] else '"' + a['activitySummary']['EndTimestamp']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'device' not in a else '"' + a['device']['display'].replace('"', '""') + ' ' + a['device']['version'].replace('"', '""') + '",'
#		csv_record += empty_record if 'activityType' not in a else '"' + a['activityType']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'eventType' not in a else '"' + a['eventType']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'activityTimeZone' not in a else '"' + a['activityTimeZone']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'BeginLatitude' not in a['activitySummary'] else '"' + a['activitySummary']['BeginLatitude']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'BeginLongitude' not in a['activitySummary'] else '"' + a['activitySummary']['BeginLongitude']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'EndLatitude' not in a['activitySummary'] else '"' + a['activitySummary']['EndLatitude']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'EndLongitude' not in a['activitySummary'] else '"' + a['activitySummary']['EndLongitude']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'GainCorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['GainCorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'LossCorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['LossCorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'MaxCorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['MaxCorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'MinCorrectedElevation' not in a['activitySummary'] else '"' + str(float(a['activitySummary']['MinCorrectedElevation']['value'])/100) + '",'
#		csv_record += empty_record if 'SumSampleCountDuration' not in a['activitySummary'] else '"' + a['activitySummary']['SumSampleCountDuration']['value'].replace('"', '""') + '"'
		csv_record += '\n'

#		csv_record += empty_record if 'gainElevation' not in a else '"' + a['gainElevation']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'minElevation' not in a else '"' + a['minElevation']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'maxElevation' not in a else '"' + a['maxElevation']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'maxElevation' not in a else '"' + a['maxElevation']['withUnit'].replace('"', '""') + '",'
#		csv_record += empty_record if 'weightedMeanMovingSpeed' not in a else '"' + a['weightedMeanMovingSpeed']['display'].replace('"', '""') + '",'  # The units vary between Minutes per Mile and mph, but withUnit always displays "Minutes per Mile"
#		csv_record += empty_record if 'maxSpeed' not in a else '"' + a['maxSpeed']['display'].replace('"', '""') + '",'  # The units vary between Minutes per Mile and mph, but withUnit always displays "Minutes per Mile"
#		csv_record += empty_record if 'sumEnergy' not in a else '"' + a['sumEnergy']['display'].replace('"', '""') + '",'
#		csv_record += empty_record if 'sumElapsedDuration' not in a else '"' + a['sumElapsedDuration']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'sumMovingDuration' not in a else '"' + a['sumMovingDuration']['value'].replace('"', '""') + '",'
#		csv_record += empty_record if 'weightedMeanSpeed' not in a else '"' + a['weightedMeanSpeed']['withUnit'].replace('"', '""') + '",'
#		csv_record += empty_record if 'sumDistance' not in a else '"' + a['sumDistance']['withUnit'].replace('"', '""') + '",'
#		csv_record += empty_record if 'minElevation' not in a else '"' + a['minElevation']['withUnit'].replace('"', '""') + '",'
#		csv_record += empty_record if 'gainElevation' not in a else '"' + a['gainElevation']['withUnit'].replace('"', '""') + '",'
#		csv_record += empty_record if 'lossElevation' not in a else '"' + a['lossElevation']['withUnit'].replace('"', '""') + '",'
#		csv_record += empty_record if 'weightedMeanBikeCadence' not in a else '"' + a['weightedMeanBikeCadence']['withUnitAbbr'].replace('"', '""') + '",'
#		csv_record += empty_record if 'maxBikeCadence' not in a else '"' + a['maxBikeCadence']['withUnitAbbr'].replace('"', '""') + '",'
#		csv_record += empty_record if 'weightedMeanAirTemperature' not in a else '"' + a['weightedMeanAirTemperature']['withUnitAbbr'].replace('"', '""') + '",'
#		csv_record += empty_record if 'minAirTemperature' not in a else '"' + a['minAirTemperature']['withUnitAbbr'].replace('"', '""') + '",'
#		csv_record += empty_record if 'maxAirTemperature' not in a else '"' + a['maxAirTemperature']['withUnitAbbr'].replace('"', '""') + '",'
#		csv_record += empty_record if 'activityType' not in a else '"' + a['activityType']['parent']['display'].replace('"', '""') + '",'

		csv_file.write(csv_record.encode('utf8'))

		if args.format == 'gpx':
			# Validate GPX data. If we have an activity without GPS data (e.g., running on a treadmill),
			# Garmin Connect still kicks out a GPX, but there is only activity information, no GPS data.
			# N.B. You can omit the XML parse (and the associated log messages) to speed things up.
			gpx = parseString(data)
			gpx_data_exists = len(gpx.getElementsByTagName('trkpt')) > 0

			if gpx_data_exists:
				print 'Done. GPX data saved.'
			else:
				print 'Done. No track points found.'
		elif args.format == 'original':
			if args.unzip and data_filename[-3:].lower() == 'zip':  # Even manual upload of a GPX file is zipped, but we'll validate the extension.
				print "Unzipping and removing original files...",
				print 'Filesize is: ' + str(stat(data_filename).st_size)
				if stat(data_filename).st_size > 0:
					zip_file = open(data_filename, 'rb')
					z = zipfile.ZipFile(zip_file)
					for name in z.namelist():
						z.extract(name, args.directory)
					zip_file.close()
				else:
					print 'Skipping 0Kb zip file.'
				remove(data_filename)
			print 'Done.'
		else:
			# TODO: Consider validating other formats.
			print 'Done.'
	total_downloaded += num_to_download
# End while loop for multiple chunks.

csv_file.close()

print 'Open CSV output.'
print csv_filename
# call(["open", csv_filename])

print 'Done!'
