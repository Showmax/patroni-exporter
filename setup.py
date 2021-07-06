#!/usr/bin/env python
from setuptools import setup

setup(
    name='patroni_exporter',
    version='0.0.2',
    description='Export Patroni metrics in Prometheus format',
    url='https://github.com/Showmax/patroni-exporter',
    author='Jan Tomsa',
    author_email='ops@showmax.com',
    scripts=['patroni_exporter.py'],
    install_requires=['prometheus_client','python-dateutil','requests'],
)
