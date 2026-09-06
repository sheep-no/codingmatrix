from app.services.image_metrics_service import ImageGenerationMetric, ImageGenerationMetrics


def test_metrics_record_and_summary():
    metrics = ImageGenerationMetrics()
    metrics.record(
        ImageGenerationMetric(
            user_id=1,
            generation_type="text-to-image",
            profile="preview",
            cache_hit=True,
            total_duration_ms=10,
            retry_count=0,
            image_count=1,
            output_bytes=100,
            status="completed",
        )
    )
    metrics.record(
        ImageGenerationMetric(
            user_id=1,
            generation_type="text-to-image",
            profile="preview",
            cache_hit=False,
            total_duration_ms=20,
            retry_count=1,
            image_count=0,
            output_bytes=0,
            status="failed",
            failure_code="invalid_image",
        )
    )

    assert metrics.summary() == {
        "requests": 2,
        "cache_hits": 1,
        "images": 1,
        "output_bytes": 100,
        "completed": 1,
        "failed": 1,
    }
