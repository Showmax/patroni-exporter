# patroni-exporter

Provides Patroni related metrics for Prometheus.

This exporter scrapes Patroni API (https://github.com/zalando/patroni) and transforms the obtained information into Prometheus-scrapable (https://prometheus.io/) format.

The following commandline arguments are available:
- port: `-p`, `--port` specifies the port it should listen at
- bind: `-b`, `--bind` specifies the address to bind to
- patroni url: `-u`, `--patroni-url` specifies the full to path the patroni API endpoint
- debug: `-d`, `--debug` enables debug output
- timeout: `-t`, `--timeout` configures the timeout for patroni API
- address family: `-a`, `--address-family` chooses which adress family to use. Either `ipv4` (`AF_INET`) or `ipv6` (`AF_INET6`). If listening on both `ipv6` and `ipv4` is required, `AF_INET6` and a bind to '' or '::' must be used (the unfortunate side-effect is that it listens on all interfaces)
- requests verify: `--requests-verify` Accepts `true|false`, in which case it controls whether Python's requests library verifies the server's TLS certificate. It also accepts a path to a CA bundle to use. Defaults to ``true``

This service also responds on the `/health` endpoint and can be monitored this way.

The `/metrics` endpoint is designated for the prometheus scraping.

The default `9547` port has been reserved on https://github.com/prometheus/prometheus/wiki/Default-port-allocations

Requires python >= 3.6 because of the usage of `f-strings` and type hints.

## Docker

There is a simple `Dockerfile` which allows you to run `patroni-exporter` in the Docker container.
Usage example:

1. Build `patroni-exporter` docker image.

```
docker build -t patroni_exporter .
```

2. Run Docker container. Don't forget to pass required commandline arguments at the end of the `run` command.

```
docker run -d -ti patroni_exporter --port some_port --patroni-url http://some_host_fqdn:some_port/patroni --timeout 5 --debug
```
