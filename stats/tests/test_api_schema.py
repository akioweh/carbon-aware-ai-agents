import schemathesis
from hypothesis import HealthCheck, settings

# current setting it to True blows up your RAM (idk why, maybe because history generation?)
RUN_DIRECTLY = False

if RUN_DIRECTLY:
    from ..app import app

    schema = schemathesis.openapi.from_asgi('/openapi.json', app)
else:
    schema = schemathesis.openapi.from_url('http://127.0.0.1:5000/openapi.json')


# calling as_state_machine is necessary to enable link-following testing
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
)
class APIWorkflow(schema.as_state_machine()):
    pass


TestAPI = APIWorkflow.TestCase
