#ifndef SCHEDULER
#define SCHEDULER

#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <ScheduleForDatacenter.hpp>
#include <map>
#include <set>

class Scheduler {
  private:
    static const unsigned int KWH = 1000 * 60 * 60;

    PredictionApi predictionApi; /// I assume we will need some constructor
                                 /// later, otherwise this can be static

    std::map<int, ScheduleForDatacenter> fullSchedule;

    auto getCombinedIntervals(
        std::map<int, std::vector<PredictedDatacenterInformation>> &data)
        -> std::multiset<PredictedDatacenterInformation>;

    auto schedule(PredictedDatacenterInformation &interval, JobRequest &job)
        -> double;

  public:
    auto calculateSchedule(JobRequest job) -> double;
    void show() const;
};

#endif
