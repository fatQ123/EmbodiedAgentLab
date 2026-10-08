"""第四周两关节描述与合成关节状态；图形工具由用户显式启用。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = FindPackageShare('embodied_arm_description')
    model = PathJoinSubstitution([
        package_share, 'urdf', 'two_link_arm.urdf.xacro',
    ])
    robot_description = ParameterValue(
        Command([FindExecutable(name='xacro'), ' ', model]), value_type=str,
    )
    gui = LaunchConfiguration('gui')
    joint_state_parameters = {
        'use_sim_time': False,
        'rate': 20,
        'zeros.joint1': 0.0,
        'zeros.joint2': 0.0,
    }

    return LaunchDescription([
        DeclareLaunchArgument(
            'gui', default_value='false', choices=['true', 'false'],
            description='启用关节滑块；false 使用无界面的合成零位发布器',
        ),
        DeclareLaunchArgument(
            'rviz', default_value='false', choices=['true', 'false'],
            description='由用户显式启用 RViz 进行模型与坐标系验收',
        ),
        Node(
            package='robot_state_publisher', executable='robot_state_publisher',
            name='robot_state_publisher', output='screen',
            parameters=[{
                'robot_description': robot_description,
                'use_sim_time': False,
            }],
        ),
        Node(
            package='joint_state_publisher', executable='joint_state_publisher',
            name='joint_state_publisher', output='screen',
            parameters=[joint_state_parameters], condition=UnlessCondition(gui),
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui', output='screen',
            parameters=[joint_state_parameters], condition=IfCondition(gui),
        ),
        Node(
            package='rviz2', executable='rviz2', name='rviz2', output='screen',
            arguments=['-d', PathJoinSubstitution([
                package_share, 'rviz', 'two_link_arm.rviz',
            ])],
            parameters=[{'use_sim_time': False}],
            condition=IfCondition(LaunchConfiguration('rviz')),
        ),
    ])
