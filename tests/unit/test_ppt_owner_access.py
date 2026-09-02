from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1 import aiGeneratorPptx


def test_ppt_owner_registration_and_access(tmp_path, monkeypatch):
    monkeypatch.setattr(aiGeneratorPptx, "PPT_OWNER_DIR", Path(tmp_path))

    aiGeneratorPptx._register_ppt_owner("ppt-1", "user-1")
    aiGeneratorPptx._verify_ppt_owner("ppt-1", "user-1")

    with pytest.raises(HTTPException) as error:
        aiGeneratorPptx._verify_ppt_owner("ppt-1", "user-2")
    assert error.value.status_code == 403


def test_unknown_ppt_owner_is_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr(aiGeneratorPptx, "PPT_OWNER_DIR", Path(tmp_path))

    with pytest.raises(HTTPException) as error:
        aiGeneratorPptx._verify_ppt_owner("missing", "user-1")
    assert error.value.status_code == 404
