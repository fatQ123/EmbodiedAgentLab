#include <chrono>
#include <functional>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include "embodied_comm_cpp/protocol.hpp"

class SensorSimulator : public rclcpp::Node {
public:
  SensorSimulator() : Node("sensor_simulator") {
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.read_only = true;
    descriptor.description = "发布频率，0.1～100 Hz，仅启动时配置";
    const auto rate = declare_parameter<double>("publish_rate", 2.0, descriptor);
    const auto period = embodied_comm_cpp::period_seconds(rate);
    publisher_ = create_publisher<std_msgs::msg::String>(embodied_comm_cpp::kSensorTopic, 10);
    timer_ = create_wall_timer(std::chrono::duration<double>(period),
      std::bind(&SensorSimulator::publish_reading, this));
    RCLCPP_INFO(get_logger(), "C++ 传感器启动：话题=%s，频率=%.2f Hz",
      publisher_->get_topic_name(), rate);
  }
private:
  void publish_reading() {
    std_msgs::msg::String message;
    message.data = embodied_comm_cpp::sensor_text(++seq_);
    publisher_->publish(message);
    RCLCPP_INFO(get_logger(), "发布：%s", message.data.c_str());
  }
  std::uint64_t seq_{0};
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  int result = 0;
  try {
    rclcpp::spin(std::make_shared<SensorSimulator>());
  } catch (const std::exception & error) {
    RCLCPP_ERROR(rclcpp::get_logger("sensor_simulator"), "%s", error.what());
    result = 1;
  }
  rclcpp::shutdown();
  return result;
}
