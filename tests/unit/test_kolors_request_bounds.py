"""Kolors 文生图/图生图请求参数边界校验（KOL3）。

原内联模型对 num_images/num_inferences/width/height/guidance_scale 无 ge/le 约束，
img2img 路径下游又不做 clamp，可被放大为任意成本的生成请求。
"""

import pytest
from pydantic import ValidationError

from app.api.v1.kolors_api import ImageToImageRequest, TextToImageRequest


@pytest.mark.parametrize(
    "field,value",
    [
        ("num_images", 5),
        ("num_images", 0),
        ("num_inferences", 101),
        ("num_inferences", 0),
        ("width", 1281),
        ("width", 255),
        ("height", 1281),
        ("guidance_scale", 21),
        ("steps", 101),
        ("cfg_scale", 0.5),
    ],
)
def test_text_to_image_rejects_out_of_range(field, value):
    with pytest.raises(ValidationError):
        TextToImageRequest(prompt="x", **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("num_images", 5),
        ("num_inferences", 101),
        ("width", 1281),
        ("height", 255),
        ("guidance_scale", 0),
        ("strength", 1.5),
        ("denoising_strength", -0.1),
        ("steps", 0),
    ],
)
def test_image_to_image_rejects_out_of_range(field, value):
    with pytest.raises(ValidationError):
        ImageToImageRequest(prompt="x", **{field: value})


def test_frontend_values_still_accepted():
    """前端实际取值（512/768/1024、steps 25、cfg 7.5、denoising 0.7）必须放行。"""
    TextToImageRequest(prompt="x", width=1024, height=1024, steps=25, cfg_scale=7.5)
    ImageToImageRequest(
        prompt="x",
        width=512,
        height=768,
        steps=25,
        cfg_scale=7.5,
        denoising_strength=0.7,
        num_images=2,
    )
