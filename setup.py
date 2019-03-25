#!/usr/bin/env python
from setuptools import setup

setup(
    name='patroni_exporter',
    version='0.0.1',
    description='Export Patroni metrics in Prometheus format',
    author='Jan Tomsa',
    author_email='ops@showmax.com',
    scripts=['patroni_exporter.py'],
)
