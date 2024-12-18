# garmin-connect-export script

:exclamation: | This script [now requires Python 3.8 or newer](https://github.com/pe-st/garmin-connect-export/issues/64)
---|---

:exclamation: | There is a [report of a deactivated user account that might by caused by using this script](https://github.com/pe-st/garmin-connect-export/issues/60). The exact reasons are not known, and my account has never been deactivated. But be aware that I can give no guarantee that Garmin tolerates requests made from this script. I believe though that this script is fair use (it doesn't do anything other than automating stuff that you do in the browser). But be careful if you plan to run the script as periodical task (with `cron` etc)
---|---

Download a copy of your Garmin Connect data, including stats and GPX tracks.

Note that Garmin introduced a while ago (around May 2018, for GDPR compatibility) a possibility to [download all of your Garmin Connect data](https://www.garmin.com/en-US/account/datamanagement/exportdata/) in one zip file. Depending on your needs this might be enough, but the script here offers additional features like getting GPX tracks instead of the original upload format or limiting the export to just a couple of activities.

## Forks and Branches

Before going into the details of this script itself, some meta information.

There exist many [forks](https://help.github.com/articles/fork-a-repo/) of this script repository:

- [pe-st](https://github.com/pe-st/garmin-connect-export)
  This is my (**pe-st**) repository, the one you're looking at (or the source of the copy you're looking at).
  It was [detached from **kjkjava**'s repo](https://github.com/pe-st/garmin-connect-export/issues/53)
  (see below) in February 2021, after more than 5 years of inactivity of the upstream repo.
- [kjkjava](https://github.com/kjkjava/garmin-connect-export)
  The original repo (mother repo) of my (**pe-st**) repo. It seems not maintained anymore (last commit in 2015, see also: [pr#42](https://github.com/kjkjava/garmin-connect-export/pull/42) and [issues#46](https://github.com/kjkjava/garmin-connect-export/issues/46))
- [moderation](https://github.com/moderation/garmin-connect-export)
  After some inactivity of the **@kjkjava** repo, **@moderation** made some corrections in his own fork to have a working script again. His fork is primarily designed for his use which is cycling, while mine (**pe-st**) is running.
  In March 2018 I integrated **@moderation**'s work into my own repo, so logically **@moderation** is now the
  father repo of my repo. In April 2018 **@moderation** migrated his script to Python 3. Unfortunately
  **@moderation**'s script [didn't work for me for a couple of months](https://github.com/moderation/garmin-connect-export/issues/11),
  probably because of different Garmin Connect REST endpoints (URLs).

For the [branches](https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging) in **pe-st**'s repo see [BRANCH.md](BRANCH.md)

## Description

This script will backup your personal Garmin Connect data. All downloaded data will go into a directory called `YYYY-MM-DD_garmin_connect_export/` in the current working directory. Activity records and details will go into a CSV file called `activities.csv`. GPX files (or whatever format you specify) containing track data, activity title, and activity descriptions are saved as well, using the Activity ID.

If there is no GPS track data (e.g., due to an indoor treadmill workout), a data file is still saved. If the GPX format is used, activity title and description data are saved. If the original format is used, Garmin may not provide a file at all and an empty file will be created. For activities where a GPX file was uploaded, Garmin may not have a TCX file available for download, so an empty file will be created. Since GPX is the only format Garmin should have for every activity, it is the default and preferred download format.

If you have many activities, you may find that this script crashes with an "Operation timed out" message. Just run the script again and it will pick up where it left off.

## Installation

- If you're comfortable using Git, just clone the repo from github
- Otherwise get the latest `zip` (or `tar.gz`) from the [releases page](https://github.com/pe-st/garmin-connect-export/releases)
  and unpack it where it suits you.
- Install the dependencies: `python3 -m pip install -r requirements.txt`

## Usage

You will need a little experience running things from the command line to use this script. That said, here are the usage details from the `--help` flag:

```
usage: gcexport.py [-h] [--version] [-v] [--username USERNAME] [--password PASSWORD]
                   [-c COUNT] [-sd START_DATE] [-ed END_DATE] [-e EXTERNAL] [-a ARGS]
                   [-f {gpx,tcx,original,json}] [-d DIRECTORY] [-s SUBDIR] [-lp LOGPATH]
                   [-u] [-ot] [--desc [DESC]] [-t TEMPLATE] [-fp] [-sa START_ACTIVITY_NO]
                   [-ex FILE] [-tf TYPE_FILTER] [-ss DIRECTORY]

Garmin Connect Exporter

optional arguments:
  -h, --help            show this help message and exit
  --version             print version and exit
  -v, --verbosity       increase output and log verbosity, save more intermediate files
  --username USERNAME   your Garmin Connect username or email address (otherwise, you will be prompted)
  --password PASSWORD   your Garmin Connect password (otherwise, you will be prompted)
  -c COUNT, --count COUNT
                        number of recent activities to download, or 'all' (default: 1)
  -sd START_DATE, --start_date START_DATE
                        the start date to get activities from (inclusive). Format example: 2023-07-31
  -ed END_DATE, --end_date END_DATE
                        the end date to get activities to (inclusive). Format example: 2023-07-31
  -e EXTERNAL, --external EXTERNAL
                        path to external program to pass CSV file too
  -a ARGS, --args ARGS  additional arguments to pass to external program
  -f {gpx,tcx,original,json}, --format {gpx,tcx,original,json}
                        export format; can be 'gpx', 'tcx', 'original' or 'json' (default: 'gpx')
  -d DIRECTORY, --directory DIRECTORY
                        the directory to export to (default: './YYYY-MM-DD_garmin_connect_export')
  -s SUBDIR, --subdir SUBDIR
                        the subdirectory for activity files (tcx, gpx etc.), supported placeholders are {YYYY} and {MM}
                        (default: export directory)
  -lp LOGPATH, --logpath LOGPATH
                        the directory to store logfiles (default: same as for --directory)
  -u, --unzip           if downloading ZIP files (format: 'original'), unzip the file and remove the ZIP file
  -ot, --originaltime   will set downloaded (and possibly unzipped) file time to the activity start time
  --desc [DESC]         append the activity's description to the file name of the download; limit size if number is given
  -t TEMPLATE, --template TEMPLATE
                        template file with desired columns for CSV output
  -fp, --fileprefix     set the local time as activity file name prefix
  -sa START_ACTIVITY_NO, --start_activity_no START_ACTIVITY_NO
                        give index for first activity to import, i.e. skipping the newest activities
  -ex FILE, --exclude FILE
                        JSON file with array of activity IDs to exclude from download.
                        Format example: {"ids": ["6176888711"]}
  -tf TYPE_FILTER, --type_filter TYPE_FILTER
                        comma-separated list of activity types to allow. Format example: 'walking,hiking'
  -ss DIRECTORY, --session DIRECTORY
                        enable loading and storing SSO information from/to given directory
```

### Authentication

You have to authenticate with username and password, and possibly an MFA code, at least for an initial login.

The script is then using OAuth tokens (thanks to the [garth](https://github.com/matin/garth) library).
You can persist the OAuth token by giving a session directory, removing the need to provide username/password/MFA
for every script run.

But keep the persistent tokens safe; if somebody gets hold of your tokens, they might be able to
read all your data in Garmin Connect (e.g. your health data), maybe even change or delete it.


### Examples

- `python gcexport.py -ss ~/.garth --count all`  
  will download all of your data to a dated directory and save your OAuth tokens in the directory `.garth` in your home directory (from the second run on you will not be asked for your username/password anymore)

- `python gcexport.py -c all -f gpx -ot --desc 20`  
  will export all of your data in GPX format, set the timestamp of the GPX files to the start time of the activity and append the 20 first characters of the activity's description to the file name.

- `python gcexport.py -c all -e /Applications/LibreOffice.app/Contents/MacOS/soffice -a calc`  
  will download all of your data and then use LibreOffice to open the CSV file with the list of your activities (the path to LibreOffice is platform-specific; the example is for macOS).

- `python gcexport.py -d ~/MyActivities -c 3 -f original -u --username bobbyjoe --password bestpasswordever1`  
  will download your three most recent activities in the FIT file format (or whatever they were uploaded as) into the `~/MyActivities` directory (unless they already exist). Using the `--password` flags is not recommended because your password will be stored in your command line history. Instead, omit it to be prompted (and note that nothing will be displayed when you type your password). Equally you might not want to have the username stored in your command line history; in this case avoid also to give the `--username` option, and you'll be prompted for it. Note also that depending on the age of your garmin account your username is the email address (I myself still can login both with username and email address, but I've had a report that for some users the email address is mandatory to login).

- `python gcexport.py -c all --start_date 2023-07-31 --end_date 2023-08-03` will download all activities from July 31st through August 3rd (the range is inclusive). These start and end date flags may be used together or individually. They may also be used in combination with `--count` and `start_activity_no`.

Alternatively, you may run it with `./gcexport.py` if you set the file as executable (i.e., `chmod u+x gcexport.py`).

### Notes on the Usage

- The `-c COUNT` option might appear to count wrongly when exporting multi-sport activities;
  they count as one activity, but the incrementing counter displayed on the console counts
  also the individual parts of a multi-sport activity


### Python

Of course, you must have Python installed to run this, any recent 3.x version should work
(see also [Python 3.x Versions](./CONTRIBUTING.md#python-3x-versions)).

Most Mac and Linux users should already have Python.
Note that if you run into the [TLSV1 ALERT problem](https://github.com/pe-st/garmin-connect-export/issues/16)
or the [HTTP 403 Authentication Error](https://github.com/pe-st/garmin-connect-export/issues/59),
your Python installation might not be recent enough.
In this case you can install a more recent Python on your Mac using [Homebrew](https://docs.brew.sh/Homebrew-and-Python)
and/or [pyenv](https://github.com/pyenv/pyenv).

Also, as stated above, you should have some basic command line experience.


## Data

This tool is not guaranteed to get all of your data, or even download it correctly. I have only tested it with my account and it works fine, but different account settings or different data types could potentially cause problems. Also, because this is not an official feature of Garmin Connect, Garmin may very well make changes that break this utility (and they certainly have since I created this project).

If you want to see all the raw data that Garmin hands to this script, just choose the JSON export format (`-f json`); in this case only metadata is exported, no track data.

The format of the CSV export file can be customized with template files (in Properties format, see the `--template` option); three examples are included:

- `csv_header_default.properties` (the default) gives you my preferred selection of columns, mainly targeted at running and hiking
- `csv_header_all.properties` gives you all available columns, handy as starting point for your own selection
- `csv_header_moderation.properties` gives you the same output as **@moderation**'s fork, mainly targeted at cycling
- `csv_header_kjkjava.properties` gives you an output similar as **@kjkjava**'s original script, mainly targeted at running

You can easily create a template file for your needs, just copy one of the examples and change the appearing columns, their order and/or their title.

Some important columns explained:

- `raw` (e.g. `durationRaw`) columns usually give you unformatted data as provided by the Garmin API, other columns (e.g. `duration`) often format the data more readable
- speed columns (e.g. `averageSpeedRaw` and `averageSpeedPace`): when there is `Pace` in the column name the value given is a speed (km/) or pace (minutes per kilometer) depending on the activity type (e.g. pace for running, hiking and walking activities, speed for other activities)
- The elevation is either uncorrected or corrected, with a flag telling which. The current API doesn't provide both sets of elevations

## Garmin Connect API

This script is for personal use only. It simulates a standard user session (i.e., in the browser), logging in using cookies and an authorization ticket. This makes the script pretty brittle. If you're looking for a more reliable option, particularly if you wish to use this for some production service, Garmin does offer a paid API service.

More information about the API endpoints used in the script is available in [CONTRIBUTING.md](CONTRIBUTING.md)

## History

The original project was written in PHP (formerly in the `old` directory, now deleted), based on "Garmin Connect export to Dailymile" code at <http://www.ciscomonkey.net/gc-to-dm-export/> (link has been down for a while). It no longer works due to the way Garmin handles logins. It could be updated, but I (**kjkjava**) decided to rewrite everything in Python for the latest version.

After 2015, when the original repo stopped being maintained, several forks from **kjkjava** started appearing (see
Forks and Branches section above).

In 2021 this fork was [detached from the original repo](https://github.com/pe-st/garmin-connect-export/issues/53);
in what concerns Github, the repo isn't a fork anymore, but a new "original".
For the history of this fork see the [CHANGELOG](CHANGELOG.md)


## Contributions

Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md)

Contributors as of 2024-07 (Hope I didn't forget anyone,
see also [Contributors](https://github.com/pe-st/garmin-connect-export/graphs/contributors)):

- Kyle Krafka @kjkjava
- Jochem Wichers Hoeth @jowiho
- Andreas Loeffler @lefty01
- @sclub
- Yohann Coppel @yohcop
- Tobias Ljunggren @tobiaslj
- @cdstrachan
- Michael Payne @moderation
- Chris McCarty @cmccarty
- Julien Rebetez @julienr
- Peter Steiner @pe-st
- @ulf-lindback
- @TheKiteRunning
- Jens Diemer @jedie
- Christian Moelders @chmoelders
- Christian Schulzendorff @chs8691
- Josef K @jkall
- Thomas Th @telemaxx
- Bart Skowron @bxsx
- Reto Conconi @retoborm
- Cristian @cristian5th
- @hannesweisbach
- @SimonBaars
- @geraudloup
- @app4g
- Simon Ågren @agrensimon
- @embear
- Joe Timmerman @joetimmerman
- Rob @rjl6789
- @gustav-b
- Ingvar Stepanyan @RReverser

## License

[MIT](https://github.com/pe-st/garmin-connect-export/blob/master/LICENSE) &copy; 2015 Kyle Krafka and contributors

## Thank You

Thanks for using this script and I hope you find it as useful as I do! :smile:
