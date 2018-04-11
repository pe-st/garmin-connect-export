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
You will need a little experience running things from the command line to use this script. That said, here are the usage details from the `--help` flag:

```
usage: gcexport.py [-h] [--version] [--username [USERNAME]]
                   [--password [PASSWORD]] [-c [COUNT]]
                   [-f [{gpx,tcx,original}]] [-d [DIRECTORY]] [-u]

optional arguments:
  -h, --help            show this help message and exit
  --version             print version and exit
  --username [USERNAME]
                        your Garmin Connect username (otherwise, you will be
                        prompted)
  --password [PASSWORD]
                        your Garmin Connect password (otherwise, you will be
                        prompted)
  -c [COUNT], --count [COUNT]
                        number of recent activities to download, or 'all'
                        (default: 1)
  -f [{gpx,tcx,original,json}], --format [{gpx,tcx,original,json}]
                        export format; can be 'gpx', 'tcx', 'original' or 'json'
                        When using `json`, only the activity's metadata is exported.
                        (default: 'gpx')
  -d [DIRECTORY], --directory [DIRECTORY]
                        the directory to export to (default: './YYYY-MM-
                        DD_garmin_connect_export')
  -u, --unzip           if downloading ZIP files (format: 'original'), unzip
                        the file and removes the ZIP file
```

Examples:
`python gcexport.py --count all` will download all of your data to a dated directory.

`python gcexport.py -d ~/MyActivities -c 3 -f original -u --username bobbyjoe --password bestpasswordever1` will download your three most recent activities in the FIT file format (or whatever they were uploaded as) into the `~/MyActivities` directory (unless they already exist). Using the `--username` and `--password` flags are not recommended because your password will be stored in your command line history. Instead, omit them to be prompted (and note that nothing will be displayed when you type your password).

Alternatively, you may run it with `./gcexport.py` if you set the file as executable (i.e., `chmod u+x gcexport.py`).

Of course, you must have Python installed to run this. Most Mac and Linux users should already have it. Also, as stated above, you should have some basic command line experience.

Data
----
This tool is not guaranteed to get all of your data, or even download it correctly. I have only tested it out on my account and it works fine, but different account settings or different data types could potentially cause problems. Also, because this is not an official feature of Garmin Connect, Garmin may very well make changes that break this utility (and they certainly have since I created this project).

If you want to see all of the raw data that Garmin hands to this script, just print out the contents of the `json_results` variable. I believe most everything that is useful has been included in the CSV file. You will notice some columns have been duplicated: one column geared towards display, and another column fit for number crunching (labeled with "Raw"). I hope this is most useful. Some information is missing, such as "Favorite" or "Avg Strokes."  This is available from the web interface, but is not included in data given to this script.

Also, be careful with speed data, because sometimes it is measured as a pace (minutes per mile) and sometimes it is measured as a speed (miles per hour).

Garmin Connect API
------------------
This script is for personal use only. It simulates a standard user session (i.e., in the browser), logging in using cookies and an authorization ticket. This makes the script pretty brittle. If you're looking for a more reliable option, particularly if you wish to use this for some production service, Garmin does offer a paid API service.

### REST endpoints

As this script doesn't use the paid API, the endpoints to use are known by reverse engineering browser sessions. And as the Garmin Connect website changes over time, chances are that this script gets broken.

Small history of the endpoint used by `gcexport.py` to get a list of activities:

- [activity-search-service-1.0](https://connect.garmin.com/proxy/activity-search-service-1.0/json/activities): initial endpoint used since 2015, worked at least until January 2018
- [activity-search-service-1.2](https://connect.garmin.com/proxy/activity-search-service-1.2/json/activities): endpoint introduced in `gcexport.py` in August 2016. In March 2018 this still works, but doesn't allow you to fetch more than 20 activities, even split over multiple calls (when doing three consecutive calls with 1,19,19 as `limit` parameter, the third one fails with HTTP error 500). The JSON returned by this endpoint however is quite rich (see example in the `json` folder).
- [activitylist-service](https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities): endpoint introduced in `gcexport.py` in March 2018. The JSON returned by this endpoint is very different from the activity-search-service-1.2 one (also here see the example in the `json` folder), e.g.
    - it is concise and offers no redundant information (e.g. only speed, not speed and pace)
    - the units are not explicitly given and must be deducted (e.g. the speed unit is m/s)
    - there is less information, e.g. there is only one set of elevation values (not both corrected and uncorrected), and other values like minimum heart rate are missing.
    - some other information is available only as an ID (e.g. `timeZoneId` or `deviceId`), and more complete information
      is available by further REST calls (one for each activity and additional ones for device information)

### Limitations of Data Provided by Current Endpoints and Choices Made

- The timezones provided are just the names (e.g. for Central European Time CET you can get either "Europe/Paris" or "(GMT+01:00) Central European Time"), but not the exact offset. Note that the "GMT+01:00" part of the name is hardcoded, so in summer (daylight savings time) Garmin Connect still uses +01:00 in the name even if the offset then is +02:00. To get the offset you need to calculate the difference between the startTimeLocal and the startTimeGMT. The current script writes the calculate offset into the CSV file.
- The elevation is either uncorrected or corrected, with a flag telling which. The current endpoints don't provide both sets of elevations anymore (older endpoints did provide them both, but these endpoints don't work anymore)
- The speed written to the CSV file is the speed in km/h for most activities and the pace (min/km) for pedestrial activities (running, walking, hiking). This is easy to change though.



History
-------
The original project was written in PHP (formerly in the `old` directory, now deleted), based on "Garmin Connect export to Dailymile" code at http://www.ciscomonkey.net/gc-to-dm-export/ (link has been down for a while). It no longer works due to the way Garmin handles logins. It could be updated, but I decided to rewrite everything in Python for the latest version.

Contributions
-------------
Contributions are welcome, particularly if this script stops working with Garmin Connect. You may consider opening a GitHub Issue first. New features, however simple, are encouraged.

License
-------
[MIT](https://github.com/kjkjava/garmin-connect-export/blob/master/LICENSE) &copy; 2015 Kyle Krafka

Thank You
---------
Thanks for using this script and I hope you find it as useful as I do! :smile:
