#!/usr/bin/env python
"""
Patroni exporter.
Collects metrics from Patroni (https://github.com/zalando/patroni)
and exports them in Prometheus (https://prometheus.io/) format
"""

__author__ = 'Jan Tomsa, Showmax Engineering'
__email__ = 'jan.tomsa@showmax.com'
__date__ = '2019/03/22'
__version__ = '0.0.1'

from dateutil.parser import parse
from collections import defaultdict
from prometheus_client.core import (
    InfoMetricFamily, GaugeMetricFamily, REGISTRY
)
from prometheus_client.exposition import choose_encoder
from typing import List, Any, Dict, Union, Type, ByteString, Iterable
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server, WSGIServer
from wsgiref.util import request_uri

import logging
import argparse
import socket
import requests
from os import environ

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('patroni-exporter')


class PatroniCollector:
    def __init__(self, url: str, timeout: int, verify: str):
        self.url = url
        self.scrape = {}
        self.data: defaultdict[str, Dict[str, Union[str, int, List]]]\
            = defaultdict(dict)
        self.timeout = timeout
        self.requests_verify = next(map(
            lambda v: v.lower() == 'true' if v in ('true', 'false') else v,
            [verify]
        ))

        self.status = '200 OK'

    def scrape_patroni(self) -> None:
        """
        Read information from patroni API

        :return:
        """
        logger.debug(f'Scraping Patroni API at {self.url}.')
        try:
            r = requests.get(self.url, timeout=self.timeout,
                             verify=self.requests_verify)
            self.scrape = r.json()
            if not self.scrape.get('role') == 'replica':
                r.raise_for_status()
            self.status = '200 OK'
        except Exception as e:
            self.status = '503 Service Unavailable'
            self.scrape = {}
            logger.error(f'Scraping of Patroni @ {self.url} failed: {e}')
        logger.debug(f'Scraped data: {self.scrape}')

    @staticmethod
    def to_timestamp(timestring: str) -> int:
        logger.debug(f'Converting {timestring} to unix timestamp')
        return int(parse(timestring).strftime('%s'))

    def preprocessing(self) -> None:
        """
        Group data from Patroni into logical blocks
        :return:
        """

        self.data.clear()

        # Do not perform preprocessing if no data have been scraped
        if not self.scrape:
            return

        # values here specify which keys from scrape
        # will go to which data sections
        scrape_mapping = {
            'postgresql_info': ('server_version', 'database_system_identifier'),
            'patroni_info': ('role', 'state'),
            'postgresql_gauge': ('postmaster_start_time', 'timeline',
                                 'pending_restart'),
            'patroni_gauge': ('cluster_unlocked', 'pause'),
        }

        # these records consist of a dict or a list of dict (replication)
        # and we don't want to put them into a sub-dict,
        # but use them as they are
        direct_mapping = {
            'xlog_gauge': 'xlog',
            'patroni_info': 'patroni',
            'replication_info': 'replication'
        }

        # timestamps to convert to unix time
        timestamp_mapping = {
            'postgresql_gauge': ('postmaster_start_time',),
            'xlog_gauge': ('replayed_timestamp',)
        }

        # use direct mapping to populate data
        for data_key, scrape_key in direct_mapping.items():
            logger.debug(f'Pre-processing {data_key}')
            if scrape_key in self.scrape:
                self.data[data_key] = self.scrape.pop(scrape_key)

        # use the rest of scrape data to populate data
        for key, values in scrape_mapping.items():
            for item in values:
                logger.debug(f'Pre-processing {item}')
                if item in self.scrape:
                    self.data[key][item] = self.scrape.pop(item)

                if item in {'pending_restart', 'cluster_unlocked', 'pause'} \
                        and item not in self.data[key]:
                    logger.debug(f'`{item}`` not in scrape, setting to False')
                    self.data[key][item] = False
                    continue

        # change to timestamp
        for key, items in timestamp_mapping.items():
            for item in items:
                if key in self.data and item in self.data[key]:
                    # replayed_timestamp is None when cluster is fresh and
                    # no data have been replayed on slave
                    if self.data[key][item] is None:
                        self.data[key].pop(item)
                        continue
                    self.data[key][item] = self.to_timestamp(
                        self.data[key][item]
                    )

        logger.debug(f'Preprocessed data: {self.data}')

        if self.scrape:
            logger.warning(f'Not all metrics '
                           f'has been preprocessed: {self.scrape}')

    @staticmethod
    def _process_gauge(data: Dict, label: str) -> List[GaugeMetricFamily]:
        metrics = []
        for k, v in data.items():
            g = GaugeMetricFamily(f'patroni_{label}_{k}',
                                  f'{label} gauge {k}')
            g.add_metric([k], float(v))
            metrics.append(g)

        return metrics

    @staticmethod
    def _process_info(data: Union[Dict, List[Dict]],
                      label: str) -> List[InfoMetricFamily]:
        i = InfoMetricFamily(f'patroni_{label}',
                             f'{label} info')

        # to ensure we have an iterable of dicts
        # the info datasets are different, some are lists of dicts,
        # some are dict only
        if not isinstance(data, (list, tuple)):
            data = [data]

        for dataset in data:
            i.add_metric([], {k: str(v) for k, v in dataset.items()})
        return [i]

    def process_data(self) -> Dict[str, List[Union[GaugeMetricFamily,
                                                   InfoMetricFamily]]]:
        """
        Iterate over the preprocessed data and call respective functions
        to create prometheus metrics
        """
        metrics = {}
        for key, value in self.data.items():
            label, func_type = key.rsplit('_', 1)
            func = getattr(self, f'_process_{func_type}', None)
            if not func:
                raise RuntimeError(f'Metric for {key} cannot be processed. '
                                   f'Required function not found')
            metrics[key] = func(value, label)
        return metrics

    def collect(self) -> Union[GaugeMetricFamily, InfoMetricFamily]:
        """Collects metrics from patroni.
           It is used by the prometheus_client library
        """
        self.scrape_patroni()
        self.preprocessing()

        sections = self.process_data()
        for name, metrics in sections.items():
            logger.debug(f'Processing section {name}')
            for metric in metrics:
                yield metric


class PatroniExporter:
    def __init__(self):
        self.cmdline = self.parse_args()
        if self.cmdline.debug:
            logger.setLevel(logging.DEBUG)

        self.collector = PatroniCollector(self.cmdline.url,
                                          self.cmdline.timeout,
                                          self.cmdline.requests_verify)
        REGISTRY.register(self.collector)

    def get_server_class(self) -> Type['WSGIServer']:
        """
        Creates a WSGI server class with the desired address family set.
        It is a hack to force WSGI to listen on both IPv4 and IPv6
        - it is possible when using AF_INET6 with binding to '' or '::'
        :return:
        """
        class ServerClass(WSGIServer):
            address_family = getattr(socket, self.cmdline.address_family)

        return ServerClass

    @staticmethod
    def parse_args() -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        parser.add_argument('-p', '--port',
                            dest='port',
                            type=int,
                            default=environ.get('PATRONI_EXPORTER_PORT', 9547),
                            help='Port to bind to')
        parser.add_argument('-b', '--bind',
                            dest='bind',
                            default=environ.get('PATRONI_EXPORTER_BIND', ''),
                            help='Interface to listen at')
        parser.add_argument('-u', '--patroni-url',
                            dest='url',
                            default=environ.get('PATRONI_EXPORTER_URL', 'http://localhost:8008/patroni'),
                            help='Patroni API url '
                                 'where to send GET requests to')
        parser.add_argument('-d', '--debug',
                            dest='debug',
                            action='store_true',
                            default=environ.get('PATRONI_EXPORTER_DEBUG', False),
                            help='Enable debug output')
        parser.add_argument('-t', '--timeout',
                            default=environ.get('PATRONI_EXPORTER_TIMEOUT', 5),
                            type=int,
                            dest='timeout',
                            help='Patroni API GET timeout')
        parser.add_argument('-a', '--address-family',
                            dest='address_family',
                            default=environ.get('PATRONI_EXPORTER_ADDRESS_FAMILY', 'AF_INET'),
                            help='Socket address family. For example '
                                 '"AF_INET" for ipv4 or "AF_INET6" for ipv6')
        parser.add_argument('--requests-verify',
                            dest='requests_verify',
                            default=environ.get('PATRONI_EXPORTER_REQUEST_VERIFY', 'true'),
                            help="""Accepts `true|false`, 
                                    in which case it controls
                                    whether requests verify the server's 
                                    TLS certificate, or a path
                                    to a CA bundle to use. 
                                    Defaults to ``true``""")

        known, unknown = parser.parse_known_args()

        # a hack because of the need to pass `-d` or '' via the systemd unit
        unknown = set(unknown) - {'', ' '}
        if unknown:
            parser.error(f'Unknown arguments: {", ".join(unknown)}')
        return known

    def app(self, environ: Dict, start_response: Any) -> Iterable[ByteString]:
        """
        Create a WSGI app which serves the metrics from a registry.
        :param environ:
        :param start_response:
        :return:
        """

        url = urlparse(request_uri(environ))
        if url.path == '/health':
            start_response(self.collector.status, [('Content-Type',
                                                    'application/json')])
            return [b'{}']

        if url.path.startswith('/metric'):
            params = parse_qs(environ.get('QUERY_STRING', ''))
            r = REGISTRY
            encoder, content_type = choose_encoder(environ.get('HTTP_ACCEPT'))
            if 'name[]' in params:
                r = r.restricted_registry(params['name[]'])
            output = encoder(r)

            status = str('200 OK')
            headers = [(str('Content-type'), content_type)]
            start_response(status, headers)
            return [output]

        start_response('404 Not Found', [('Content-Type', 'application/json')])
        return [b'{}']

    def __call__(self) -> None:
        httpd = make_server(self.cmdline.bind,
                            self.cmdline.port,
                            self.app,
                            self.get_server_class())
        httpd.serve_forever()


if __name__ == '__main__':
    pe = PatroniExporter()
    pe()
