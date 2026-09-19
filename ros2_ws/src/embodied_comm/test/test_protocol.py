import pytest
from embodied_comm.common import period_seconds, sensor_text, parse_sensor


@pytest.mark.parametrize('rate,period', [(2.0, .5), (5.0, .2), (.1, 10.0), (100.0, .01)])
def test_period(rate, period):
    assert period_seconds(rate) == pytest.approx(period)


@pytest.mark.parametrize('rate', [0.0, -1.0, .09, 100.1, float('inf'), -float('inf'), float('nan')])
def test_invalid_rate(rate):
    with pytest.raises(ValueError):
        period_seconds(rate)


@pytest.mark.parametrize('seq,value', [(1, 0.0), (2, 1.0), (101, 100.0), (102, 0.0)])
def test_message(seq, value):
    assert parse_sensor(sensor_text(seq)) == {'seq': seq, 'value': value}


def test_invalid_sequence():
    with pytest.raises(ValueError):
        sensor_text(0)
