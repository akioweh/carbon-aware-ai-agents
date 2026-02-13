#ifndef SCHEDULER_EXCEPTION_HANDLER_HPP
#define SCHEDULER_EXCEPTION_HANDLER_HPP
#include "exceptions/NetworkException.hpp"
#pragma once

#include "SchedulingException.hpp"
#include "ValidationException.hpp"
#include <drogon/HttpAppFramework.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>

namespace scheduler::exceptions {

/**
 * @brief Registers the application-wide exception handler on the drogon app.
 *
 * Maps domain exceptions to HTTP error responses:
 * - ValidationException  -> 422 Unprocessable Entity
 * - SchedulingException  -> 409 Conflict
 * - anything else        -> delegates to drogon's default handler (500)
 *
 * Must be called before drogon::app().run().
 */
inline void registerExceptionHandler() {
    auto defaultHandler = drogon::app().getExceptionHandler();
    drogon::app().setExceptionHandler(
        [defaultHandler = std::move(defaultHandler)](
            const std::exception &e, const drogon::HttpRequestPtr &req,
            std::function<void(const drogon::HttpResponsePtr &)> &&callback)
            -> void {
            auto makeErrorResponse =
                [](drogon::HttpStatusCode status,
                   const char *message) -> drogon::HttpResponsePtr {
                Json::Value body;
                body["error"] = message;
                auto resp = drogon::HttpResponse::newHttpJsonResponse(body);
                resp->setStatusCode(status);
                return resp;
            };

            if (const auto *ex =
                    dynamic_cast<const ValidationException *>(&e)) {
                callback(makeErrorResponse(drogon::k422UnprocessableEntity,
                                           ex->what()));
                return;
            }
            if (const auto *ex =
                    dynamic_cast<const SchedulingException *>(&e)) {
                callback(makeErrorResponse(drogon::k409Conflict, ex->what()));
                return;
            }
            if (const auto *ex = dynamic_cast<const NetworkException *>(&e)) {
                callback(makeErrorResponse(drogon::k503ServiceUnavailable,
                                           ex->what()));
                return;
            }
            defaultHandler(e, req, std::move(callback));
        });
}

} // namespace scheduler::exceptions

#endif // SCHEDULER_EXCEPTION_HANDLER_HPP
