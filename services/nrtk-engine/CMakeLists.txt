cmake_minimum_required(VERSION 3.25)
project(nrtk_engine VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(nrtk_health src/health.c)
target_include_directories(nrtk_health PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_options(nrtk_health PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(nrtk-engine src/main.cpp)
target_link_libraries(nrtk-engine PRIVATE nrtk_health)
target_compile_options(nrtk-engine PRIVATE -Wall -Wextra -Wpedantic -Werror)

enable_testing()
add_executable(nrtk-health-test tests/health_test.c)
target_link_libraries(nrtk-health-test PRIVATE nrtk_health)
add_test(NAME nrtk-health-test COMMAND nrtk-health-test)
