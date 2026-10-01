"""启动通信系统、正常质检工位坐标树以及可选的 RViz."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = FindPackageShare('embodied_comm')
    publish_rate = LaunchConfiguration('publish_rate')
    timeout_sec = LaunchConfiguration('timeout_sec')
    diagnostic_rate = LaunchConfiguration('diagnostic_rate')
    fault_stop_after_sec = LaunchConfiguration('fault_stop_after_sec')
    fault_sensor_crash_after_sec = LaunchConfiguration(
        'fault_sensor_crash_after_sec'
    )
    fault_service_delay_sec = LaunchConfiguration('fault_service_delay_sec')
    publisher_reliability = LaunchConfiguration('publisher_reliability')
    executor_sensor_topic = LaunchConfiguration('executor_sensor_topic')
    frame_publish_rate = LaunchConfiguration('frame_publish_rate')
    tf_fault_mode = LaunchConfiguration('tf_fault_mode')
    tf_fault_after_sec = LaunchConfiguration('tf_fault_after_sec')
    rviz_config = LaunchConfiguration('rviz_config')
    return LaunchDescription([
        DeclareLaunchArgument('publish_rate', default_value='2.0'),
        DeclareLaunchArgument('timeout_sec', default_value='3.0'),
        DeclareLaunchArgument('diagnostic_rate', default_value='1.0'),
        DeclareLaunchArgument('fault_stop_after_sec', default_value='0.0'),
        DeclareLaunchArgument(
            'fault_sensor_crash_after_sec', default_value='0.0',
        ),
        DeclareLaunchArgument('fault_service_delay_sec', default_value='0.0'),
        DeclareLaunchArgument('publisher_reliability', default_value='reliable'),
        DeclareLaunchArgument('executor_sensor_topic', default_value='/sensor_state'),
        DeclareLaunchArgument(
            'frame_publish_rate', default_value='10.0',
            description='动态坐标和 Marker 的发布频率，单位 Hz',
        ),
        DeclareLaunchArgument(
            'tf_fault_mode', default_value='normal',
            description='TF 模式：normal、missing 或 stale',
        ),
        DeclareLaunchArgument(
            'tf_fault_after_sec', default_value='5.0',
            description='stale 模式下停止刷新动态 TF 的等待时间',
        ),
        DeclareLaunchArgument(
            'use_rviz', default_value='true',
            description='是否启动 RViz；自动化测试和无图形环境使用 false',
        ),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=PathJoinSubstitution([
                package_share, 'config', 'week03_workcell.rviz',
            ]),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                package_share, 'launch', 'three_nodes.launch.py',
            ])),
            launch_arguments={
                'publish_rate': publish_rate,
                'timeout_sec': timeout_sec,
                'diagnostic_rate': diagnostic_rate,
                'fault_stop_after_sec': fault_stop_after_sec,
                'fault_sensor_crash_after_sec': fault_sensor_crash_after_sec,
                'fault_service_delay_sec': fault_service_delay_sec,
                'publisher_reliability': publisher_reliability,
                'executor_sensor_topic': executor_sensor_topic,
            }.items(),
        ),
        Node(
            package='embodied_comm', executable='workcell_visualizer', output='screen',
            parameters=[{
                'publish_rate': ParameterValue(
                    frame_publish_rate, value_type=float,
                ),
                'tf_fault_mode': tf_fault_mode,
                'tf_fault_after_sec': ParameterValue(
                    tf_fault_after_sec, value_type=float,
                ),
            }],
        ),
        Node(
            package='rviz2', executable='rviz2', name='rviz2', output='screen',
            arguments=['-d', rviz_config],
            condition=IfCondition(LaunchConfiguration('use_rviz')),
        ),
    ])
