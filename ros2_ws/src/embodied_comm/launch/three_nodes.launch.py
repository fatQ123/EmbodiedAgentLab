"""启动三个业务节点；重映射只作用于执行器的传感器输入。"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('publish_rate', default_value='2.0',
                              description='传感器发布频率，单位 Hz，必须为有限正数'),
        DeclareLaunchArgument('timeout_sec', default_value='3.0',
                              description='监控器传感器超时阈值，单位秒，必须为有限正数'),
        DeclareLaunchArgument('executor_sensor_topic', default_value='/sensor_state',
                              description='仅执行器订阅的传感器话题，用于连接配置与故障实验'),
        Node(
            package='embodied_comm', executable='sensor_simulator', output='screen',
            parameters=[{'publish_rate': ParameterValue(
                LaunchConfiguration('publish_rate'), value_type=float)}],
        ),
        Node(
            package='embodied_comm', executable='task_executor', output='screen',
            remappings=[('/sensor_state', LaunchConfiguration('executor_sensor_topic'))],
        ),
        Node(
            package='embodied_comm', executable='status_monitor', output='screen',
            parameters=[{'timeout_sec': ParameterValue(
                LaunchConfiguration('timeout_sec'), value_type=float)}],
        ),
    ])
