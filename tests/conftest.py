import contextlib
import pathlib
from asyncio import sleep
from timeit import default_timer
from typing import Generator, Callable, Awaitable

import pytest
import redis.asyncio as redis
from pytest_docker.plugin import DockerComposeExecutor, Services


@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    """
    Define a clear static project name to prefix the dependencies.
    Otherwise, the `docker-pytest` will assign itself
    """
    return "pytest-tech-meetup-september-2024-python-docker-demo"


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig: pytest.Config) -> pathlib.Path:
    """
    Define the path to the docker-compose.yml file.
    Depending on the situation you can implement multiple files for various
    purposes and scenarios
    """

    compose_file = "docker-compose-test.linux.yaml"
    return pytestconfig.rootpath / "tests" / compose_file


async def wait_until_responsive(check: Callable[[], Awaitable[bool]], timeout: float, pause: float) -> None:
    """
    Wait until a service is responsive.
    Use this function instead of `docker_services.wait_until_responsive` to support coroutines
    """
    ref = default_timer()
    now = ref
    while (now - ref) < timeout:
        if await check():
            return

        await sleep(pause)
        now = default_timer()

    raise Exception("Timeout reached while waiting on service!")


async def __get_redis_like_service_uri(url: str) -> str:
    """
    Make sure the redis-compatible service  is up and running - and return its URI
    """

    async def is_alive() -> bool:
        try:
            async with redis.from_url(url) as redis_connected:
                return await redis_connected.ping()
        except:  # noqa
            return False

    await wait_until_responsive(timeout=60, pause=0.1, check=is_alive)
    return url


@pytest.fixture(scope="session")
async def redis_uri(docker_ip: str, docker_services: Services) -> str:
    port = docker_services.port_for("redis", 6379)
    return await __get_redis_like_service_uri(f"redis://{docker_ip}:{port}")


@pytest.fixture(scope="session")
async def keydb_uri(docker_ip: str, docker_services: Services) -> str:
    port = docker_services.port_for("keydb", 6379)
    return await __get_redis_like_service_uri(f"redis://{docker_ip}:{port}")


@contextlib.contextmanager
def get_docker_services(
        docker_compose_command,
        docker_compose_file,
        docker_compose_project_name,
        docker_setup,
        docker_cleanup,
) -> Generator[Services, None, None]:
    """
    Force `docker_cleanup` first to ensure we do not have the traces (running containers) from the previous runs;
    these might be left if you have decided to abruptly interrupt the test session -
    for example, when you have just violently killed the process handling the previous test session.
    After that spawn the containers in the "cleaned" environment
    """
    docker_compose = DockerComposeExecutor(docker_compose_command, docker_compose_file, docker_compose_project_name)

    docker_compose.execute(docker_cleanup)  # !< -- cleanup first, just in case
    docker_compose.execute(docker_setup)

    try:
        yield Services(docker_compose)
    finally:
        docker_compose.execute(docker_cleanup)
