from gcexport import *

def test_paceOrSpeedRaw_cycling():
    # 10 m/s is 36 km/h
    assert paceOrSpeedRaw(2, 4, 10.0) == 36.0

def test_paceOrSpeedRaw_running():
    # 3.33 m/s is 12 km/h is 5 min/km
    assert paceOrSpeedRaw(1, 4, 10.0/3) == 5.0

def test_trunc6_more():
    assert trunc6(0.123456789) == '0.123456'

def test_trunc6_less():
    assert trunc6(0.123) == '0.123000'
