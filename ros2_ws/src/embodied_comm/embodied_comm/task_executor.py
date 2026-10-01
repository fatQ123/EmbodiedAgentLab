"""保存最新传感器输入，并提供快速服务和可取消的长任务 Action."""
import json
import math
import threading
import time

from embodied_comm.common import (
    EXECUTE_TASK_ACTION, EXECUTE_TASK_SERVICE, nonnegative_parameter,
    parse_sensor, positive_parameter, sensor_qos, SENSOR_TOPIC,
    TASK_STATUS_TOPIC,
)
from embodied_interfaces.action import ExecuteTask
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


class TaskExecutor(Node):
    """执行即时检查与单工位长任务，并共享同一份最新传感器数据."""

    MIN_DURATION_SEC = 0.1
    MAX_DURATION_SEC = 300.0
    FEEDBACK_PERIOD_SEC = 0.2

    def __init__(self, **kwargs):
        super().__init__('task_executor', **kwargs)
        try:
            self.sensor_timeout_sec = positive_parameter(
                self, 'sensor_timeout_sec', 3.0,
            )
            self.fault_service_delay_sec = nonnegative_parameter(
                self, 'fault_service_delay_sec', 0.0,
            )
        except Exception:
            self.destroy_node()
            raise
        # 同一传感器流必须按到达顺序串行处理；请求类接口仍可并发响应。
        self.sensor_callback_group = MutuallyExclusiveCallbackGroup()
        self.request_callback_group = ReentrantCallbackGroup()
        self._sensor_lock = threading.Lock()
        self.latest_reading = None
        self.last_received_at = None
        self.received_count = 0
        self.subscription = self.create_subscription(
            String, SENSOR_TOPIC, self.receive, sensor_qos('reliable'),
            callback_group=self.sensor_callback_group,
        )
        self.task_id = 0
        self._task_id_lock = threading.Lock()
        self.status_publisher = self.create_publisher(String, TASK_STATUS_TOPIC, 10)
        self.service = self.create_service(
            Trigger, EXECUTE_TASK_SERVICE, self.execute_task,
            callback_group=self.request_callback_group,
        )
        self._goal_lock = threading.Lock()
        self._goal_reserved = False
        self._active_goal_handle = None
        self.action_server = ActionServer(
            self,
            ExecuteTask,
            EXECUTE_TASK_ACTION,
            execute_callback=self.execute_long_task,
            goal_callback=self.goal_callback,
            handle_accepted_callback=self.handle_accepted_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.request_callback_group,
        )
        self.get_logger().info(
            f'执行器已启动：话题={self.subscription.topic_name}，'
            f'数据新鲜度={self.sensor_timeout_sec:.2f} 秒，'
            f'快速服务={EXECUTE_TASK_SERVICE}，长任务={EXECUTE_TASK_ACTION}，'
            f'Service 延迟故障={self.fault_service_delay_sec:.2f} 秒'
        )

    def receive(self, message):
        try:
            reading = parse_sensor(message.data)
        except (ValueError, OverflowError) as exc:
            self.get_logger().warning(f'忽略非法传感器消息：{exc}')
            return
        # 仅格式合法的消息更新缓存；越界读数留给任务检查。
        with self._sensor_lock:
            self.latest_reading = reading
            self.last_received_at = time.monotonic()
            self.received_count += 1
            received_count = self.received_count
        self.get_logger().info(
            f'最新传感器：seq={reading["seq"]}，value={reading["value"]:.1f}，'
            f'累计接收={received_count}'
        )

    def sensor_snapshot(self):
        with self._sensor_lock:
            return self.latest_reading, self.last_received_at

    def reading_result(self, reading, received_at):
        """把最新读数转换为统一的成功标志、说明和可空序号."""
        if reading is None or received_at is None:
            return False, '没有有效传感器数据：尚未收到格式合法的读数', None
        age = max(0.0, time.monotonic() - received_at)
        if age >= self.sensor_timeout_sec:
            return (
                False,
                f'传感器数据已过期：last_seq={reading["seq"]}，'
                f'age={age:.2f} 秒，阈值={self.sensor_timeout_sec:.2f} 秒',
                None,
            )
        if not 0.0 <= reading['value'] <= 100.0:
            return (
                False,
                f'检查失败：seq={reading["seq"]}，value={reading["value"]}，'
                '读数不在有效范围 [0, 100]',
                reading['seq'],
            )
        return (
            True,
            f'检查通过：seq={reading["seq"]}，value={reading["value"]}',
            reading['seq'],
        )

    def publish_task_status(self, success, message, sensor_seq):
        """为一次终态分配编号并只发布一条兼容的任务状态."""
        with self._task_id_lock:
            self.task_id += 1
            task_id = self.task_id
        status = {
            'task_id': task_id,
            'success': success,
            'message': message,
            'sensor_seq': sensor_seq,
        }
        self.status_publisher.publish(String(data=json.dumps(status, ensure_ascii=False)))
        self.get_logger().info(f'任务结果：task_id={task_id}，{message}')
        return task_id

    def execute_task(self, request, response):
        if self.fault_service_delay_sec > 0.0:
            self.get_logger().warning(
                f'故障注入：{EXECUTE_TASK_SERVICE} 延迟 '
                f'{self.fault_service_delay_sec:.2f} 秒后响应'
            )
            time.sleep(self.fault_service_delay_sec)
        reading, received_at = self.sensor_snapshot()
        success, message, sensor_seq = self.reading_result(reading, received_at)
        response.success = success
        response.message = message
        self.publish_task_status(success, message, sensor_seq)
        return response

    def goal_callback(self, goal_request):
        task_name = goal_request.task_name.strip()
        duration = float(goal_request.duration_sec)
        if not task_name:
            self.get_logger().warning('拒绝长任务：task_name 不能为空')
            return GoalResponse.REJECT
        if (not math.isfinite(duration)
                or not self.MIN_DURATION_SEC <= duration <= self.MAX_DURATION_SEC):
            self.get_logger().warning(
                f'拒绝长任务 {task_name!r}：duration_sec 必须是 '
                f'[{self.MIN_DURATION_SEC}, {self.MAX_DURATION_SEC}] 内的有限数值'
            )
            return GoalResponse.REJECT
        with self._goal_lock:
            if self._goal_reserved:
                self.get_logger().warning(
                    f'拒绝长任务 {task_name!r}：质检工位正在执行其他任务'
                )
                return GoalResponse.REJECT
            # 在 goal_callback 中预留工位，避免两个并发请求同时被接受。
            self._goal_reserved = True
        self.get_logger().info(
            f'接受长任务：task_name={task_name}，duration={duration:.2f} 秒'
        )
        return GoalResponse.ACCEPT

    def handle_accepted_callback(self, goal_handle):
        with self._goal_lock:
            self._active_goal_handle = goal_handle
        goal_handle.execute()

    def cancel_callback(self, goal_handle):
        with self._goal_lock:
            is_active_goal = goal_handle is self._active_goal_handle and goal_handle.is_active
        if not is_active_goal:
            self.get_logger().warning('拒绝取消：目标已经不是当前活动任务')
            return CancelResponse.REJECT
        self.get_logger().info(
            f'接受取消请求：task_name={goal_handle.request.task_name.strip()}'
        )
        return CancelResponse.ACCEPT

    @staticmethod
    def feedback_phase(progress_percent):
        if progress_percent < 10.0:
            return 'preparing'
        if progress_percent < 90.0:
            return 'inspecting'
        return 'validating'

    def publish_action_feedback(self, goal_handle, progress_percent, phase):
        feedback = ExecuteTask.Feedback()
        feedback.progress_percent = float(progress_percent)
        feedback.phase = phase
        goal_handle.publish_feedback(feedback)

    @staticmethod
    def action_result(success, message, sensor_seq):
        result = ExecuteTask.Result()
        result.success = success
        result.message = message
        result.sensor_seq = sensor_seq if sensor_seq is not None else 0
        return result

    def execute_long_task(self, goal_handle):
        task_name = goal_handle.request.task_name.strip()
        duration = float(goal_handle.request.duration_sec)
        started_at = time.monotonic()
        feedback_period = min(self.FEEDBACK_PERIOD_SEC, duration / 10.0)
        try:
            while True:
                if goal_handle.is_cancel_requested:
                    message = f'任务已取消：task_name={task_name}'
                    goal_handle.canceled()
                    self.publish_task_status(False, message, None)
                    return self.action_result(False, message, None)
                if not goal_handle.is_active:
                    return self.action_result(False, '任务已不再活动', None)

                elapsed = time.monotonic() - started_at
                if elapsed >= duration:
                    break
                progress = min(99.0, elapsed / duration * 100.0)
                phase = self.feedback_phase(progress)
                self.publish_action_feedback(goal_handle, progress, phase)
                self.get_logger().info(
                    f'长任务反馈：task_name={task_name}，phase={phase}，'
                    f'progress={progress:.1f}%'
                )
                time.sleep(min(feedback_period, duration - elapsed))

            # 即使任务很短，也显式给出验证阶段，保证工业流程阶段完整可见。
            self.publish_action_feedback(goal_handle, 99.0, 'validating')
            reading, received_at = self.sensor_snapshot()
            success, check_message, sensor_seq = self.reading_result(
                reading, received_at,
            )
            message = f'task_name={task_name}，{check_message}'
            if not success:
                goal_handle.abort()
                self.publish_task_status(False, message, sensor_seq)
                return self.action_result(False, message, sensor_seq)

            self.publish_action_feedback(goal_handle, 100.0, 'completed')
            goal_handle.succeed()
            self.publish_task_status(True, message, sensor_seq)
            return self.action_result(True, message, sensor_seq)
        finally:
            with self._goal_lock:
                if self._active_goal_handle is goal_handle:
                    self._active_goal_handle = None
                self._goal_reserved = False

    def destroy_node(self):
        if getattr(self, 'action_server', None) is not None:
            self.action_server.destroy()
            self.action_server = None
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    executor = MultiThreadedExecutor(num_threads=4)
    try:
        node = TaskExecutor()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
