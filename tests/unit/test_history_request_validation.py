"""HistoryRequest 分页参数必须收敛，避免负 offset / 超大 limit 直达 SQL。"""

import pytest
from pydantic import ValidationError

from app.schema.history import HistoryRequest


def test_defaults_are_valid():
    request = HistoryRequest()

    assert request.limit == 20
    assert request.offset == 0


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_invalid_limit_rejected(limit):
    with pytest.raises(ValidationError):
        HistoryRequest(limit=limit)


def test_negative_offset_rejected():
    with pytest.raises(ValidationError):
        HistoryRequest(offset=-1)
