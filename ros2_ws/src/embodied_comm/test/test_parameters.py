from embodied_comm.sensor_simulator import SensorSimulator
from embodied_comm.spatial_health_monitor import SpatialHealthMonitor
from embodied_comm.status_monitor import StatusMonitor
from embodied_comm.task_executor import TaskExecutor
from embodied_comm.workcell_visualizer import WorkcellVisualizer
import pytest
from rclpy.parameter import Parameter


@pytest.mark.parametrize('node_type,name', [
    (SensorSimulator, 'publish_rate'), (StatusMonitor, 'timeout_sec'),
    (StatusMonitor, 'diagnostic_rate'), (TaskExecutor, 'sensor_timeout_sec'),
    (WorkcellVisualizer, 'publish_rate'),
    (WorkcellVisualizer, 'tf_fault_after_sec'),
    (SpatialHealthMonitor, 'tf_timeout_sec'),
    (SpatialHealthMonitor, 'diagnostic_rate'),
])
@pytest.mark.parametrize('value', [0.0, -1.0, float('nan'), float('inf'), -float('inf')])
def test_invalid_parameters(ros_context, node_type, name, value):
    with pytest.raises(ValueError, match='必须是有限正数'):
        node_type(context=ros_context, parameter_overrides=[Parameter(name, value=value)])


@pytest.mark.parametrize('node_type,name,value', [
    (SensorSimulator, 'publish_rate', 5.0), (StatusMonitor, 'timeout_sec', 0.4),
    (StatusMonitor, 'diagnostic_rate', 5.0),
    (TaskExecutor, 'sensor_timeout_sec', 0.4),
    (WorkcellVisualizer, 'publish_rate', 20.0),
    (WorkcellVisualizer, 'tf_fault_after_sec', 0.4),
    (SpatialHealthMonitor, 'tf_timeout_sec', 0.4),
    (SpatialHealthMonitor, 'diagnostic_rate', 5.0),
])
def test_startup_parameter_is_read_only(ros_context, node_type, name, value):
    node = node_type(context=ros_context, parameter_overrides=[Parameter(name, value=value)])
    try:
        assert node.get_parameter(name).value == value
        assert not node.set_parameters([Parameter(name, value=2.0)])[0].successful
    finally:
        node.destroy_node()


@pytest.mark.parametrize('node_type,name,value', [
    (SensorSimulator, 'publisher_reliability', 'invalid'),
    (WorkcellVisualizer, 'tf_fault_mode', 'invalid'),
])
def test_invalid_choice_parameters(ros_context, node_type, name, value):
    with pytest.raises(ValueError, match='必须是'):
        node_type(
            context=ros_context,
            parameter_overrides=[Parameter(name, value=value)],
        )


@pytest.mark.parametrize('node_type,name,value,replacement', [
    (SensorSimulator, 'publisher_reliability', 'best_effort', 'reliable'),
    (WorkcellVisualizer, 'tf_fault_mode', 'missing', 'normal'),
])
def test_choice_parameters_are_read_only(
        ros_context, node_type, name, value, replacement):
    node = node_type(
        context=ros_context,
        parameter_overrides=[Parameter(name, value=value)],
    )
    try:
        assert node.get_parameter(name).value == value
        result = node.set_parameters([
            Parameter(name, value=replacement),
        ])[0]
        assert not result.successful
    finally:
        node.destroy_node()


@pytest.mark.parametrize('value', [-1.0, float('nan'), float('inf'), -float('inf')])
@pytest.mark.parametrize('node_type,name', [
    (SensorSimulator, 'fault_stop_after_sec'),
    (SensorSimulator, 'fault_crash_after_sec'),
    (TaskExecutor, 'fault_service_delay_sec'),
])
def test_invalid_nonnegative_fault_parameter(
        ros_context, node_type, name, value):
    with pytest.raises(ValueError, match='必须是有限非负数'):
        node_type(
            context=ros_context,
            parameter_overrides=[Parameter(name, value=value)],
        )


@pytest.mark.parametrize('node_type,name,value', [
    (SensorSimulator, 'fault_stop_after_sec', 0.2),
    (SensorSimulator, 'fault_crash_after_sec', 1.0),
    (TaskExecutor, 'fault_service_delay_sec', 0.2),
])
def test_nonnegative_fault_parameter_is_read_only(
        ros_context, node_type, name, value):
    node = node_type(
        context=ros_context,
        parameter_overrides=[Parameter(name, value=value)],
    )
    try:
        assert node.get_parameter(name).value == value
        result = node.set_parameters([
            Parameter(name, value=0.0),
        ])[0]
        assert not result.successful
    finally:
        node.destroy_node()
