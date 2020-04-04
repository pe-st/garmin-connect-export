# Welcome!

If you are here, it means you are interested in helping this small project out.
A hearty welcome and thank you! There are many ways you can contribute:

- Offer PR's to fix bugs or implement new features.
- Give feedback and bug reports regarding the software or the documentation.
- Setting up an automated toolchain with mock endpoints for the HTTP calls for easier testing
- Improve our examples, tutorials, and documentation.

## Python 2 vs 3

At the time of this writing (2020-04) Python 2 has passed its [sunset](https://python3statement.org/).
But as the target audience of this script are not necessarily Python aficionados, it should be as easy
to use as possible: clone the repo or download/extract the zip and then start using it.

This implies that the script should work also with Python 2.7 for some time to come,
e.g. the current macOS Catalina ships with Python 2.7.16 and the current Raspberry Pi OS (Raspian Buster)
comes with Python 2.7.16 as well.

## Getting started

### Pull requests

If you are new to GitHub [here](https://help.github.com/categories/collaborating-with-issues-and-pull-requests/)
is a detailed help source on getting involved with development on GitHub.

### Testing

There is a small set of unit test, using [pytest](https://docs.pytest.org/en/latest/)

I found that the free [PyCharm Community](https://www.jetbrains.com/pycharm/download/) is well suited for running the
tests, and it's very easy to switch between Python 2.7 and Python 3.x to make sure the tests run with both versions.

Unfortunately there are no mocks yet for simulating Garmin Connect during development, so for real tests you'll have to
run the script against your own Garmin account.

## REST endpoints

As this script doesn't use the paid API, the endpoints to use are known by reverse engineering browser sessions. And as
the Garmin Connect website changes over time, chances are that this script gets broken.

Small history of the endpoints used by `gcexport.py` to get a list of activities:

- [activity-search-service-1.0](https://connect.garmin.com/proxy/activity-search-service-1.0/json/activities):
  initial endpoint used since 2015, worked at least until January 2018
- [activity-search-service-1.2](https://connect.garmin.com/proxy/activity-search-service-1.2/json/activities):
  endpoint introduced in `gcexport.py` in August 2016. In March 2018 this still works, but doesn't allow you to fetch
  more than 20 activities, even split over multiple calls (when doing three consecutive calls with 1,19,19 as `limit`
  parameter, the third one fails with HTTP error 500).
  In August 2018 it stopped working altogether. The JSON returned by this endpoint however was quite rich
  (see example `activity-search-service-1.2.json` in the `json` folder).
- [Profile page](https://connect.garmin.com/modern/profile) and
  [User Stats page](https://connect.garmin.com/modern/proxy/userstats-service/statistics/user_name)
  were introduced in August 2018 when activity-search-service-1.2 stopped working. Their purpose in this script is
  solely to get the number of activities which I didn't find elsewhere.
- [activitylist-service](https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities):
  endpoint introduced in `gcexport.py` in March 2018. The JSON returned by this endpoint is very different from the
  activity-search-service-1.2 one (also here see the example in the `json` folder), e.g.
    - it is concise and offers no redundant information (e.g. only speed, not speed and pace)
    - the units are not explicitly given and must be deducted (e.g. the speed unit is m/s)
    - there is less information, e.g. there is only one set of elevation values (not both corrected and uncorrected), and other values like minimum heart rate are missing.
    - some other information is available only as an ID (e.g. `timeZoneId` or `deviceId`), and more complete information
      is available by further REST calls (one for each activity and additional ones for device information)

Endpoints to get information about a specific activity:

- [activity-service](https://connect.garmin.com/modern/proxy/activity-service/activity/nnnn): A kind of summary of the activity, most values are present in their canonical format.
- [activity-service-1.3 details](https://connect.garmin.com/modern/proxy/activity-service-1.3/json/activityDetails/nnnn): A detailed list of measurements, with a list of the metrics available for each measurement.

### Limitations of Data Provided by Current Endpoints and Choices Made

- The timezones provided are just the names (e.g. for Central European Time CET you can get either "Europe/Paris" or "(GMT+01:00) Central European Time"), but not the exact offset. Note that the "GMT+01:00" part of the name is hardcoded, so in summer (daylight savings time) Garmin Connect still uses +01:00 in the name even if the offset then is +02:00. To get the offset you need to calculate the difference between the startTimeLocal and the startTimeGMT.

