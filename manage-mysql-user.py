#!/usr/bin/python
import logging
import os
import mysql.connector
import mysql.connector.pooling
from multiprocessing import Process
import boto3

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch

libraries = ('boto3', 'mysql')
patch(libraries)

def handler(event, context):

    logger = logging.getLogger()
    logger.setLevel(os.environ['LOG_LEVEL'])
    logger.info(f"Event: {event}")
