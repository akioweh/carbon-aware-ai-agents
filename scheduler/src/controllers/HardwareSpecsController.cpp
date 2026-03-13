#include "HardwareSpecsController.hpp"
#include "Serializable.hpp"
#include "utils/HardwareConversion.hpp"
#include <drogon/HttpResponse.h>

namespace scheduler::controllers {
using namespace drogon;
auto HardwareSpecsController::
    getTypesOfGpus( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/) const -> Task<HttpResponsePtr> {
    const auto ret = toJson(utils::hardwareConstants::getAvailableGpuTypes());
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}
} // namespace scheduler::controllers