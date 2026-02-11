#ifndef JOB_REQUEST
#define JOB_REQUEST
#pragma once

#include <Serializable.hpp>
#include <chrono>
#include <string>

struct JobRequest {
    std::string job_type;
    double workload_amount;
    std::chrono::system_clock::time_point earliest_start;
    std::chrono::system_clock::time_point latest_finish;
};

#endif
