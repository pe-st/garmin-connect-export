#!/usr/bin/php
<?php
/*
This script will backup your personal Garmin Connect data.
Activity records and details will go in a CSV file called     <-- TODO
'YYYY-MM-DD_garmin_connect_backup.csv' saved to the current
working directory.  GPX files containing track data,
activity title, and activity descriptions, will be saved in a
folder within the current working directory, called
'YYYY-MM-DD_garmin_connect_backup_gpx'.

Code is intended to be run from the command line as so:
	php -f backup_garmin_connect.php [how_many]
where [how_many] is how many recent activities to download.
The default is 1 and 'all' will download all activities.      <-- TODO

Code based on Garmin Connect export to Dailymile code
on http://www.ciscomonkey.net/gc-to-dm-export/ by rmullins@ciscomonkey.net
This project would not be possible without his work.

-Kyle Krafka, Oct. 24, 2012
*/

// TODO: Would it be better to use TCX files?  I believe they can hold heart rate data, while GPX cannot!

// Set your username and password for Garmin Connect here.
// WARNING: This data will be send in cleartext over HTTP
// so be sure you're on a private connection, and be aware
// that any remote parties storing HTTP requests will have
// your username and password right there.
// It might be best just to temporarily change your password
// at https://my.garmin.com/mygarmin/customers/updateAccountInformation.faces
// to use this script.
$username = 'username';
$password = 'password';

// Set this if you need it on your installation.
date_default_timezone_set('America/New_York');
$current_date = date('Y-m-d'); // TODO is this string format correct!?

// End of user edits.

$limit_maximum = 100; // Maximum number of activities you can request at once

// URLs for various services
$urlGCLogin    = 'http://connect.garmin.com/signin';
$urlGCSearch   = 'http://connect.garmin.com/proxy/activity-search-service-1.0/json/activities?';
$urlGCActivity = 'http://connect.garmin.com/proxy/activity-service-1.1/gpx/activity/';

// Initially, we need to get a valid session cookie, so we pull the login page.
curl( $urlGCLogin );

// Now we'll actually login
curl( $urlGCLogin . '?login=login&login:signInButton=Sign%20In&javax.faces.ViewState=j_id1&login:loginUsernameField='.$username.'&login:password='.$password.'&login:rememberMe=on');


$csv_file = fopen($current_date . '_garmin_connect_backup.csv', 'w+');

$activities_directory = './' . $current_date . '_garmin_connect_backup';
// Create directory for gpx files
if (!file_exists($activities_directory)) {
    mkdir($activities_directory);
}

// Write header to CSV
fwrite( $csv_file, "Activity ID,Activity Name,Description,Begin Timestamp,Begin Timestamp (Raw Milliseconds),End Timestamp,End Timestamp (Raw Milliseconds),Device,Activity Parent,Activity Type,Event Type,Activity Time Zone,Max. Elevation,Max. Elevation (Raw),Begin Latitude (Decimal Degrees Raw),Begin Longitude (Decimal Degrees Raw),End Latitude (Decimal Degrees Raw),End Longitude (Decimal Degrees Raw),Average Moving Speed,Average Moving Speed (Raw),Max. Heart Rate (bpm),Average Heart Rate (bpm),Max. Speed,Max. Speed (Raw),Calories,Calories (Raw),Duration (h:m:s),Duration (Raw Seconds),Moving Duration (h:m:s),Moving Duration (Raw Seconds),Average Speed,Average Speed (Raw),Distance,Distance (Raw),Max. Heart Rate (bpm),Min. Elevation,Min. Elevation (Raw),Elevation Gain,Elevation Gain (Raw),Elevation Loss,Elevation Loss (Raw)\n" );

$download_all = false;
if ( ! empty( $argc ) && ( is_numeric( $argv[1] ) ) ) {
	$total_to_download = $argv[1];
} else if ( ! empty( $argc ) && strcasecmp($argv[1], "all") == 0 ) {
	// If the user wants to download all activities, first download one,
	// then the result of that request will tell us how many are available
	// so we will modify the variables then.
	$total_to_download = 1;
	$download_all = true;
} else {
	$total_to_download = 1;
}
$total_downloaded = 0;

// This loop will download multiple chunks if needed
while( $total_downloaded < $total_to_download ) {
	$num_to_download = ($total_to_download - $total_downloaded > 100) ? 100 : ($total_to_download - $total_downloaded); // Maximum of 100... 400 return status if over 100.  So download 100 or whatever remains if less than 100.

	// Now we search GC for the latest activity.
	// We support calling multiples from command line if specified,
	// otherwise, only pull the last activity.                        <-- TODO: update doc
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
		$total_to_download = intval( $search->{'totalFound'} );
		$download_all = false;
	}

	// Pull out just the list of activites
	$activities = $json->{'results'}->{'activities'};

	// Process each activity.
	foreach ( $activities as $a ) {
		// Display which entry we're working on.
		print "Garmin Connect activity: [" . $a->{'activity'}->{'activityId'} . "] ";
		print $a->{'activity'}->{'beginTimestamp'}->{'display'}  . ": ";
		print $a->{'activity'}->{'activityName'}->{'value'} . "\n";

		// Write data to CSV
		// TODO: put these in a better order
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

		// Download the GPX file from GC.
		print "\tDownloading .GPX ... ";

		$gpx_filename = $activities_directory . '/activity_' . $a->{'activity'}->{'activityId'} . '.gpx';
		$save_file = fopen( $gpx_filename, 'w+' );
		$curl_opts = array(
			CURLOPT_FILE => $save_file
			);
		curl( $urlGCActivity . $a->{'activity'}->{'activityId'} . '?full=true', array(), array(), $curl_opts );
		fclose( $save_file );

		// Now we need to validate the .GPX.  If we have an activity without GPS data, GC still kicks out a .GPX file for it.
		// As I ride a trainer in the bad months, this is a common occurance for me, as I would imagine it would be for anyone
		// using a treadmill as well.
		$gpx = simplexml_load_file( $gpx_filename, 'SimpleXMLElement', LIBXML_NOCDATA );
		$gpxdataexists = ( count( $gpx->trk->trkseg->trkpt ) > 0);

		if ( $gpxdataexists ) {
			print "Done. GPX data saved.\n";
		} else {
			// We don't need to create a track, as we have no GPS track data. :(
			print "Done. No track points found.\n";
		}
	}

	$total_downloaded += $num_to_download;

// end while for multiple chunks
}

fclose($csv_file);

print "\n\n";
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
