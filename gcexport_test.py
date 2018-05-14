from gcexport import *

def test_pace_or_speed_raw_cycling():
    # 10 m/s is 36 km/h
    assert pace_or_speed_raw(2, 4, 10.0) == 36.0

def test_pace_or_speed_raw_running():
    # 3.33 m/s is 12 km/h is 5 min/km
    assert pace_or_speed_raw(1, 4, 10.0/3) == 5.0

def test_trunc6_more():
    assert trunc6(0.123456789) == '0.123456'

def test_trunc6_less():
    assert trunc6(0.123) == '0.123000'

def test_offset_date_time():
    assert offset_date_time("2018-03-08 12:23:22", "2018-03-08 11:23:22") == datetime(2018, 3, 8, 12, 23, 22, 0, FixedOffset(60, "LCL"))
    assert offset_date_time("2018-03-08 12:23:22", "2018-03-08 12:23:22") == datetime(2018, 3, 8, 12, 23, 22, 0, FixedOffset(0, "LCL"))
