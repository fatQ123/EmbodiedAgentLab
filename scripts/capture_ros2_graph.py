#!/usr/bin/env python3
"""使用本机 Jazzy rqt_graph 插件采集实时图；Qt 可离屏运行。

用系统 Python，先 source ROS 环境。输出是实际插件窗口截图和原始 DOT，
不是手工绘制的架构图。此实验脚本使用 rqt_graph 的内部接口，升级后需复验。
"""
import argparse
import time
from pathlib import Path

import rclpy
from python_qt_binding.QtCore import QObject
from python_qt_binding.QtWidgets import QApplication
from rqt_graph.ros_graph import RosGraph


class CaptureContext(QObject):
    def __init__(self, node):
        super().__init__()
        self.node = node

    def serial_number(self):
        return 1

    def add_widget(self, widget):
        self.widget = widget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--wrong-topic', action='store_true')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    rclpy.init(args=[])
    node = rclpy.create_node('rqt_graph_capture')
    context = CaptureContext(node)
    plugin = None
    try:
        deadline = time.monotonic() + 12
        required = {'sensor_simulator', 'task_executor', 'status_monitor'}
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if required <= set(node.get_node_names()):
                break
        assert required <= set(node.get_node_names()), '三个业务节点尚未发现'
        plugin = RosGraph(context)
        widget = plugin._widget
        widget.resize(1400, 700)
        widget.setWindowTitle('ROS 2 live graph — ' + args.output_dir.name)
        widget.graph_type_combo_box.setCurrentIndex(2)  # Nodes/Topics (all)
        widget.dead_sinks_check_box.setChecked(False)
        widget.leaf_topics_check_box.setChecked(False)
        widget.unreachable_check_box.setChecked(False)
        widget.quiet_check_box.setChecked(True)
        widget.filter_line_edit.setText('/sensor_simulator,/task_executor,/status_monitor')
        widget.topic_filter_line_edit.setText('/sensor_state,/sensor_state_wrong,/task_status')
        widget.auto_fit_graph_check_box.setChecked(True)
        plugin.initialized = True
        widget.show()
        required_text = ['/sensor_state', '/task_status', '/task_executor', '/status_monitor']
        if args.wrong_topic:
            required_text.append('/sensor_state_wrong')
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.2)
            app.processEvents()
            plugin._update_rosgraph()
            app.processEvents()
            if all(text in (plugin._current_dotcode or '') for text in required_text):
                break
        assert all(text in (plugin._current_dotcode or '') for text in required_text), '实时图发现不完整'
        plugin._fit_in_view()
        app.processEvents()
        (args.output_dir / 'rqt_graph.dot').write_text(plugin._current_dotcode)
        assert widget.grab().save(str(args.output_dir / 'rqt_graph.png'))
    finally:
        if plugin is not None:
            plugin.shutdown_plugin()
            plugin._widget.close()
        node.destroy_node()
        rclpy.try_shutdown()
        app.quit()


if __name__ == '__main__':
    main()
