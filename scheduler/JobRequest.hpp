#ifndef JOB_REQUEST
#define JOB_REQUEST

#include <string>

class JobRequest
{
    public:
    long long deadline;
    std::string type; /// this will later be some sort of specific job type, given by enum.
    long long work; /// given in units of computation.
};

#endif