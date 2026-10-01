"""启动健康诊断并可控复现传感器话题停止故障."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = FindPackageShare('embodied_comm')
    argument_defaults = {
        'publish_rate': '2.0',
        'timeout_sec': '3.0',
        'diagnostic_rate': '1.0',
        'fault_stop_after_sec': '0.0',
        'fault_sensor_crash_after_sec': '0.0',
        'fault_service_delay_sec': '0.0',
        'publisher_reliability': 'reliable',
        'executor_sensor_topic': '/sensor_state',
        'frame_publish_rate': '10.0',
        'tf_fault_mode': 'normal',
        'tf_fault_after_sec': '5.0',
        'use_rviz': 'true',
        'rviz_config': PathJoinSubstitution([
            package_share, 'config', 'week03_workcell.rviz',
        ]),
    }
    declarations = [
        DeclareLaunchArgument(name, default_value=value)
        for name, value in argument_defaults.items()
    ]
    day2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            package_share, 'launch', 'week03_day2.launch.py',
        ])),
        launch_arguments={
            name: LaunchConfiguration(name) for name in argument_defaults
        }.items(),
    )
    return LaunchDescription([*declarations, day2])
