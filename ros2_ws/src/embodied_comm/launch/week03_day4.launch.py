"""启动第 4 天 QoS、话题停止及 TF 缺失/过期故障实验."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
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
    argument_descriptions = {
        'publish_rate': '传感器数据发布频率，单位 Hz',
        'timeout_sec': '传感器数据新鲜度与诊断超时阈值，单位秒',
        'diagnostic_rate': '传感器与 TF 诊断发布频率，单位 Hz',
        'fault_stop_after_sec': '大于 0 时按秒停止传感器话题；0 为关闭',
        'fault_sensor_crash_after_sec': '大于 0 时按秒使传感器节点异常退出',
        'fault_service_delay_sec': '快速服务响应延迟秒数；0 为关闭',
        'publisher_reliability': '传感器 Publisher：reliable 或 best_effort',
        'executor_sensor_topic': '仅供执行器使用的传感器输入话题',
        'frame_publish_rate': '动态 TF 和 Marker 发布频率，单位 Hz',
        'tf_fault_mode': 'TF 故障模式：normal、missing 或 stale',
        'tf_fault_after_sec': 'stale 模式下停止刷新动态 TF 的等待秒数',
        'use_rviz': '是否启动 RViz；无图形测试使用 false',
        'rviz_config': 'RViz 配置文件路径',
    }
    declarations = [
        DeclareLaunchArgument(
            name,
            default_value=value,
            description=argument_descriptions[name],
        )
        for name, value in argument_defaults.items()
    ]
    declarations.append(DeclareLaunchArgument(
        'tf_timeout_sec', default_value='1.0',
        description='完整 TF 坐标链的新鲜度阈值，单位秒',
    ))
    day3 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            package_share, 'launch', 'week03_day3.launch.py',
        ])),
        launch_arguments={
            name: LaunchConfiguration(name) for name in argument_defaults
        }.items(),
    )
    spatial_monitor = Node(
        package='embodied_comm',
        executable='spatial_health_monitor',
        output='screen',
        parameters=[{
            'tf_timeout_sec': ParameterValue(
                LaunchConfiguration('tf_timeout_sec'), value_type=float,
            ),
            'diagnostic_rate': ParameterValue(
                LaunchConfiguration('diagnostic_rate'), value_type=float,
            ),
        }],
    )
    return LaunchDescription([*declarations, day3, spatial_monitor])
