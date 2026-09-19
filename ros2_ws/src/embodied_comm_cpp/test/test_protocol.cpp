#include <limits>
#include <gtest/gtest.h>
#include "embodied_comm_cpp/protocol.hpp"
using namespace embodied_comm_cpp;

TEST(Protocol, PeriodAndBounds) {
  EXPECT_DOUBLE_EQ(period_seconds(2.0), 0.5);
  EXPECT_DOUBLE_EQ(period_seconds(5.0), 0.2);
  EXPECT_DOUBLE_EQ(period_seconds(0.1), 10.0);
  EXPECT_DOUBLE_EQ(period_seconds(100.0), 0.01);
}
TEST(Protocol, RejectInvalidRates) {
  for (double rate : {0.0, -1.0, 0.09, 100.1,
    std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(),
    std::numeric_limits<double>::quiet_NaN()})
  {
    EXPECT_THROW(period_seconds(rate), std::invalid_argument);
  }
}
TEST(Protocol, MessageSequenceAndWrap) {
  for (std::uint64_t seq : {1, 2, 101, 102}) {
    auto reading = parse_sensor(sensor_text(seq));
    EXPECT_EQ(reading.seq, seq);
    EXPECT_DOUBLE_EQ(reading.value, static_cast<double>((seq - 1) % 101));
  }
  EXPECT_THROW(sensor_text(0), std::invalid_argument);
}
TEST(Protocol, AcceptPythonFormat) {
  auto reading = parse_sensor("{\"seq\": 9, \"value\": 101.5}");
  EXPECT_EQ(reading.seq, 9u);
  EXPECT_DOUBLE_EQ(reading.value, 101.5);
}
TEST(Protocol, RejectMalformedMessages) {
  for (const auto * text : {"bad", "[]", "{}", "{\"seq\":true,\"value\":1}",
    "{\"seq\":1.0,\"value\":1}", "{\"seq\":0,\"value\":1}",
    "{\"seq\":1,\"value\":true}", "{\"seq\":1,\"value\":NaN}"})
  {
    EXPECT_THROW(parse_sensor(text), std::invalid_argument);
  }
}
