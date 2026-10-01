"""共享消息格式、启动参数校验与节点生命周期."""
import json
import math

from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

SENSOR_TOPIC = '/sensor_state'
TASK_STATUS_TOPIC = '/task_status'
DIAGNOSTICS_TOPIC = '/diagnostics'
EXECUTE_TASK_SERVICE = '/execute_task'
EXECUTE_TASK_ACTION = '/execute_task_long'


def positive_parameter(node, name, default):
    value = node.declare_parameter(
        name, default,
        ParameterDescriptor(read_only=True, description='有限正数；仅启动时配置'),
    ).value
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} 必须是有限正数，收到 {value}')
    return value


def nonnegative_parameter(node, name, default):
    value = node.declare_parameter(
        name, default,
        ParameterDescriptor(read_only=True, description='有限非负数；仅启动时配置'),
    ).value
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} 必须是有限非负数，收到 {value}')
    return value


def choice_parameter(node, name, default, choices):
    """声明只读字符串枚举参数，并在节点启动时拒绝未知值."""
    value = node.declare_parameter(
        name, default,
        ParameterDescriptor(
            read_only=True,
            description=f'仅启动时配置；可选值：{", ".join(choices)}',
        ),
    ).value
    if value not in choices:
        raise ValueError(
            f'{name} 必须是 {", ".join(choices)} 之一，收到 {value!r}'
        )
    return value


def sensor_qos(reliability='reliable'):
    """返回显式的传感器 QoS，避免依赖中间件默认值."""
    policies = {
        'reliable': ReliabilityPolicy.RELIABLE,
        'best_effort': ReliabilityPolicy.BEST_EFFORT,
    }
    if reliability not in policies:
        raise ValueError(f'未知传感器可靠性：{reliability!r}')
    return QoSProfile(
        depth=10,
        reliability=policies[reliability],
        durability=DurabilityPolicy.VOLATILE,
    )


def period_seconds(rate):
    if not math.isfinite(rate) or not 0.1 <= rate <= 100.0:
        raise ValueError('publish_rate 必须是 [0.1, 100] Hz 内的有限正数')
    return 1.0 / rate


def sensor_text(seq):
    if type(seq) is not int or seq < 1:
        raise ValueError('seq 必须从 1 开始')
    return json.dumps({'seq': seq, 'value': float((seq - 1) % 101)}, allow_nan=False)


def parse_sensor(text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('传感器消息必须为 JSON 对象')
    seq, value = data.get('seq'), data.get('value')
    if type(seq) is not int or seq < 1:
        raise ValueError('seq 必须是从 1 开始的整数')
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('value 必须是有限数值')
    return {'seq': seq, 'value': value}


def parse_task_status(text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('任务状态必须为 JSON 对象')
    if type(data.get('task_id')) is not int or data['task_id'] < 1:
        raise ValueError('task_id 必须是正整数')
    if type(data.get('success')) is not bool or not isinstance(data.get('message'), str):
        raise ValueError('任务状态必须包含布尔 success 和字符串 message')
    if 'sensor_seq' not in data:
        raise ValueError('缺少 sensor_seq')
    seq = data['sensor_seq']
    if seq is not None and (type(seq) is not int or seq < 1):
        raise ValueError('sensor_seq 必须为正整数或 null')
    if data['success'] and seq is None:
        raise ValueError('成功任务必须包含传感器序号')
    return data


def run_node(node_type, args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = node_type()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
