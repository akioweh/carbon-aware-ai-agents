#ifndef CORO
#define CORO

#include <atomic>
#include <coroutine>
#include <cstddef>
#include <iostream>
#include <vector>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>

namespace scheduler::coro
{
    namespace detail
    {
        template<typename T>
        class Handler
        {
            std::vector<T> results ;
            std::coroutine_handle<> whenAllHandle;
            std::atomic<size_t> activeJobsCounter; 

            public:
            Handler(size_t numberOfJobs) : activeJobsCounter(numberOfJobs)
            {
                results.resize(numberOfJobs) ;
            }

            auto await_ready() -> bool
            {
                return false;
            }

            auto await_suspend(std::coroutine_handle<> injectedHandle)
            {
                whenAllHandle = injectedHandle; 
            }

            auto await_resume() -> std::vector<T>
            {
                return std::move(results); 
            }

            auto jobFinished()
            {   
                if(activeJobsCounter.fetch_sub(1) == 1) resumeWhenAll();
            }

            auto resumeWhenAll()
            {
                whenAllHandle.resume();
            }

            auto saveResult(size_t index, T value)
            {
                results[index] = std::move(value);
            }
        };
    }

        template<typename T>
        auto when_all(std::vector<drogon::Task<T>> jobs) -> drogon::Task<std::vector<T>>
        {
            auto numberOfJobs = jobs.size(); 
            auto manager = make_shared<detail::Handler<T>>(numberOfJobs) ;
            auto taskWrapper = [](size_t index, drogon::Task<T> job, std::shared_ptr<detail::Handler<T>> manager) -> drogon::Task<>
            {
                manager->saveResult(index, co_await job) ;
                manager->jobFinished();
                co_return;
            };

            for(int i=0;i<numberOfJobs;i++) async_run(taskWrapper(i,std::move(jobs[i]),manager)) ;

            co_return co_await *manager; 
        }
}


#endif