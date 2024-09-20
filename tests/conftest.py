import contextlib
import pathlib
from asyncio import sleep
from timeit import default_timer
from typing import Generator, Callable, Awaitable, Iterator

import pytest
import redis.asyncio as redis
from pytest_docker.plugin import DockerComposeExecutor, Services


#####
#
#  PART 1. Make sure you have no dangling containers from the previous sessions because you have been violent
#          and killed the python pytest process without giving it a chance to properly stop the containers
#          in the `docker_services` fixture.
#
#####


@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    """
    Define a clear static project name to prefix the dependencies.
    Otherwise, the `docker-pytest` will assign it itself using the PID of the process.
    """
    return "pytest-tech-meetup-september-2024-python-docker-demo"


@contextlib.contextmanager
def get_docker_services(
        docker_compose_command: str,
        docker_compose_file: list[str] | str,
        docker_compose_project_name: str,
        docker_setup: list[str] | str,
        docker_cleanup: list[str] | str,
) -> Generator[Services, None, None]:
    """
    Redefine the context manager here to force `docker_cleanup` first to ensure we do not have the traces
     (running containers) from the previous sessions;
     these might be left if you have decided to abruptly interrupt the test session -
     for example, when you have just violently killed the process handling the previous test session.
    After that spawn the containers in the "cleaned" environment.
    """
    docker_compose = DockerComposeExecutor(
        docker_compose_command, docker_compose_file, docker_compose_project_name
    )

    def do_cleanup(_docker_cleanup_commands):
        if _docker_cleanup_commands:
            # Maintain backwards compatibility with the string format.
            if isinstance(_docker_cleanup_commands, str):
                _docker_cleanup_commands = [_docker_cleanup_commands]
            for cleanup_command in _docker_cleanup_commands:
                docker_compose.execute(cleanup_command)

    do_cleanup(docker_cleanup)  # !< -- cleanup first

    # setup containers.
    if docker_setup:
        # Maintain backwards compatibility with the string format.
        if isinstance(docker_setup, str):
            docker_setup = [docker_setup]
        for command in docker_setup:
            docker_compose.execute(command)

    try:
        # Let test(s) run.
        yield Services(docker_compose)
    finally:
        # Clean up.
        do_cleanup(docker_cleanup)


@pytest.fixture(scope="session")
def docker_services(
        docker_compose_command: str,
        docker_compose_file: list[str] | str,
        docker_compose_project_name: str,
        docker_setup: str,
        docker_cleanup: str,
) -> Iterator[Services]:
    """
    Start all services from a docker compose file (`docker-compose up`).
    After test are finished, shutdown all services (`docker-compose down`).

    Put the fixture here to make sure we are using our customized `get_docker_services` context manager.
    """

    with get_docker_services(
            docker_compose_command,
            docker_compose_file,
            docker_compose_project_name,
            docker_setup,
            docker_cleanup,
    ) as docker_service:
        yield docker_service


#####
#
#  PART 2. Make sure you are can use various docker compose files.
#          You can have multiple docker compose files and define these in your nested `conftest.py` files using the
#          separate fixtures.
#
#####


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig: pytest.Config) -> pathlib.Path:
    """
    Define the path to the docker-compose.yml file.
    Depending on the situation you can implement multiple files for various purposes and scenarios
    """
    compose_file = "docker-compose-test.linux.yaml"
    return pytestconfig.rootpath / "tests" / compose_file


#####
#
#  PART 3. Make sure you can use asyncio-compatible code, because the original codebase does not provide the ready to
#          use utilities.
#          This is not a rocket science but for some reason the original package does not offer such a utility.
#          Feel free to contribute and add it there :)
#
#####


async def wait_until_responsive(check: Callable[[], Awaitable[bool]], timeout: float, pause: float) -> None:
    """
    Wait until a service is responsive.
    Use this function instead of `docker_services.wait_until_responsive` to support coroutines.

    In most of the cases you do not want to introduce extra python packages to communicate with the external deps
     that are different from what you use in the production code. So if you are relying on asyncio in you production
     code & you are using the packages that do not have the sync interfaces, then you will just have to make something
     like this by yourself.
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


#######
#
#  PART 4. (BONUS) Make sure you can access the dependencies which _might_ be a bit tricky if your tests are also
#          running inside a docker container that does not have its own dockerd inside.
#
######


@pytest.fixture(scope="session")
def am_i_running_inside_container() -> bool:
    # You can build some checks here based on the env variables, for example.
    return False


@pytest.fixture(scope="session")
def docker_host(docker_ip: str, am_i_running_inside_container: bool) -> str:
    """
    A lot of trickery going on with this situation.

    But in a nutshell, you might have a situation that you have a host with dockerd and your tests are packaged inside
     docker image, so you want to run these tests from there.
    And also you do not have the dockerd _inside_ you image with tests, so you want to ask a host to also run these
     dependencies for you.

     ----------------------------          ----------------------         -------------------------------------------
     |  Container running tests |  < -- >  |  Host with dockerd |  < -->  |  Containers with dependencies for tests |
     ----------------------------          ----------------------         -------------------------------------------

    In this case you will have to control the host dockerd by mapping its socket file to yours inside your container
     with tests:

        docker run -v /var/run/docker.sock:/var/run/docker.sock

    But also, in this case you cannot just access 127.0.0.1 and expect to see the exposed ports of the dependencies
     there, because now 127.0.0.1 from the tests point of view is not the host where all the dependencies have exposed
     their ports. But! we can establish the docker bridge network, so the containers will be able to communicate with
     each other. For that we have 2 options: use the default bridge or create the new one in docker-compose.yml and
     attach the services to it, and attach the container with tests to it.
    In case of default bridge, we will have to communicate with the services by their IP. In case of the custom bridge
     we can assign the hostnames to the services inside the network, and, after we will attach the container with tests
     to this network, we will be able to access these by the hostnames.

    In both cases we will have to issue additional commands like `docker inspect` and `docker network connect`, and
     there is another alternative that is at the same time simpler but hackier.
    It is to allow the traffic from the container with tests to go to the host and access the exposed dependencies ports
     from there. For that you have to access the host using the magic hostname "host.docker.internal" which is
     associated with the default docker's bridge network where your container with tests is in by default.
    This is really a very badly documented thing and there are not a lot of things you can find about it in the official
     docker documentation:

        https://docs.docker.com/engine/network/drivers/bridge/#use-the-default-bridge-network
        https://docs.docker.com/reference/cli/dockerd/#configure-host-gateway-ip

    Also, you will have to run the `docker run` command in your host with

        docker run -v /var/run/docker.sock:/var/run/docker.sock --add-host=host.docker.internal:host-gateway

     to explicitly allow the access from the container to the host. It is not always required, and depends on the OS of
     the host that is running the dockerd.
    """
    if am_i_running_inside_container:
        return "host.docker.internal"

    else:
        return docker_ip


# NB! if we are connecting to the service through the dockerd host + exposed port, use the `docker_services.port_for`
# which under the hood calls `docker compose port` command to get the exposed port, which might not be static
# if you have defined the range of ports

@pytest.fixture(scope="session")
async def redis_uri(docker_ip: str, docker_services: Services) -> str:
    port = docker_services.port_for("redis", 6379)
    return await __get_redis_like_service_uri(f"redis://{docker_ip}:{port}")


@pytest.fixture(scope="session")
async def keydb_uri(docker_ip: str, docker_services: Services) -> str:
    port = docker_services.port_for("keydb", 6379)
    return await __get_redis_like_service_uri(f"redis://{docker_ip}:{port}")
