#ifndef SCHEDULER
#define SCHEDULER

#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <ScheduleForDatacenter.hpp>
#include <map>
#include <set>

class Scheduler
{
  private:
    PredictionApi predictionApi; /// I assume we will need some constructor later, otherwise this
                                 /// can be static

    std::set<PredictedDatacenterInformation>
    getCombinedIntervals(std::map<int, std::vector<PredictedDatacenterInformation>> &data);

    double schedule(PredictedDatacenterInformation &interval, JobRequest &job);

  public:
    std::map<int, ScheduleForDatacenter> calculateSchedule(JobRequest job);
};

#endif