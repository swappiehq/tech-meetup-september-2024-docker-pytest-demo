Simple demo scenario to demonstrate the power of `pytest-docker` and
the few minor changes you could add there to better serve your needs.

The project contains a simple function communicating with the [KeyDB](https://docs.keydb.dev/)
and [Redis](https://redis.io/)
databases and the tests to demonstrate how to utilize the
dependencies in a convenient pytest-style way using the fixtures.

#### How to use it

There is a single folder named test and a simple `requirement.txt` file. Just install the requirements from it

```shell
pip install -r requirements.txt
```

and then
run the

```shell
pytest
```

or build the docker image and run the tests there

```shell
docker run -it -v /var/run/docker.sock:/var/run/docker.sock --add-host=host.docker.internal:host-gateway --entrypoint pytest $(docker build -q .)
```