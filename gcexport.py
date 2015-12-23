#!/usr/bin/python

"""
File: gcexport.py
Author: Kyle Krafka (https://github.com/kjkjava/)
Date: April 28, 2015

Description:	Use this script to export your fitness data from Garmin Connect.
				See README.md for more information.
"""

from urllib import urlencode
from datetime import datetime
from getpass import getpass
from sys import argv
from os.path import isdir
from os.path import isfile
from os import mkdir
from os import remove
from xml.dom.minidom import parseString

import urllib2, cookielib, json
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

# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers={}):
	request = urllib2.Request(url)
	request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1337 Safari/537.36')  # Tell Garmin we're some supported browser.
	for header_key, header_value in headers.iteritems():
		request.add_header(header_key, header_value)
	if post:
		post = urlencode(post)  # Convert dictionary to POST parameter string.
	response = opener.open(request, data=post)  # This line may throw a urllib2.HTTPError.

	# N.B. urllib2 will follow any 302 redirects. Also, the "open" call above may throw a urllib2.HTTPError which is checked for below.
	if response.getcode() != 200:
		raise Exception('Bad return code (' + response.getcode() + ') for: ' + url)

	return response.read()

print 'Welcome to Garmin Connect Exporter!'

# Create directory for data files.
if isdir(args.directory):
	print 'Warning: Output directory already exists. Will skip already-downloaded files and append to the CSV file.'

username = args.username if args.username else raw_input('Username: ')
password = args.password if args.password else getpass()

# Maximum number of activities you can request at once.  Set and enforced by Garmin.
limit_maximum = 100

# URLs for various services.
url_gc_login     = 'https://sso.garmin.com/sso/login?service=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&webhost=olaxpw-connect04&source=https%3A%2F%2Fconnect.garmin.com%2Fen-US%2Fsignin&redirectAfterAccountLoginUrl=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&redirectAfterAccountCreationUrl=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&gauthHost=https%3A%2F%2Fsso.garmin.com%2Fsso&locale=en_US&id=gauth-widget&cssUrl=https%3A%2F%2Fstatic.garmincdn.com%2Fcom.garmin.connect%2Fui%2Fcss%2Fgauth-custom-v1.1-min.css&clientId=GarminConnect&rememberMeShown=true&rememberMeChecked=false&createAccountShown=true&openCreateAccount=false&usernameShown=false&displayNameShown=false&consumeServiceTicket=false&initialFocus=true&embedWidget=false&generateExtraServiceTicket=false'
url_gc_post_auth = 'https://connect.garmin.com/post-auth/login?'
url_gc_search    = 'http://connect.garmin.com/proxy/activity-search-service-1.0/json/activities?'
url_gc_gpx_activity = 'http://connect.garmin.com/proxy/activity-service-1.1/gpx/activity/'
url_gc_tcx_activity = 'http://connect.garmin.com/proxy/activity-service-1.1/tcx/activity/'
url_gc_original_activity = 'http://connect.garmin.com/proxy/download-service/files/activity/'

# Initially, we need to get a valid session cookie, so we pull the login page.
http_req(url_gc_login)

# Now we'll actually login.
post_data = {'username': username, 'password': password, 'embed': 'true', 'lt': 'e1s1', '_eventId': 'submit', 'displayNameRequired': 'false'}  # Fields that are passed in a typical Garmin login.
http_req(url_gc_login, post_data)

# Get the key.
# TODO: Can we do this without iterating?
login_ticket = None
for cookie in cookie_jar:
	if cookie.name == 'CASTGC':
		login_ticket = cookie.value
		break

if not login_ticket:
	raise Exception('Did not get a ticket cookie. Cannot log in. Did you enter the correct username and password?')

# Chop of 'TGT-' off the beginning, prepend 'ST-0'.
login_ticket = 'ST-0' + login_ticket[4:]

http_req(url_gc_post_auth + 'ticket=' + login_ticket)

# We should be logged in now.
if not isdir(args.directory):
	mkdir(args.directory)

csv_filename = args.directory + '/activities.csv'
csv_existed = isfile(csv_filename)

csv_file = open(csv_filename, 'a')

# Write header to CSV file
if not csv_existed:
	csv_file.write('Activity ID,Activity Name,Description,Begin Timestamp,Begin Timestamp (Raw Milliseconds),End Timestamp,End Timestamp (Raw Milliseconds),Device,Activity Parent,Activity Type,Event Type,Activity Time Zone,Max. Elevation,Max. Elevation (Raw),Begin Latitude (Decimal Degrees Raw),Begin Longitude (Decimal Degrees Raw),End Latitude (Decimal Degrees Raw),End Longitude (Decimal Degrees Raw),Average Moving Speed,Average Moving Speed (Raw),Max. Heart Rate (bpm),Average Heart Rate (bpm),Max. Speed,Max. Speed (Raw),Calories,Calories (Raw),Duration (h:m:s),Duration (Raw Seconds),Moving Duration (h:m:s),Moving Duration (Raw Seconds),Average Speed,Average Speed (Raw),Distance,Distance (Raw),Max. Heart Rate (bpm),Min. Elevation,Min. Elevation (Raw),Elevation Gain,Elevation Gain (Raw),Elevation Loss,Elevation Loss (Raw)\n')

download_all = False
if args.count == 'all':
	# If the user wants to download all activities, first download one,
	# then the result of that request will tell us how many are available
	# so we will modify the variables then.
	total_to_download = 1
	download_all = True
else:
	total_to_download = int(args.count)
total_downloaded = 0

# This while loop will download data from the server in multiple chunks, if necessary.
while total_downloaded < total_to_download:
	# Maximum of 100... 400 return status if over 100.  So download 100 or whatever remains if less than 100.
	if total_to_download - total_downloaded > 100:
		num_to_download = 100
	else:
		num_to_download = total_to_download - total_downloaded

	search_params = {'start': total_downloaded, 'limit': num_to_download}
	# Query Garmin Connect
	result = http_req(url_gc_search + urlencode(search_params))
	json_results = json.loads(result)  # TODO: Catch possible exceptions here.
		

	search = json_results['results']['search']

	if download_all:
		# Modify total_to_download based on how many activities the server reports.
		total_to_download = int(search['totalFound'])
		# Do it only once.
		download_all = False

	# Pull out just the list of activities.
	activities = json_results['results']['activities']

	# Process each activity.
	for a in activities:
		# Display which entry we're working on.
		print 'Garmin Connect activity: [' + a['activity']['activityId'] + ']',
		print a['activity']['activityName']['value']
		print '\t' + a['activity']['beginTimestamp']['display'] + ',',
		if 'sumElapsedDuration' in a['activity']:
			print a['activity']['sumElapsedDuration']['display'] + ',',
		else:
			print '??:??:??,',
		if 'sumDistance' in a['activity']:
			print a['activity']['sumDistance']['withUnit']
		else:
			print '0.00 Miles'

		if args.format == 'gpx':
			data_filename = args.directory + '/activity_' + a['activity']['activityId'] + '.gpx'
			download_url = url_gc_gpx_activity + a['activity']['activityId'] + '?full=true'
			file_mode = 'w'
		elif args.format == 'tcx':
			data_filename = args.directory + '/activity_' + a['activity']['activityId'] + '.tcx'
			download_url = url_gc_tcx_activity + a['activity']['activityId'] + '?full=true'
			file_mode = 'w'
		elif args.format == 'original':
			data_filename = args.directory + '/activity_' + a['activity']['activityId'] + '.zip'
			fit_filename = args.directory + '/' + a['activity']['activityId'] + '.fit'
			download_url = url_gc_original_activity + a['activity']['activityId']
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
				raise Exception('Failed. Got an unexpected HTTP error (' + str(e.code) + ').')

		save_file = open(data_filename, file_mode)
		save_file.write(data)
		save_file.close()

		# Write stats to CSV.
		empty_record = '"",'

		csv_record = ''

		csv_record += empty_record if 'activityId' not in a['activity'] else '"' + a['activity']['activityId'].replace('"', '""') + '",'
		csv_record += empty_record if 'activityName' not in a['activity'] else '"' + a['activity']['activityName']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'activityDescription' not in a['activity'] else '"' + a['activity']['activityDescription']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'beginTimestamp' not in a['activity'] else '"' + a['activity']['beginTimestamp']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'beginTimestamp' not in a['activity'] else '"' + a['activity']['beginTimestamp']['millis'].replace('"', '""') + '",'
		csv_record += empty_record if 'endTimestamp' not in a['activity'] else '"' + a['activity']['endTimestamp']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'endTimestamp' not in a['activity'] else '"' + a['activity']['endTimestamp']['millis'].replace('"', '""') + '",'
		csv_record += empty_record if 'device' not in a['activity'] else '"' + a['activity']['device']['display'].replace('"', '""') + ' ' + a['activity']['device']['version'].replace('"', '""') + '",'
		csv_record += empty_record if 'activityType' not in a['activity'] else '"' + a['activity']['activityType']['parent']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'activityType' not in a['activity'] else '"' + a['activity']['activityType']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'eventType' not in a['activity'] else '"' + a['activity']['eventType']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'activityTimeZone' not in a['activity'] else '"' + a['activity']['activityTimeZone']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'maxElevation' not in a['activity'] else '"' + a['activity']['maxElevation']['withUnit'].replace('"', '""') + '",'
		csv_record += empty_record if 'maxElevation' not in a['activity'] else '"' + a['activity']['maxElevation']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'beginLatitude' not in a['activity'] else '"' + a['activity']['beginLatitude']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'beginLongitude' not in a['activity'] else '"' + a['activity']['beginLongitude']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'endLatitude' not in a['activity'] else '"' + a['activity']['endLatitude']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'endLongitude' not in a['activity'] else '"' + a['activity']['endLongitude']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'weightedMeanMovingSpeed' not in a['activity'] else '"' + a['activity']['weightedMeanMovingSpeed']['display'].replace('"', '""') + '",'  # The units vary between Minutes per Mile and mph, but withUnit always displays "Minutes per Mile"
		csv_record += empty_record if 'weightedMeanMovingSpeed' not in a['activity'] else '"' + a['activity']['weightedMeanMovingSpeed']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'maxHeartRate' not in a['activity'] else '"' + a['activity']['maxHeartRate']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'weightedMeanHeartRate' not in a['activity'] else '"' + a['activity']['weightedMeanHeartRate']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'maxSpeed' not in a['activity'] else '"' + a['activity']['maxSpeed']['display'].replace('"', '""') + '",'  # The units vary between Minutes per Mile and mph, but withUnit always displays "Minutes per Mile"
		csv_record += empty_record if 'maxSpeed' not in a['activity'] else '"' + a['activity']['maxSpeed']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumEnergy' not in a['activity'] else '"' + a['activity']['sumEnergy']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumEnergy' not in a['activity'] else '"' + a['activity']['sumEnergy']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumElapsedDuration' not in a['activity'] else '"' + a['activity']['sumElapsedDuration']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumElapsedDuration' not in a['activity'] else '"' + a['activity']['sumElapsedDuration']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumMovingDuration' not in a['activity'] else '"' + a['activity']['sumMovingDuration']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumMovingDuration' not in a['activity'] else '"' + a['activity']['sumMovingDuration']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'weightedMeanSpeed' not in a['activity'] else '"' + a['activity']['weightedMeanSpeed']['withUnit'].replace('"', '""') + '",'
		csv_record += empty_record if 'weightedMeanSpeed' not in a['activity'] else '"' + a['activity']['weightedMeanSpeed']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumDistance' not in a['activity'] else '"' + a['activity']['sumDistance']['withUnit'].replace('"', '""') + '",'
		csv_record += empty_record if 'sumDistance' not in a['activity'] else '"' + a['activity']['sumDistance']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'minHeartRate' not in a['activity'] else '"' + a['activity']['minHeartRate']['display'].replace('"', '""') + '",'
		csv_record += empty_record if 'maxElevation' not in a['activity'] else '"' + a['activity']['maxElevation']['withUnit'].replace('"', '""') + '",'
		csv_record += empty_record if 'maxElevation' not in a['activity'] else '"' + a['activity']['maxElevation']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'gainElevation' not in a['activity'] else '"' + a['activity']['gainElevation']['withUnit'].replace('"', '""') + '",'
		csv_record += empty_record if 'gainElevation' not in a['activity'] else '"' + a['activity']['gainElevation']['value'].replace('"', '""') + '",'
		csv_record += empty_record if 'lossElevation' not in a['activity'] else '"' + a['activity']['lossElevation']['withUnit'].replace('"', '""') + '",'
		csv_record += empty_record if 'lossElevation' not in a['activity'] else '"' + a['activity']['lossElevation']['value'].replace('"', '""') + '"'
		csv_record += '\n'

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
				zip_file = open(data_filename, 'rb')
				z = zipfile.ZipFile(zip_file)
				for name in z.namelist():
					z.extract(name, args.directory)
				zip_file.close()
				remove(data_filename)
			print 'Done.'
		else:
			# TODO: Consider validating other formats.
			print 'Done.'
	total_downloaded += num_to_download
# End while loop for multiple chunks.

csv_file.close()

print 'Done!'
