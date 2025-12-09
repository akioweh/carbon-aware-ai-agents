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
    static const unsigned int KWH = 1000 * 60 * 60 ;

    PredictionApi predictionApi; /// I assume we will need some constructor later, otherwise this
                                 /// can be static

    std::map<int,ScheduleForDatacenter>fullSchedule;

    std::multiset<PredictedDatacenterInformation>
    getCombinedIntervals(std::map<int, std::vector<PredictedDatacenterInformation>> &data);

    double schedule(PredictedDatacenterInformation &interval, JobRequest &job);

  public:
    double calculateSchedule(JobRequest job);
    void show();
};

#endif