#include <cstdint>
#include <memory>
#include <optional>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include "embodied_comm_cpp/protocol.hpp"

class StatusMonitor : public rclcpp::Node {
public:
  StatusMonitor() : Node("status_monitor") {
    subscription_ = create_subscription<std_msgs::msg::String>(
      embodied_comm_cpp::kSensorTopic, 10,
      [this](const std_msgs::msg::String & message) {receive(message);});
    RCLCPP_INFO(get_logger(), "C++ 监控器启动：话题=%s", subscription_->get_topic_name());
  }
private:
  void receive(const std_msgs::msg::String & message) {
    try {
      latest_ = embodied_comm_cpp::parse_sensor(message.data);
    } catch (const std::exception & error) {
      RCLCPP_WARN(get_logger(), "忽略非法传感器消息：%s", error.what());
      return;
    }
    ++count_;
    RCLCPP_INFO(get_logger(), "收到传感器：seq=%llu，value=%.1f，累计=%llu",
      static_cast<unsigned long long>(latest_->seq), latest_->value,
      static_cast<unsigned long long>(count_));
  }
  std::optional<embodied_comm_cpp::Reading> latest_;
  std::uint64_t count_{0};
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<StatusMonitor>());
  rclcpp::shutdown();
  return 0;
}
