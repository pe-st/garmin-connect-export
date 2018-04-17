from gcexport import *

def test_paceOrSpeedRaw_cycling():
    # 10 m/s is 36 km/h
    assert paceOrSpeedRaw(2, 4, 10.0) == 36.0

def test_paceOrSpeedRaw_running():
    # 3.33 m/s is 12 km/h is 5 min/km
    assert paceOrSpeedRaw(1, 4, 10.0/3) == 5.0
