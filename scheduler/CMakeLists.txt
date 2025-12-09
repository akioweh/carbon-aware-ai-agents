cmake_minimum_required(VERSION 3.10)

project(DatacenterScheduler LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(Scheduler
    src/PredictionApi.cpp
    src/ScheduleForDatacenter.cpp
    src/ScheduledInterval.cpp
    src/Scheduler.cpp
)

target_include_directories(Scheduler PRIVATE src)

target_compile_options(Scheduler PRIVATE -Wall -Wextra -Wpedantic)
