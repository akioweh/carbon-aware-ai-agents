#ifndef JOB_REQUEST
#define JOB_REQUEST

#include <string>

class JobRequest
{
    public:
    long long deadline;
    std::string type; /// this will later be some sort of specific job type, given by enum.
    double work; /// given in units of computation.
    int jobId;
};

#endif