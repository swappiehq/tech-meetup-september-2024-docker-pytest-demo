from dataclasses import dataclass

import redis.asyncio as redis


@dataclass
class DemoApplication:
    """
    The simple class that is accepting the URI of the redis-like DB service and
     can do only one thing - connect to the service dnd return the output of the INFO command
    """
    storage_uri: str

    async def info(self) -> dict:
        async with redis.from_url(self.storage_uri) as connected:
            return await connected.info()  # type: ignore


async def test_get_name_of_executable_inside_running_redis_container(redis_uri: str) -> None:
    redis_info = await DemoApplication(redis_uri).info()
    assert redis_info["executable"] == "/data/redis-server"


async def test_get_name_of_executable_inside_running_keydb_container(keydb_uri: str) -> None:
    keydb_info = await DemoApplication(keydb_uri).info()
    assert keydb_info["executable"] == "/keydb-server"
