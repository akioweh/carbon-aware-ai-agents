#ifndef JOB_REQUEST
#define JOB_REQUEST

#include <Serializable.hpp>
#include <chrono>
#include <string>
#include <utility>

class JobRequest {
  public:
    std::string job_type;
    double workload_amount;
    std::chrono::system_clock::time_point earliest_start;
    std::chrono::system_clock::time_point latest_finish;
    std::string jobId;

    JobRequest(std::string job_type, double workload_amount,
               std::chrono::system_clock::time_point earliest_start,
               std::chrono::system_clock::time_point latest_finish,
               std::string jobId)
        : job_type(std::move(job_type)), workload_amount(workload_amount),
          earliest_start(earliest_start), latest_finish(latest_finish),
          jobId(std::move(jobId)) {};
};

#endif
