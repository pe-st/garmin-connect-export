garmin-connect-export
=====================

Download a copy of your Garmin Connect data, including stats and GPX tracks.

Description
-----------
This script will backup your personal Garmin Connect data.  All downloaded data will go into a directory called `YYYY-MM-DD_garmin_connect_export/` in the current working directory.  Activity records and details will go in a CSV file called `activities.csv`.  GPX files containing track data, activity title, and activity descriptions are saved as well, using the Activity ID.  If there is no GPS track data (e.g. due to an indoor treadmill workout), the GPX file is still saved with only activity title and description inside.

Usage
-----
This could be easily modified to be a web application, as it is PHP, but the intended usage is from the command line.

Usage: `php -f garmin-connect-export.php [how_many]`

You should change `[how_many]` to the number of recent activities you wish to download.  The default is 1 and `all` will download all activities.

Alternatively, you may run it with `./garmin-connect-export.php [how_many]` if you set the file as executable (i.e. `chmod u+x garmin-connect-export.php`).

Of course, you must have PHP installed to run this.  Most Mac and Linux users should already have it.

Data
----
This tool is not guaranteed to get all of your data, or even download it correctly.  I have only tested it out on my account and it works fine, but different account settings or different data sources may cause problems.  Also, because this is not an official feature of Garmin Connect, Garmin may very well make changes that break this utility.

If you want to see all of the raw data that Garmin hands to this program, just print out the contents of the `$json` variable.  I believe most everything that is useful has been included in the CSV file.  You will notice some columns have been duplicated: one column geared towards display, and another columns fit for number crunching (labeled with "Raw").  I hope this is most useful.  Some information is missing, such as "Favorite" or "Avg Strokes."  This is available from the web interface, but is not included in data given to this program.

Also, be careful with speed data, because sometimes it is measured as a pace (minutes per mile) and sometimes it is measured as a speed (miles per hour).

Credits
-------
Code based on "Garmin Connect export to Dailymile" code at http://www.ciscomonkey.net/gc-to-dm-export/.  This project would not be possible without the original author's work!

Contributions are welcome, but you might want to open a GitHub Issue if you are not sure whether or not I will accept it!

Thank You
---------
Thanks for using this program and I hope you find it as useful as I do!
