#ifndef PREDICTION_API
#define PREDICTION_API

#include <PredictedDatacenterInformation.hpp>
#include <map>
#include <vector>

class PredictionApi {
  public:
    auto getData()
        -> std::map<int, std::vector<PredictedDatacenterInformation>>;
};

#endif
