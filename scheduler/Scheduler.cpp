#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <ScheduleForDatacenter.hpp>
#include <Scheduler.hpp>

using namespace std;

set<PredictedDatacenterInformation>
Scheduler::getCombinedIntervals(map<int, vector<PredictedDatacenterInformation>> &data)
{
    set<PredictedDatacenterInformation> intervals;

    for (auto [datacenterId, predictions] : data)
    {
        for (auto prediction : predictions)
        {
            intervals.insert(prediction);
        }
    }

    return intervals;
}

double Scheduler::schedule(PredictedDatacenterInformation &interval, JobRequest &job)
{
    double maxWorkInInterval =
        (interval.datacenterInfo.maxLoad - interval.currentLoad) * interval.lengthOfInterval;

    if (maxWorkInInterval >= job.work)
    {
        job.work = 0;
        return job.work / interval.lengthOfInterval; /// this is the additional load
    }
    else
    {
        job.work -= maxWorkInInterval;
        return maxWorkInInterval;
    }
}

map<int, ScheduleForDatacenter> Scheduler::calculateSchedule(JobRequest job)
{
    auto data = predictionApi.getData();

    auto intervals = getCombinedIntervals(data);

    map<int, ScheduleForDatacenter> fullSchedule;

    while (intervals.size() > 0 && job.work > 0)
    {
        auto interval = *intervals.begin();
        double additionalLoad = schedule(interval, job);

        if (fullSchedule.count(interval.datacenterInfo.datacenterId) == 0)
        {
            auto scheduleForDC = ScheduleForDatacenter(interval.datacenterInfo);
            fullSchedule[interval.datacenterInfo.datacenterId] = scheduleForDC;
        }

        auto scheduledInterval =
            ScheduledInterval(interval.timestamp, job.jobId, additionalLoad, interval.currentLoad);

        fullSchedule[interval.datacenterInfo.datacenterId].addInterval(scheduledInterval);
    }

    return fullSchedule;
}

int main()
{
    JobRequest job = JobRequest(127, "NORMAL", 1500.0, 1);
    Scheduler scheduler; 
    auto idk = scheduler.calculateSchedule(job);
}