garmin-connect-export
=====================

Download a copy of your Garmin Connect data, including stats and GPX tracks.

Description
-----------
This script will backup your personal Garmin Connect data. All downloaded data will go into a directory called `YYYY-MM-DD_garmin_connect_export/` in the current working directory. Activity records and details will go into a CSV file called `activities.csv`. GPX files (or whatever format you specify) containing track data, activity title, and activity descriptions are saved as well, using the Activity ID.

If there is no GPS track data (e.g., due to an indoor treadmill workout), a data file is still saved. If the GPX format is used, activity title and description data are saved. If the original format is used, Garmin may not provide a file at all and an empty file will be created. For activities where a GPX file was uploaded, Garmin may not have a TCX file available for download, so an empty file will be created. Since GPX is the only format Garmin should have for every activity, it is the default and preferred download format.

If you have many activities, you may find that this script crashes with an "Operation timed out" message. Just run the script again and it will pick up where it left off.

Usage
-----
Usage: `python gcexport.py [how_many] [format] [directory]`

`[how_many]` specifies the number of recent activities you wish to download. You may also specify `all` to download everything. The default is `1`.

`[format]` specifies the desired export format. Valid formats are `gpx`, `tcx`, `original` or `json`. The default is `gpx`. When using `original`, a ZIP file is exported that contains the initial input format (e.g., FIT files). When using `json`, a JSON file is created with all the metadata.

`[directory]` specifies the output directory for the CSV file and the GPX files. The default is a subdirectory with the format `YYYY-MM-DD_garmin_connect_export`. If the directory does not exist, it will be created. If it does exist, activities with existing GPX files will be skipped and the CSV file will be appended to. This should make it easy to restart failed downloads without repeating work. This also allows you to specify a master directory so that this script can be run regularly (to maintain an up-to-date backup) without re-downloading everything.

Example: `python gcexport.py all` will download all of your data to a dated directory.

Alternatively, you may run it with `./gcexport.py [how_many] [format] [directory]` if you set the file as executable (i.e., `chmod u+x gcexport.py`).

Of course, you must have Python installed to run this. Most Mac and Linux users should already have it. Also, you should have some basic command line experience.

Data
----
This tool is not guaranteed to get all of your data, or even download it correctly. I have only tested it out on my account and it works fine, but different account settings or different data types could potentially cause problems. Also, because this is not an official feature of Garmin Connect, Garmin may very well make changes that break this utility (and they certainly have since I created this project).

If you want to see all of the raw data that Garmin hands to this script, just print out the contents of the `json_results` variable. I believe most everything that is useful has been included in the CSV file. You will notice some columns have been duplicated: one column geared towards display, and another column fit for number crunching (labeled with "Raw"). I hope this is most useful. Some information is missing, such as "Favorite" or "Avg Strokes."  This is available from the web interface, but is not included in data given to this script.

Also, be careful with speed data, because sometimes it is measured as a pace (minutes per mile) and sometimes it is measured as a speed (miles per hour).

Garmin Connect API
------------------
This script is for personal use only. It simulates a standard user session (i.e., in the browser), logging in using cookies and an authorization ticket. This makes the script pretty brittle. If you're looking for a more reliable option, particularly if you wish to use this for some production service, Garmin does offer a paid API service.

History
-------
The original project was written in PHP (now in the `old` directory), based on "Garmin Connect export to Dailymile" code at http://www.ciscomonkey.net/gc-to-dm-export/ (link has been down for a while). It no longer works due to the way Garmin handles logins. It could be updated, but I decided to rewrite everything in Python for the latest version.

Contributions
-------------
Contributions are welcome, particularly if this script stops working with Garmin Connect. You may consider opening a GitHub Issue first. New features, however simple, are encouraged.

License
-------
[MIT](https://github.com/kjkjava/garmin-connect-export/blob/master/LICENSE) &copy; 2015 Kyle Krafka

Thank You
---------
Thanks for using this script and I hope you find it as useful as I do! :smile:
