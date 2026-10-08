"""第四周合成关节状态与描述集成；RViz 由用户显式启用。"""

import math

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _finite_float(context, name):
    raw_value = LaunchConfiguration(name).perform(context)
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f"Launch argument '{name}' must be a finite number; got {raw_value!r}"
        ) from error
    if not math.isfinite(value):
        raise RuntimeError(
            f"Launch argument '{name}' must be a finite number; got {raw_value!r}"
        )
    return value


def _launch_nodes(context):
    # Parse before starting any process so arrays are ROS double arrays even
    # when a CLI value is written as an integer. Motion limits remain in C++.
    numeric = {
        name: _finite_float(context, name)
        for name in ('rate', 'frequency', 'joint1', 'joint2', 'amplitude1', 'amplitude2')
    }
    package_share = FindPackageShare('embodied_arm_description')
    model = PathJoinSubstitution([
        package_share, 'urdf', 'two_link_arm.urdf.xacro',
    ])
    # Expand once so both consumers receive the exact same model string.
    robot_description = ParameterValue(
        Command([FindExecutable(name='xacro'), ' ', model]).perform(context),
        value_type=str,
    )
    state_publisher = Node(
        package='robot_state_publisher', executable='robot_state_publisher',
        name='robot_state_publisher', output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': False,
        }],
    )
    cpp_publisher = Node(
        package='embodied_arm_cpp', executable='synthetic_joint_publisher',
        name='synthetic_joint_publisher', output='screen',
        parameters=[{
            'robot_description': robot_description,
            'mode': ParameterValue(LaunchConfiguration('mode'), value_type=str),
            'rate': numeric['rate'],
            'frequency': numeric['frequency'],
            'positions': [numeric['joint1'], numeric['joint2']],
            'amplitudes': [numeric['amplitude1'], numeric['amplitude2']],
            'use_sim_time': False,
        }],
    )
    gui_publisher = Node(
        package='joint_state_publisher_gui', executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui', output='screen',
        parameters=[{'robot_description': robot_description, 'rate': 20}],
    )
    # Instantiate one state source in this launch. Other independently started
    # launches on the same ROS Domain remain the operator's responsibility.
    joint_publisher = (
        cpp_publisher if LaunchConfiguration('state_source').perform(context) == 'cpp'
        else gui_publisher
    )
    # Register before starting the required nodes. Shutdown ends the group;
    # it does not promise a nonzero ros2 launch exit status on a node failure.
    required_node_handlers = [
        RegisterEventHandler(OnProcessExit(
            target_action=node,
            on_exit=[EmitEvent(event=Shutdown(reason=f'{name} exited'))],
        ))
        for node, name in (
            (state_publisher, 'robot_state_publisher'),
            (joint_publisher, 'joint state source'),
        )
    ]
    rviz = Node(
        package='rviz2', executable='rviz2', name='rviz2', output='screen',
        arguments=['-d', PathJoinSubstitution([
            package_share, 'rviz', 'two_link_arm.rviz',
        ])],
        parameters=[{'use_sim_time': False}],
        condition=IfCondition(LaunchConfiguration('use_rviz')),
    )
    # Closing optional RViz leaves the state/TF chain running until Ctrl-C.
    return [*required_node_handlers, state_publisher, joint_publisher, rviz]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'state_source', default_value='cpp', choices=['gui', 'cpp'],
            description='唯一关节状态来源；gui 仅由用户手动启动',
        ),
        DeclareLaunchArgument(
            'mode', default_value='static', choices=['sine', 'static'],
            description='合成运动模式：sine 正弦运动，static 固定关节位置',
        ),
        DeclareLaunchArgument(
            'rate', default_value='20.0',
            description='JointState 发布频率，Hz；范围与采样约束由 C++ 节点校验',
        ),
        DeclareLaunchArgument(
            'frequency', default_value='0.1',
            description='正弦运动频率，Hz；static 模式不用于运动',
        ),
        DeclareLaunchArgument(
            'joint1', default_value='0.0',
            description='joint1 固定位置或正弦中心，rad',
        ),
        DeclareLaunchArgument(
            'joint2', default_value='0.0',
            description='joint2 固定位置或正弦中心，rad',
        ),
        DeclareLaunchArgument(
            'amplitude1', default_value='0.5',
            description='joint1 正弦振幅，rad；static 模式不用于运动',
        ),
        DeclareLaunchArgument(
            'amplitude2', default_value='0.5',
            description='joint2 正弦振幅，rad；static 模式不用于运动',
        ),
        DeclareLaunchArgument(
            'rviz', default_value='false', choices=['true', 'false'],
            description='旧入口兼容别名；建议使用 use_rviz',
        ),
        DeclareLaunchArgument(
            'use_rviz', default_value=LaunchConfiguration('rviz'),
            choices=['true', 'false'],
            description='由用户显式启用 RViz；默认无界面',
        ),
        OpaqueFunction(function=_launch_nodes),
    ])
