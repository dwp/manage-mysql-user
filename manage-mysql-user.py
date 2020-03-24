#!/usr/bin/python
import logging
import os
import mysql.connector
import mysql.connector.pooling
import boto3
import random
import string

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch

libraries = ('boto3', 'mysql')
patch(libraries)

# Initialise logging
logger = logging.getLogger(__name__)
log_level = os.environ["LOG_LEVEL"] if "LOG_LEVEL" in os.environ else "INFO"
logger.setLevel(logging.getLevelName(log_level.upper()))
logger.info("Logging at {} level".format(log_level.upper()))

def generate_password():
    valid_chars = string.ascii_letters + string.digits + string.punctuation
    invalid_chars = ['/', '@', '"', '\\', '\''] # Not allowed in a MySQL password
    pw_chars = ''.join([i for i in valid_chars if i not in invalid_chars])
    pw = ''.join((random.choice(pw_chars)) for x in range(40))
    return pw


def update_password_parameter(password,parameter_name):
    ssm = boto3.client('ssm')
    try:
        ssm.put_parameter(Name=parameter_name,
                          Type='SecureString',
                          Value=password,
                          Overwrite=True)
    except Exception as e:
        logger.error(e)


def get_master_password():
    ssm = boto3.client('ssm')
    return ssm.get_parameter(
        Name=os.environ['RDS_MASTER_PASSWORD_PARAMETER_NAME'],
        WithDecryption=True)['Parameter']['Value']


def get_mysql_password(parameter_name):
    ssm = boto3.client('ssm')
    return ssm.get_parameter(
        Name=parameter_name,
        WithDecryption=True)['Parameter']['Value']


def get_connection(password):
    return mysql.connector.connect(
        host = os.environ['RDS_ENDPOINT'],
        user = os.environ['RDS_MASTER_USERNAME'],
        password = password,
        database = os.environ['RDS_DATABASE_NAME'],
        ssl_ca = '/var/task/rds-ca-2019-2015-root.pem',
        ssl_verify_cert = True,
    )


def execute_statement(sql):
    connection = get_connection(get_mysql_password(os.environ['RDS_MASTER_PASSWORD_PARAMETER_NAME']))
    logger = logging.getLogger()
    cursor = connection.cursor()
    cursor.execute(sql)
    connection.commit()
    connection.close()


def execute_query(sql):
    connection = get_connection(get_mysql_password(os.environ['RDS_MASTER_PASSWORD_PARAMETER_NAME']))
    logger = logging.getLogger()
    cursor = connection.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    connection.commit()
    connection.close()
    return result


def check_user_exists(username):
    result = execute_query("SELECT user FROM mysql.user WHERE user = '{}';".format(username))
    if len(result) > 0:
        if username in result[0]:
            logger.debug(f"User {username} found in database: {result}")
            return True
        else:
            logger.error(f"Unexpected query result while checking if user {username} exists in database: {result}")
    else:
        logger.debug(f"User {username} doesn't exist in database")
        return False


def test_connection(username,password_parameter):
    mysql_user_password = get_mysql_password(password_parameter)
    try:
        connection = mysql.connector.connect(
            host = os.environ['RDS_ENDPOINT'],
            user = username,
            password = mysql_user_password,
            database = os.environ['RDS_DATABASE_NAME'],
            ssl_ca = '/var/task/rds-ca-2019-2015-root.pem',
            ssl_verify_cert = True,
        )
    except Exception as e:
        logger.error(e)
        return False
    else:
        return True


def handler(event, context):

    logger.info(f"Event: {event}")

    mysql_user_username = event['mysql_user_username']
    mysql_user_password_parameter_name = event['mysql_user_password_parameter_name']
    database = os.environ['RDS_DATABASE_NAME']

    logger.info(f"Updating {mysql_user_username}")

    pw = generate_password()
    update_password_parameter(pw,mysql_user_password_parameter_name)

    user_exists = check_user_exists(mysql_user_username)
    if user_exists:
        logger.info(f"User {mysql_user_username} already exists in MySQL, will update password")

    # In Aurora CREATE USER IF NOT EXISTS does not update password for existing user, hence SET PASSWORD is required
    execute_statement("CREATE USER IF NOT EXISTS '{}'@'%' IDENTIFIED BY '{}';".format(mysql_user_username,pw))
    execute_statement("SET PASSWORD FOR '{}'@'%' = PASSWORD('{}');".format(mysql_user_username,pw))
    execute_statement("GRANT ALL ON `{}`.* to '{}'@'%';".format(database, mysql_user_username))

    test_result = test_connection(mysql_user_username,mysql_user_password_parameter_name)
    if test_result:
        logger.info(f"Password rotation complete: MySQL user {mysql_user_username} succesfully logged in using password from SSM parameter {mysql_user_password_parameter_name}")
    else:
        raise ValueError(f"Password rotation failed: MySQL user {mysql_user_username} failed to login using password from SSM parameter {mysql_user_password_parameter_name}")
