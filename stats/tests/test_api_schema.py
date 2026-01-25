import schemathesis
from hypothesis import settings

schema = schemathesis.openapi.from_url('http://localhost:5000/openapi.json')


@schema.parametrize()
@settings(max_examples=10)
def test_api(case):
    case.call_and_validate()
