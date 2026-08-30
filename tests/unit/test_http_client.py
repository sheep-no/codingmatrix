import asyncio

from app.utils.aicloud import http_client


def test_shared_client_is_recreated_for_a_new_event_loop():
    first_loop = asyncio.new_event_loop()
    second_loop = asyncio.new_event_loop()
    first_client = None
    second_client = None

    try:
        first_client = first_loop.run_until_complete(http_client.get_http_client())
        second_client = second_loop.run_until_complete(http_client.get_http_client())

        assert second_client is not first_client
    finally:
        if second_client is not None:
            second_loop.run_until_complete(second_client.aclose())
        if first_client is not None:
            first_loop.run_until_complete(first_client.aclose())
        http_client._http_client = None
        http_client._http_client_loop = None
        second_loop.close()
        first_loop.close()
