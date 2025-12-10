cmake_minimum_required(VERSION 4.2)
project(scheduler)

set(CMAKE_CXX_STANDARD 23)

add_executable(scheduler main.cpp)

target_include_directories(scheduler PRIVATE src)
