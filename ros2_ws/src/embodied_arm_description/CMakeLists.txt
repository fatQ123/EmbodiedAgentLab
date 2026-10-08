cmake_minimum_required(VERSION 3.8)
project(embodied_arm_description)

find_package(ament_cmake REQUIRED)

install(DIRECTORY urdf launch rviz DESTINATION share/${PROJECT_NAME})
install(FILES LICENSE DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_model test/test_model.py)
endif()

ament_package()
