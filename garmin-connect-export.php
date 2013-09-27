#!/usr/bin/php
<?php
/*
File: garmin-connect-export.php
Author: Kyle Krafka (https://github.com/kjkjava/)
Original Code: http://www.ciscomonkey.net/gc-to-dm-export/
Date (Original Code): March 28, 2011
Date (Project Started): October 2012
Date (Latest Update): May 27, 2013

Description: 	Use this script to export your fitness data from Garmin Connect.
				See README.md for more information.
*/

// Begin user edits.

// Set your username and password for Garmin Connect here.
// WARNING: This data will be sent in cleartext over HTTP
// so be sure you're on a private connection, and be aware
// that any remote parties storing HTTP requests will have
// your username and password on record.
// For the paranoid, you might want to temporarily change your password
// at https://my.garmin.com/mygarmin/customers/updateAccountInformation.faces
// to use this script.  Also, you might want to revert this
// file back to 'username' and 'password' when you're done.
$username = 'username';
$password = 'password';

// Set this if you need it on your installation.
date_default_timezone_set('America/New_York');
$current_date = date('Y-m-d');

// End of user edits.

// Maximum number of activities you can request at once.  Set and enforced by Garmin.
$limit_maximum = 100;

// URLs for various services
$urlGCLogin    = 'http://connect.garmin.com/signin';
$urlGCSearch   = 'http://connect.garmin.com/proxy/activity-search-service-1.0/json/activities?';
$urlGCActivity = 'http://connect.garmin.com/proxy/activity-service-1.1/gpx/activity/';

// Initially, we need to get a valid session cookie, so we pull the login page.
curl( $urlGCLogin );

// Now we'll actually login
curl( $urlGCLogin . '?login=login&login:signInButton=Sign%20In&javax.faces.ViewState=j_id1&login:loginUsernameField='.$username.'&login:password='.$password.'&login:rememberMe=on');

$activities_directory = './' . $current_date . '_garmin_connect_export';
// Create directory for GPX files
if (!file_exists($activities_directory)) {
    mkdir($activities_directory);
}

$csv_file = fopen($activities_directory . '/activities.csv', 'w+');

// Write header to CSV file
fwrite( $csv_file, "Activity ID,Activity Name,Description,Begin Timestamp,Begin Timestamp (Raw Milliseconds),End Timestamp,End Timestamp (Raw Milliseconds),Device,Activity Parent,Activity Type,Event Type,Activity Time Zone,Max. Elevation,Max. Elevation (Raw),Begin Latitude (Decimal Degrees Raw),Begin Longitude (Decimal Degrees Raw),End Latitude (Decimal Degrees Raw),End Longitude (Decimal Degrees Raw),Average Moving Speed,Average Moving Speed (Raw),Max. Heart Rate (bpm),Average Heart Rate (bpm),Max. Speed,Max. Speed (Raw),Calories,Calories (Raw),Duration (h:m:s),Duration (Raw Seconds),Moving Duration (h:m:s),Moving Duration (Raw Seconds),Average Speed,Average Speed (Raw),Distance,Distance (Raw),Max. Heart Rate (bpm),Min. Elevation,Min. Elevation (Raw),Elevation Gain,Elevation Gain (Raw),Elevation Loss,Elevation Loss (Raw)\n" );

$download_all = false;
if ( $argc > 1 && ( is_numeric( $argv[1] ) ) ) {
	$total_to_download = $argv[1];
} else if ( $argc > 1 && strcasecmp($argv[1], "all") == 0 ) {
	// If the user wants to download all activities, first download one,
	// then the result of that request will tell us how many are available
	// so we will modify the variables then.
	$total_to_download = 1;
	$download_all = true;
} else {
	$total_to_download = 1;
}
$total_downloaded = 0;

// This while loop will download data from the server in multiple chunks, if necessary
while( $total_downloaded < $total_to_download ) {
	$num_to_download = ($total_to_download - $total_downloaded > 100) ? 100 : ($total_to_download - $total_downloaded); // Maximum of 100... 400 return status if over 100.  So download 100 or whatever remains if less than 100.

	// Query Garmin Connect
	$search_opts = array(
		'start' => $total_downloaded,
		'limit' => $num_to_download
		);

	$result = curl( $urlGCSearch . http_build_query( $search_opts ) );
	$json = json_decode( $result );

	if ( ! $json ) {
		echo "Error: ";	
		switch(json_last_error()) {
			case JSON_ERROR_DEPTH:
				echo ' - Maximum stack depth exceeded';
				break;
			case JSON_ERROR_CTRL_CHAR:
				echo ' - Unexpected control character found';
				break;
			case JSON_ERROR_SYNTAX:
				echo ' - Syntax error, malformed JSON';
				break;
		}
		echo PHP_EOL;
		var_dump( $result );
		die();
	}

	$search = $json->{'results'}->{'search'};

	if ( $download_all ) {
		// Modify $total_to_download based on how many activities the server reports
		$total_to_download = intval( $search->{'totalFound'} );
		// Do it only once
		$download_all = false;
	}

	// Pull out just the list of activities
	$activities = $json->{'results'}->{'activities'};

	// Process each activity.
	foreach ( $activities as $a ) {
		// Display which entry we're working on.
		print "Garmin Connect activity: [" . $a->{'activity'}->{'activityId'} . "] ";
		print $a->{'activity'}->{'beginTimestamp'}->{'display'}  . ": ";
		print $a->{'activity'}->{'activityName'}->{'value'} . "\n";

		// Write data to CSV
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'activityId'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'activityName'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'activityDescription'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'beginTimestamp'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'beginTimestamp'}->{'millis'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'endTimestamp'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'endTimestamp'}->{'millis'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'device'}->{'display'} . " " . $a->{'activity'}->{'device'}->{'version'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'activityType'}->{'parent'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'activityType'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'eventType'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'activityTimeZone'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxElevation'}->{'withUnit'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxElevation'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'beginLatitude'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'beginLongitude'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'endLatitude'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'endLongitude'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'weightedMeanMovingSpeed'}->{'display'}) . "\"," ); // The units vary between Minutes per Mile and mph, but withUnit always displays "Minutes per Mile"
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'weightedMeanMovingSpeed'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxHeartRate'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'weightedMeanHeartRate'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxSpeed'}->{'display'}) . "\"," ); // The units vary between Minutes per Mile and mph, but withUnit always displays "Minutes per Mile"
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxSpeed'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumEnergy'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumEnergy'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumElapsedDuration'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumElapsedDuration'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumMovingDuration'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumMovingDuration'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'weightedMeanSpeed'}->{'withUnit'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'weightedMeanSpeed'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumDistance'}->{'withUnit'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'sumDistance'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'minHeartRate'}->{'display'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxElevation'}->{'withUnit'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'maxElevation'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'gainElevation'}->{'withUnit'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'gainElevation'}->{'value'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'lossElevation'}->{'withUnit'}) . "\"," );
		fwrite( $csv_file, "\"" . str_replace("\"", "\"\"", $a->{'activity'}->{'lossElevation'}->{'value'}) . "\"");
		fwrite( $csv_file, "\n");

		// Download the GPX file from Garmin Connect
		// TODO: Consider using TCX files?  Does Garmin Connect include heart rate data in TCX downloads?
		print "\tDownloading GPX file... ";

		$gpx_filename = $activities_directory . '/activity_' . $a->{'activity'}->{'activityId'} . '.gpx';
		$save_file = fopen( $gpx_filename, 'w+' );
		$curl_opts = array(
			CURLOPT_FILE => $save_file
			);
		curl( $urlGCActivity . $a->{'activity'}->{'activityId'} . '?full=true', array(), array(), $curl_opts );
		fclose( $save_file );

		// Validate the GPX data.  If we have an activity without GPS data (e.g. running on a treadmill),
		// Garmin Connect still kicks out a GPX, but there is only activity information, no GPS data.
		$gpx = simplexml_load_file( $gpx_filename, 'SimpleXMLElement', LIBXML_NOCDATA );
		$gpxdataexists = ( count( $gpx->trk->trkseg->trkpt ) > 0);

		if ( $gpxdataexists ) {
			print "Done. GPX data saved.\n";
		} else {
			print "Done. No track points found.\n";
		}
	}

	$total_downloaded += $num_to_download;

// End while loop for multiple chunks
}

fclose($csv_file);

print "Done!\n\n";
// End

function curl( $url, $post = array(), $head = array(), $opts = array() )
{
	$cookie_file = '/tmp/cookies.txt';
	$ch = curl_init();

	//curl_setopt( $ch, CURLOPT_VERBOSE, 1 );
	curl_setopt( $ch, CURLOPT_URL, $url );
	curl_setopt( $ch, CURLOPT_RETURNTRANSFER, 1 );	
	curl_setopt( $ch, CURLOPT_ENCODING, "gzip" );
	curl_setopt( $ch, CURLOPT_COOKIEFILE, $cookie_file );
	curl_setopt( $ch, CURLOPT_COOKIEJAR, $cookie_file );
	curl_setopt( $ch, CURLOPT_FOLLOWLOCATION, 1 );

	foreach ( $opts as $k => $v ) {
		curl_setopt( $ch, $k, $v );
	}

	if ( count( $post ) > 0 ) {
		// POST mode
		curl_setopt( $ch, CURLOPT_POST, 1 );
		curl_setopt( $ch, CURLOPT_POSTFIELDS, $post );
	}
	else {
		curl_setopt( $ch, CURLOPT_HTTPHEADER, $head );
		curl_setopt( $ch, CURLOPT_CRLF, 1 );
	}

	$success = curl_exec( $ch );

	if ( curl_errno( $ch ) !== 0 ) {
		throw new Exception( sprintf( '%s: CURL Error %d: %s', __CLASS__, curl_errno( $ch ), curl_error( $ch ) ) );
	}

	if ( curl_getinfo( $ch, CURLINFO_HTTP_CODE ) !== 200 ) {
		if ( curl_getinfo( $ch, CURLINFO_HTTP_CODE ) !== 201 ) {
			throw new Exception( sprintf( 'Bad return code(%1$d) for: %2$s', curl_getinfo( $ch, CURLINFO_HTTP_CODE ), $url ) );
		}
	}

	curl_close( $ch );
	return $success;
}

?>
