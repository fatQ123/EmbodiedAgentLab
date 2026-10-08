#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <rcl_interfaces/msg/set_parameters_result.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <urdf/model.h>

namespace
{
constexpr double kPi = 3.141592653589793;
constexpr std::size_t kJointCount = 2;

struct JointInfo
{
  std::string name;
  double lower;
  double upper;
  double velocity;
};

std::vector<JointInfo> parse_joints(const std::string & description)
{
  urdf::Model model;
  if (description.empty() || !model.initString(description)) {
    throw std::invalid_argument("robot_description must contain valid URDF XML");
  }
  auto link = model.getLink("tool0");
  if (!model.getLink("base_link") || !link) {
    throw std::invalid_argument("robot_description must contain base_link and tool0");
  }

  std::vector<JointInfo> joints;
  while (link->name != "base_link") {
    const auto joint = link->parent_joint;
    const auto parent = link->getParent();
    if (!joint || !parent) {
      throw std::invalid_argument("tool0 must descend from base_link in robot_description");
    }
    if (joint->type != urdf::Joint::FIXED) {
      if (joint->type != urdf::Joint::REVOLUTE || joint->mimic) {
        throw std::invalid_argument(
          "base_link to tool0 supports only fixed and independent revolute joints");
      }
      const auto limits = joint->limits;
      if (!limits || !std::isfinite(limits->lower) || !std::isfinite(limits->upper) ||
        !std::isfinite(limits->velocity) || limits->lower > limits->upper ||
        limits->velocity < 0.0)
      {
        throw std::invalid_argument("invalid position or velocity limits for " + joint->name);
      }
      joints.push_back({joint->name, limits->lower, limits->upper, limits->velocity});
    }
    link = parent;
  }
  if (joints.size() != kJointCount) {
    throw std::invalid_argument("base_link to tool0 must contain exactly 2 revolute joints");
  }
  // Traversal collected tool-to-base order; parameter arrays use base-to-tool order.
  std::reverse(joints.begin(), joints.end());
  return joints;
}

rcl_interfaces::msg::ParameterDescriptor startup_parameter(const std::string & description)
{
  rcl_interfaces::msg::ParameterDescriptor descriptor;
  descriptor.read_only = true;
  descriptor.description = description + "; startup only";
  return descriptor;
}

void validate_array(const std::string & name, const std::vector<double> & values)
{
  if (values.size() != kJointCount) {
    throw std::invalid_argument(name + " must contain exactly 2 values in URDF chain order");
  }
  for (const auto value : values) {
    if (!std::isfinite(value)) {
      throw std::invalid_argument(name + " values must be finite");
    }
  }
}
}  // namespace

class SyntheticJointPublisher : public rclcpp::Node
{
public:
  SyntheticJointPublisher() : Node("synthetic_joint_publisher")
  {
    if (get_parameter("use_sim_time").as_bool()) {
      throw std::invalid_argument("use_sim_time=true is unsupported for synthetic joint states");
    }
    const auto description = declare_parameter<std::string>(
      "robot_description", "", startup_parameter("URDF XML defining base_link to tool0"));
    joints_ = parse_joints(description);

    mode_ = declare_parameter<std::string>(
      "mode", "static", startup_parameter("Synthetic state mode: static or sine"));
    const auto rate = declare_parameter<double>(
      "rate", 20.0, startup_parameter("Publication rate in Hz, in [0.1, 100]"));
    rcl_interfaces::msg::ParameterDescriptor position_descriptor;
    position_descriptor.description =
      "Two static positions or sine centers in rad, ordered from base_link toward tool0";
    const auto positions = declare_parameter<std::vector<double>>(
      "positions", std::vector<double>{0.0, 0.0},
      position_descriptor);
    amplitudes_ = declare_parameter<std::vector<double>>(
      "amplitudes", std::vector<double>{0.5, 0.5},
      startup_parameter("Two nonnegative sine amplitudes in rad, in URDF chain order"));
    const auto frequency = declare_parameter<double>(
      "frequency", 0.1, startup_parameter("Positive finite sine frequency in Hz"));

    if (mode_ != "static" && mode_ != "sine") {
      throw std::invalid_argument("mode must be static or sine");
    }
    if (!std::isfinite(rate) || rate < 0.1 || rate > 100.0) {
      throw std::invalid_argument("rate must be finite and in [0.1, 100] Hz");
    }
    if (!std::isfinite(frequency) || frequency <= 0.0) {
      throw std::invalid_argument("frequency must be positive and finite in Hz");
    }
    validate_array("amplitudes", amplitudes_);
    for (const auto amplitude : amplitudes_) {
      if (amplitude < 0.0) {
        throw std::invalid_argument("amplitudes must be nonnegative");
      }
    }
    if (mode_ == "sine") {
      if (rate < 10.0 * frequency) {
        throw std::invalid_argument("sine mode requires rate >= 10 * frequency");
      }
      angular_frequency_ = 2.0 * kPi * frequency;
    }
    validate_positions(positions);
    std::copy(positions.begin(), positions.end(), positions_.begin());

    // Validate without side effects: another callback or descriptor may reject
    // the same atomic transaction. Only the post-set callback commits state.
    parameter_callback_ = add_on_set_parameters_callback(
      std::bind(&SyntheticJointPublisher::validate_parameters, this, std::placeholders::_1));
    commit_callback_ = add_post_set_parameters_callback(
      [this](const std::vector<rclcpp::Parameter> & parameters) {
        // rclcpp uses the last value if a transaction repeats a parameter name.
        for (auto it = parameters.rbegin(); it != parameters.rend(); ++it) {
          if (it->get_name() == "positions") {
            const auto & values = it->as_double_array();
            std::lock_guard<std::mutex> lock(positions_mutex_);
            std::copy(values.begin(), values.end(), positions_.begin());
            break;
          }
        }
      });

    for (const auto & joint : joints_) {
      message_.name.push_back(joint.name);
    }
    message_.position.resize(kJointCount);
    if (mode_ == "sine") {
      message_.velocity.resize(kJointCount);
    }
    // Static mode has no generated velocity; leave velocity empty.
    // effort remains empty: these are synthetic kinematic states, not measurements.
    const auto qos = rclcpp::QoS(rclcpp::KeepLast(10)).reliable().durability_volatile();
    publisher_ = create_publisher<sensor_msgs::msg::JointState>("/joint_states", qos);
    start_time_ = std::chrono::steady_clock::now();
    timer_ = create_wall_timer(
      std::chrono::duration<double>(1.0 / rate),
      std::bind(&SyntheticJointPublisher::publish_state, this));
    RCLCPP_INFO(
      get_logger(),
      "Synthetic joint states only: topic=%s mode=%s rate=%.3f Hz order=[%s, %s]; not measured",
      publisher_->get_topic_name(), mode_.c_str(), rate,
      joints_[0].name.c_str(), joints_[1].name.c_str());
  }

private:
  void validate_positions(const std::vector<double> & positions) const
  {
    validate_array("positions", positions);
    for (std::size_t i = 0; i < kJointCount; ++i) {
      const auto & joint = joints_[i];
      if (positions[i] < joint.lower || positions[i] > joint.upper) {
        throw std::invalid_argument(
          "position for " + joint.name + " must lie in [" +
          std::to_string(joint.lower) + ", " + std::to_string(joint.upper) + "] rad");
      }
      if (mode_ == "sine") {
        const double minimum = positions[i] - amplitudes_[i];
        const double maximum = positions[i] + amplitudes_[i];
        if (!std::isfinite(minimum) || !std::isfinite(maximum) ||
          minimum < joint.lower || maximum > joint.upper)
        {
          throw std::invalid_argument("sine motion exceeds position limits for " + joint.name);
        }
        const double peak_velocity = amplitudes_[i] * angular_frequency_;
        if (!std::isfinite(peak_velocity) || peak_velocity > joint.velocity) {
          throw std::invalid_argument("sine peak velocity exceeds URDF limit for " + joint.name);
        }
      }
    }
  }

  rcl_interfaces::msg::SetParametersResult validate_parameters(
    const std::vector<rclcpp::Parameter> & parameters) const
  {
    rcl_interfaces::msg::SetParametersResult result;
    result.successful = true;
    const rclcpp::Parameter * positions = nullptr;
    for (const auto & parameter : parameters) {
      // Keep TimeSource's built-in declaration while disallowing runtime changes.
      if (parameter.get_name() == "use_sim_time") {
        result.successful = false;
        result.reason = "use_sim_time is startup only and must remain false";
        return result;
      }
      if (parameter.get_name() == "positions") {
        positions = &parameter;
      }
    }
    if (positions) {
      if (positions->get_type() != rclcpp::ParameterType::PARAMETER_DOUBLE_ARRAY) {
        result.successful = false;
        result.reason = "positions must be a double array";
        return result;
      }
      try {
        validate_positions(positions->as_double_array());
      } catch (const std::invalid_argument & error) {
        result.successful = false;
        result.reason = error.what();
      }
    }
    return result;
  }

  void publish_state()
  {
    std::array<double, kJointCount> positions;
    {
      std::lock_guard<std::mutex> lock(positions_mutex_);
      positions = positions_;
    }
    std::copy(positions.begin(), positions.end(), message_.position.begin());
    if (mode_ == "sine") {
      const double elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - start_time_).count();
      const double phase = angular_frequency_ * elapsed;
      const double sine = std::sin(phase);
      const double cosine = std::cos(phase);
      for (std::size_t i = 0; i < kJointCount; ++i) {
        message_.position[i] = positions[i] + amplitudes_[i] * sine;
        message_.velocity[i] = amplitudes_[i] * angular_frequency_ * cosine;
      }
    }
    message_.header.stamp = now();
    publisher_->publish(message_);
  }

  std::string mode_;
  std::vector<JointInfo> joints_;
  std::array<double, kJointCount> positions_{};
  std::mutex positions_mutex_;
  std::vector<double> amplitudes_;
  double angular_frequency_{0.0};
  std::chrono::steady_clock::time_point start_time_;
  sensor_msgs::msg::JointState message_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameter_callback_;
  rclcpp::node_interfaces::PostSetParametersCallbackHandle::SharedPtr commit_callback_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  int result = 0;
  try {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<SyntheticJointPublisher>());
  } catch (const std::exception & error) {
    RCLCPP_ERROR(rclcpp::get_logger("synthetic_joint_publisher"), "%s", error.what());
    result = 1;
  }
  if (rclcpp::ok()) {
    rclcpp::shutdown();
  }
  return result;
}
