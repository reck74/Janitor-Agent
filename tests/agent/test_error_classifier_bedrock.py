"""Botocore's structured HTTP status participates in the normal retry classifier."""
import pytest
ClientError = pytest.importorskip("botocore.exceptions").ClientError
from agent.error_classifier import classify_api_error, FailoverReason


@pytest.mark.parametrize(('status', 'code', 'reason'), [
    (400, 'ValidationException', FailoverReason.format_error),
    (429, 'ThrottlingException', FailoverReason.rate_limit),
    (503, 'ServiceUnavailableException', FailoverReason.overloaded),
])
def test_botocore_status_is_not_lost(status, code, reason):
    error = ClientError({'Error': {'Code': code, 'Message': 'fixture error'},
                         'ResponseMetadata': {'HTTPStatusCode': status}}, 'Converse')
    result = classify_api_error(error, provider='bedrock')
    assert result.status_code == status
    assert result.reason == reason
