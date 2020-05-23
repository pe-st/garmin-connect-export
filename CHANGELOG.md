# Changelog for the Garmin Connect Exporter

This changelog is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).


## 3.0.1 - 2020-05-23

- fixed: `--subdir` was broken in 3.0.0 by the migration to Python 3 (reported by @jamorris, issue #37)
- changed: moved unit tests for `resolve_path` from **unittest** framework to **pytest**


## 3.0.0 - 2020-05-16

- added: support for Python 3, thanks to @telemaxx and @bartskowron
- added: file `CONTRIBUTING.md` and moved some parts of `README.md` into it
- changed: with Windows the script now uses backslashes as path separator
- changed: default Git branch is now `master` (the old `develop` branch is kept for the time being)
- fixed: `-fp` option for `original` format


## 2.3.3 - 2020-01-30

- fixed: skipping existing `.fit` files didn't work (reported by @fellrnr, issue #25)


## 2.3.2 - 2019-08-25

- added: parent activity type "Winter Sports"


## 2.3.1 - 2019-08-18

- added: new command line switch `--subdir` / `-s` (courtesy of Christian Schulzendorff @chs8691):
  Exported activity files now can be saved in subdirectories, optionally grouped by year (and/or month) of the activity start time. Usually this is used together with the parameter `directory`, which is the root directory for DIR. `--subdir` supports the two placeholders `{YYYY}` and `{MM}` which can be used within DIR. Examples:
  ```
  --directory downloads --subdir {YYYY} --> downloads/2019/
  --directory downloads --subdir {YYYY}/{MM} --> downloads/2019/03/
  --directory downloads --subdir myTcxFiles/{YYYY} -f tcx --> downloads/myTcxFiles/2019/
  --directory downloads --subdir activities{YYYY}/GPX -f gpx --> downloads/activities2019/GPX/
  ```
  Note that only the activity files go into the subdirectory, the CSV and other files remain in the main directory
- added: new command line switch `--start_activity_no` / `-sa` (courtesy of Josef K @jkall):
  This is a minor fix to allow user to restart downloading where it crashed. Example:

  First download:
  ```
  $ python gcexport.py --count all ~/Downloads/garmin
  Garmin Connect activity (657/2098) [activity_id] ...
  ...some error...
  ```
  Second run:
  ```
  $ python gcexport.py --count all --start_activity_no 657 ~/Downloads/garmin
  ...
  Skipping Garmin Connect activity (656/2098) [activity_id]
  Garmin Connect activity (657/2098) [activity_id]
  ```


## 2.3.0 - 2019-04-18

- changed: the HTTP request to login to Garmin Connect (the old one didn't work anymore)


## 2.2.1 - 2019-03-30

- added: new command line switch `--fileprefix` / `-fp` (courtesy of Christian Schulzendorff @chs8691):
  A downloaded activity file can now have a date/time prefix, e.g. "20190301-065831-activity_3424910202.tcx". This works for all export types (tcx, gpx, json and original).
  Existing downloaded files will not be touched. If downloaded twice, once with and once without the parameter, two files will be created.


## 2.2.0 - 2018-11-09

- added: new exported fields
    - `vo2max` the VO2 Max (maximum volume of oxygen, cardiovascular fitness indicator)
    - `aerobicEffect` aerobic training effect (value between 0 and 5)
    - `anaerobicEffect` anaerobic training effect (value between 0 and 5)
    - `averageRunCadence` average number of steps per minute. Excludes time spent standing
    - `maxRunCadence` maximum number of steps per minute
    - `strideLength` average length of the stride from one footfall to the next (in meters)
    - `steps` number of steps
    - `privacy` who can see your activity
    - `fileFormat` the format of the original upload (fit, gpx or tcx)
    - `locationName` location determined by Garmin
    - `gear` the gear used (only tested for shoes); nickname if set, the brand/model otherwise
    - `elevationCorrected` flag telling if the elevation correction is applied
- changed: new default CSV template with different CSV output;
  to get the old CSV format use `-t csv_header_moderation.properties`
- added: Python version to the log file
- changed: improved exception logging


## 2.1.5 - 2018-09-24

- added: command line switches `-v` (verbosity) and `--desc` (description)


## 2.1.4 - 2018-09-21

- added: command line switches `-e` and `-a` to pass the CSV output to an external programm
  (merged from @moderation's commit from 2018-09-09)


## 2.1.3 - 2018-09-17

- added: CHANGELOG.md file
- changed: improved detection if device information is unknown or missing
  (i.e. they once were known, but the information got lost somehow)
- changed: the default CSV template (csv_header_default.properties) makes no difference
  anymore between corrected and uncorrected elevation
- changed: the URL_GC_ACTIVITY_DETAIL endpoint isn't called anymore when the chosen
  CSV template doesn't contain the `sampleCount` column


## 2.1.2 - 2018-09-11

- added: switch `-ot` to set file time to activity time (original
  [Pull Request](https://github.com/kjkjava/garmin-connect-export/pull/8) by @tobiaslj)


## 2.1.1 - 2018-09-10

- added: Python module `logging` to write log files
- changed: console output is less verbose
- changed: remove most Pylint warning


## 2.1.0 - 2018-09-08

- added: CSV templates (csv_header_default.properties and csv_header_running.properties)
  to make the CSV output configurable


## 2.0.3 - 2018-08-30

- changed: Fix regex for displayName to allow dots (original
  [Pull Request](https://github.com/moderation/garmin-connect-export/pull/19) by @chmoelders)


## 2.0.2 - 2018-08-24

- changed: use the User Stats to discover the number of activities
  (the old `activity-search-service-1.2` endpoint doesn't work anymore)


## 2.0.1 - 2018-06-15

- added: first unit tests
- changed: refactor into a Python module having a `main` function and using
  the `if __name__ == "__main__":` incantation
- changed: fixed some Pylint issues
- changed: note about using the user name or email address for logging in
- changed: fixed user name prompt (reported by
  [@TheKiteRunning](https://github.com/pe-st/garmin-connect-export/issues/6))


## 2.0.0 - 2018-04-17 - pe-st | branch develop

- changed: aligned with the current state of the **moderation** fork, but still using Python 2 for now
- changed: fixed distance and elapsedDuration parsing
  ([Pull Request](https://github.com/pe-st/garmin-connect-export/pull/3) by @lindback)


## 2018-04-06 - pe-st | branch develop

- changed: login ticket is now extracted from HTML response (the cookie doesn't contain the ticket anymore)


## 2018-03-10..2018-04-10 - pe-st | branch develop

- changed: various tunings to the CSV output


## 2018-03-10 - pe-st | branch develop

- added: using `activitylist-service` to get the list of activities
- changed: using **moderation**'s master as base using newer Garmin endpoints
  (`activity-search-service-1.2`)


## 2017-06-14 - pe-st | branch develop

- added: JSON export format
  ([Pull Request](https://github.com/kjkjava/garmin-connect-export/pull/6) by @yohcop)
- changed: use newer endpoints for GPX/TCX downloads (`modern/.../download-service`)
  ([Pull Request](https://github.com/kjkjava/garmin-connect-export/pull/30) by @julienr)
- changed: don't abort for HTTP status 204 (empty GPX file)


## 2015-12-23 - kjkjava | branch master

- last commit in original repo of **kjkjava**
- using `activity-search-service-1.0` for the list and `activity-service-1.1` for GPX/TCX exports
