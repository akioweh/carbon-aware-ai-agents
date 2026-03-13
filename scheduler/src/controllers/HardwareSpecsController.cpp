#include "HardwareSpecsController.hpp"
#include <drogon/HttpResponse.h>

namespace scheduler::controllers {
using namespace drogon;
auto HardwareSpecsController::
    getTypesOfGpus( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/) const -> Task<HttpResponsePtr> {
    // to be implemented.
}
} // namespace scheduler::controllers