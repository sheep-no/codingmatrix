from app.services.image_resource_service import (
    build_image_resource_fingerprint,
    hash_reference_bytes,
)


def _fingerprint(**overrides):
    values = {
        "user_id": 7,
        "model": "Kwai-Kolors/Kolors",
        "generation_type": "text-to-image",
        "prompt": "a red bird",
        "negative_prompt": "blurry",
        "style": "cinematic",
        "reference_hash": None,
        "width": 1024,
        "height": 1024,
        "steps": 50,
        "guidance_scale": 7.5,
        "strength": None,
        "num_images": 1,
        "seed": 42,
    }
    values.update(overrides)
    return build_image_resource_fingerprint(**values)


def test_equivalent_text_and_numeric_values_share_fingerprint():
    first = _fingerprint(prompt="  a red bird  ", guidance_scale=7.5)
    second = _fingerprint(prompt="a red bird", guidance_scale=7.5000001)

    assert first == second


def test_each_output_affecting_parameter_changes_fingerprint():
    baseline = _fingerprint()

    for field, value in {
        "user_id": 8,
        "model": "other-model",
        "generation_type": "image-to-image",
        "prompt": "a blue bird",
        "negative_prompt": "low quality",
        "style": "watercolor",
        "reference_hash": "ref-hash",
        "width": 768,
        "height": 768,
        "steps": 36,
        "guidance_scale": 8.0,
        "strength": 0.5,
        "num_images": 2,
        "seed": 43,
    }.items():
        assert _fingerprint(**{field: value}) != baseline, field


def test_empty_optional_text_is_equivalent_to_none():
    assert _fingerprint(style="   ") == _fingerprint(style=None)
    assert _fingerprint(negative_prompt="  ") == _fingerprint(negative_prompt=None)


def test_reference_hash_uses_content_and_is_independent_of_path():
    content = b"reference-image"

    assert hash_reference_bytes(content) == hash_reference_bytes(bytes(content))
    assert _fingerprint(reference_hash=hash_reference_bytes(content)) != _fingerprint()


def test_non_finite_numeric_value_is_rejected():
    try:
        _fingerprint(guidance_scale=float("nan"))
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("non-finite numeric values must be rejected")
