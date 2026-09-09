from app.services.image_resource_service import build_generation_response


def test_generation_response_has_same_shape_for_live_result():
    response = build_generation_response(
        {
            "success": True,
            "images": ["data:image/png;base64,abc"],
            "paths": ["/tmp/generated.png"],
        },
        cached=False,
    )

    assert response == {
        "success": True,
        "cached": False,
        "status": "completed",
        "images": ["data:image/png;base64,abc"],
        "paths": ["/tmp/generated.png"],
        "paths_hash": ["generated.png"],
    }


def test_generation_response_has_same_shape_for_cached_result():
    response = build_generation_response(
        {"success": True, "paths": ["/tmp/cached.png"]},
        cached=True,
    )

    assert response["success"] is True
    assert response["cached"] is True
    assert response["status"] == "completed"
    assert response["images"] == []
    assert response["paths"] == ["/tmp/cached.png"]
    assert response["paths_hash"] == ["cached.png"]
    assert response["message"] == "使用缓存的图片"
