import pytest
from rclpy.parameter import Parameter

from embodied_comm.sensor_simulator import SensorSimulator
from embodied_comm.status_monitor import StatusMonitor


@pytest.mark.parametrize('node_type,name', [
    (SensorSimulator, 'publish_rate'), (StatusMonitor, 'timeout_sec'),
])
@pytest.mark.parametrize('value', [0.0, -1.0, float('nan'), float('inf'), -float('inf')])
def test_invalid_parameters(ros_context, node_type, name, value):
    with pytest.raises(ValueError, match='必须是有限正数'):
        node_type(context=ros_context, parameter_overrides=[Parameter(name, value=value)])


@pytest.mark.parametrize('node_type,name,value', [
    (SensorSimulator, 'publish_rate', 5.0), (StatusMonitor, 'timeout_sec', 0.4),
])
def test_startup_parameter_is_read_only(ros_context, node_type, name, value):
    node = node_type(context=ros_context, parameter_overrides=[Parameter(name, value=value)])
    try:
        assert node.get_parameter(name).value == value
        assert not node.set_parameters([Parameter(name, value=2.0)])[0].successful
    finally:
        node.destroy_node()
