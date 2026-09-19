#pragma once

#include <cmath>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <json/json.h>

namespace embodied_comm_cpp {
constexpr const char * kSensorTopic = "/sensor_state";

inline double period_seconds(double rate) {
  if (!std::isfinite(rate) || rate < 0.1 || rate > 100.0) {
    throw std::invalid_argument("publish_rate 必须是 [0.1, 100] Hz 内的有限正数");
  }
  return 1.0 / rate;
}

struct Reading {
  std::uint64_t seq;
  double value;
};

inline std::string sensor_text(std::uint64_t seq) {
  if (seq == 0) {throw std::invalid_argument("seq 必须从 1 开始");}
  Json::Value data;
  data["seq"] = Json::UInt64(seq);
  data["value"] = static_cast<double>((seq - 1) % 101);
  Json::StreamWriterBuilder writer;
  writer["indentation"] = "";
  return Json::writeString(writer, data);
}

inline Reading parse_sensor(const std::string & text) {
  Json::CharReaderBuilder builder;
  builder["allowComments"] = false;
  builder["failIfExtra"] = true;
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  Json::Value data;
  std::string errors;
  if (!reader->parse(text.data(), text.data() + text.size(), &data, &errors) ||
    !data.isObject())
  {
    throw std::invalid_argument("传感器消息必须为合法 JSON 对象");
  }
  const auto & seq = data["seq"];
  const auto & value = data["value"];
  if ((seq.type() != Json::uintValue && seq.type() != Json::intValue) ||
    !seq.isUInt64() || seq.asUInt64() == 0 || !value.isNumeric() ||
    !std::isfinite(value.asDouble()))
  {
    throw std::invalid_argument("seq 必须是正整数，value 必须是有限数值");
  }
  return {seq.asUInt64(), value.asDouble()};
}
}  // namespace embodied_comm_cpp
