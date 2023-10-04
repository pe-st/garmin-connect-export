# -*- coding: utf-8 -*-
"""
Tests for gcexport.py; Call them with this command line:

py.test gcexport_test.py
"""

from gcexport import *
from io import StringIO


def test_pace_or_speed_raw_cycling():
    # 10 m/s is 36 km/h
    assert pace_or_speed_raw(2, 4, 10.0) == 36.0


def test_pace_or_speed_raw_running():
    # 3.33 m/s is 12 km/h is 5 min/km
    assert pace_or_speed_raw(1, 4, 10.0 / 3) == 5.0


def test_pace_or_speed_formatted_cycling():
    # 10 m/s is 36 km/h
    assert pace_or_speed_formatted(2, 4, 10.0) == '36.0'


def test_pace_or_speed_formatted_running():
    # 3.33 m/s is 12 km/h is 5 min/km
    assert pace_or_speed_formatted(1, 4, 10.0 / 3) == '05:00'


def test_trunc6_more():
    assert trunc6(0.123456789) == '0.123456'


def test_trunc6_less():
    assert trunc6(0.123) == '0.123000'


def test_offset_date_time():
    assert offset_date_time("2018-03-08 12:23:22", "2018-03-08 11:23:22") == datetime(
        2018, 3, 8, 12, 23, 22, 0, FixedOffset(60, "LCL")
    )
    assert offset_date_time("2018-03-08 12:23:22", "2018-03-08 12:23:22") == datetime(
        2018, 3, 8, 12, 23, 22, 0, FixedOffset(0, "LCL")
    )


def test_datetime_from_iso():
    assert datetime_from_iso("2018-03-08 12:23:22") == datetime(2018, 3, 8, 12, 23, 22, 0)
    assert datetime_from_iso("2018-03-08 12:23:22.0") == datetime(2018, 3, 8, 12, 23, 22, 0)
    assert datetime_from_iso("2018-03-08T12:23:22") == datetime(2018, 3, 8, 12, 23, 22, 0)
    assert datetime_from_iso("2018-03-08T12:23:22.0") == datetime(2018, 3, 8, 12, 23, 22, 0)


def test_epoch_seconds_from_summary():
    # activity with a beginTimestamp
    with open('json/activity_2541953812_overview.json') as json_timestamp:
        summary = json.load(json_timestamp)
    assert summary['beginTimestamp'] == 1520508202000
    assert epoch_seconds_from_summary(summary) == 1520508202

    # activity with a startTimeLocal without fractions
    with open('json/activity_multisport_overview.json') as json_timestamp:
        summary = json.load(json_timestamp)
    assert summary['beginTimestamp'] == None
    assert summary['startTimeLocal'] == '2021-04-11 11:50:49'
    assert epoch_seconds_from_summary(summary) == 1618134649

    # activity with a startTimeLocal with fractions
    summary['startTimeLocal'] = '2021-04-11 11:50:50.3'
    assert epoch_seconds_from_summary(summary) == 1618134650


def test_hhmmss_from_seconds():
    # check/document that no rounding happens in hhmmss_from_seconds and the caller must round itself:
    # 2969.6 s are 49 minutes and 29.6 seconds
    assert hhmmss_from_seconds(2969.6) == "00:49:29"
    assert hhmmss_from_seconds(round(2969.6)) == "00:49:30"


def test_sanitize_filename():
    assert 'all_ascii' == sanitize_filename(u'all_ascii')
    assert 'deja_funf' == sanitize_filename(u'déjà fünf')
    assert 'deja_' == sanitize_filename(u'déjà fünf', 5)
    assert '' == sanitize_filename(u'')
    assert '' == sanitize_filename(None)

    with open('json/activity_emoji.json') as json_data:
        details = json.load(json_data)
    assert 'Biel__Pavillon' == sanitize_filename(details['activityName'])


def test_load_properties_keys():
    with open('csv_header_default.properties', 'r') as prop:
        csv_header_props = prop.read()
    csv_columns = []
    csv_headers = load_properties(csv_header_props, keys=csv_columns)

    assert csv_columns[0] == 'startTimeIso'
    assert csv_headers['startTimeIso'] == "Start Time"


def test_csv_write_record():
    with open('json/activitylist-service.json') as json_data_1:
        activities = json.load(json_data_1)
    with open('json/activity_emoji.json') as json_data_2:
        details = json.load(json_data_2)
    with open('json/activity_types.properties', 'r') as prop_1:
        activity_type_props = prop_1.read()
    activity_type_name = load_properties(activity_type_props)
    with open('json/event_types.properties', 'r') as prop_2:
        event_type_props = prop_2.read()
    event_type_name = load_properties(event_type_props)

    extract = {}
    extract['start_time_with_offset'] = offset_date_time("2018-03-08 12:23:22", "2018-03-08 11:23:22")
    extract['end_time_with_offset'] = offset_date_time("2018-03-08 12:23:22", "2018-03-08 12:23:22")
    extract['elapsed_duration'] = 42.43
    extract['elapsed_seconds'] = 42
    extract['samples'] = None
    extract['device'] = "some device"
    extract['gear'] = "some gear"
    extract['hrZones'] = HR_ZONES_EMPTY
    extract['hrZones'][1] = json.loads('{ "secsInZone": 1689.269, "zoneLowBoundary": 138 }')

    csv_file = StringIO()
    csv_filter = CsvFilter(csv_file, 'csv_header_all.properties')
    csv_write_record(csv_filter, extract, activities[0], details, activity_type_name, event_type_name)
    expected = '"Biel 🏛 Pavillon"'
    assert csv_file.getvalue()[69 : 69 + len(expected)] == expected


def write_to_file_mock(filename, content, mode, file_time=None):
    pass


def http_req_mock_device(url, post=None, headers=None):
    with open('json/device_856399.json') as json_device:
        return json_device.read()


def test_extract_device():
    args = parse_arguments([])

    with open('json/activity_2541953812.json') as json_detail:
        details = json.load(json_detail)
    assert u'fēnix 5 10.0.0.0' == extract_device({}, details, None, args, http_req_mock_device, write_to_file_mock)

    with open('json/activity_154105348_gpx_device_null.json') as json_detail:
        details = json.load(json_detail)
    assert None == extract_device({}, details, None, args, http_req_mock_device, write_to_file_mock)

    with open('json/activity_995784118_gpx_device_0.json') as json_detail:
        details = json.load(json_detail)
    assert None == extract_device({}, details, None, args, http_req_mock_device, write_to_file_mock)


def http_req_mock_zones(url, post=None, headers=None):
    with open('json/activity_2541953812_zones.json') as json_zones:
        return json_zones.read()


def test_load_zones():
    args = parse_arguments([])

    zones = load_zones('2541953812', None, args, http_req_mock_zones, write_to_file_mock)
    assert 5 == len(zones)
    assert 100 == zones[0]['zoneLowBoundary']
    assert 138 == zones[1]['zoneLowBoundary']
    assert 148 == zones[2]['zoneLowBoundary']
    assert 168 == zones[3]['zoneLowBoundary']
    assert 182 == zones[4]['zoneLowBoundary']
    assert 2462.848 == zones[0]['secsInZone']


def test_resolve_path():
    assert resolve_path('root', 'sub/{YYYY}', '2018-03-08 12:23:22') == 'root/sub/2018'
    assert resolve_path('root', 'sub/{MM}', '2018-03-08 12:23:22') == 'root/sub/03'
    assert resolve_path('root', 'sub/{YYYY}/{MM}', '2018-03-08 12:23:22') == 'root/sub/2018/03'
    assert resolve_path('root', 'sub/{yyyy}', '2018-03-08 12:23:22') == 'root/sub/{yyyy}'
    assert resolve_path('root', 'sub/{YYYYMM}', '2018-03-08 12:23:22') == 'root/sub/{YYYYMM}'
    assert resolve_path('root', 'sub/all', '2018-03-08 12:23:22') == 'root/sub/all'


mock_details_multi_counter = 0


def http_req_mock_details_multi(url, post=None, headers=None):
    global mock_details_multi_counter
    mock_details_multi_counter += 1

    if mock_details_multi_counter == 1:
        with open('json/activity_multisport_detail.json') as json_stream:
            return json_stream.read()
    elif mock_details_multi_counter >= 2 & mock_details_multi_counter <= 6:
        with open('json/activity_multisport_child.json') as json_stream:
            json_string = json_stream.read()
            activity_id = url.split('/')[-1]
            return json_string.replace('6588349076', activity_id)
    else:
        raise Exception('mock_details_multi_counter has invalid value ' + str(mock_details_multi_counter))


def test_fetch_multisports():
    args = parse_arguments([])

    with open('json/activities-list.json') as json_detail:
        activity_summaries = json.load(json_detail)

    # assert state before fetch_multisports
    assert activity_summaries[0]['activityId'] == 6609987243
    assert activity_summaries[1]['activityId'] == 6588349056
    assert activity_summaries[2]['activityId'] == 6585943400

    global mock_details_multi_counter
    mock_details_multi_counter = 0
    fetch_multisports(activity_summaries, http_req_mock_details_multi, args)

    # the entries 0/1/2 from before are now 0/1/7
    assert activity_summaries[0]['activityId'] == 6609987243
    assert activity_summaries[1]['activityId'] == 6588349056
    assert activity_summaries[7]['activityId'] == 6585943400

    # at indexes 2..6 are now the five child activities
    assert activity_summaries[2]['activityId'] == 6588349067
    assert activity_summaries[3]['activityId'] == 6588349072
    assert activity_summaries[4]['activityId'] == 6588349076
    assert activity_summaries[5]['activityId'] == 6588349079
    assert activity_summaries[6]['activityId'] == 6588349081
