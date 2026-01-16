#ifndef UTILS
#define UTILS

#include <string>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>

namespace scheduler::utils
{
  auto parseTimestampSeconds(const std::string &timestamp) -> long long;
  auto makeGetRequest(const std::string &host, const std::string &path)
      -> drogon::Task<std::shared_ptr<Json::Value>> ;
}

#endif