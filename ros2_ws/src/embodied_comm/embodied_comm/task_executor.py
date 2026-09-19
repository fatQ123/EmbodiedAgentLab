"""保存最新传感器输入，并按请求快速检查读数。"""
import json
import time

from std_srvs.srv import Trigger

from rclpy.node import Node
from std_msgs.msg import String

from embodied_comm.common import (
    EXECUTE_TASK_SERVICE, SENSOR_TOPIC, TASK_STATUS_TOPIC, parse_sensor, run_node,
)


class TaskExecutor(Node):
    def __init__(self, **kwargs):
        super().__init__('task_executor', **kwargs)
        self.latest_reading = None
        self.last_received_at = None
        self.received_count = 0
        self.subscription = self.create_subscription(
            String, SENSOR_TOPIC, self.receive, 10,
        )
        self.task_id = 0
        self.status_publisher = self.create_publisher(String, TASK_STATUS_TOPIC, 10)
        self.service = self.create_service(Trigger, EXECUTE_TASK_SERVICE, self.execute_task)
        self.get_logger().info(
            f'执行器已启动：话题={self.subscription.topic_name}，等待传感器数据'
        )

    def receive(self, message):
        try:
            reading = parse_sensor(message.data)
        except (ValueError, OverflowError) as exc:
            self.get_logger().warning(f'忽略非法传感器消息：{exc}')
            return
        # 仅格式合法的消息更新缓存；越界读数留给任务检查。
        self.latest_reading = reading
        self.last_received_at = time.monotonic()
        self.received_count += 1
        self.get_logger().info(
            f'最新传感器：seq={reading["seq"]}，value={reading["value"]:.1f}，'
            f'累计接收={self.received_count}'
        )

    def execute_task(self, request, response):
        reading = self.latest_reading
        if reading is None:
            response.success = False
            response.message = '没有有效传感器数据：尚未收到格式合法的读数'
        elif not 0.0 <= reading['value'] <= 100.0:
            response.success = False
            response.message = (
                f'检查失败：seq={reading["seq"]}，value={reading["value"]}，'
                '读数不在有效范围 [0, 100]'
            )
        else:
            response.success = True
            response.message = f'检查通过：seq={reading["seq"]}，value={reading["value"]}'
        self.task_id += 1
        status = {
            'task_id': self.task_id,
            'success': response.success,
            'message': response.message,
            'sensor_seq': reading['seq'] if reading is not None else None,
        }
        self.status_publisher.publish(String(data=json.dumps(status, ensure_ascii=False)))
        self.get_logger().info(f'任务结果：task_id={self.task_id}，{response.message}')
        return response


def main(args=None):
    run_node(TaskExecutor, args)
