#!/usr/bin/python
import logging
import os
import mysql.connector
import mysql.connector.pooling
import boto3
import random
import string
import json

libraries = ("boto3", "mysql")

# Initialise logging
logger = logging.getLogger(__name__)
log_level = os.environ["LOG_LEVEL"] if "LOG_LEVEL" in os.environ else "INFO"
logger.setLevel(logging.getLevelName(log_level.upper()))
logger.info("Logging at {} level".format(log_level.upper()))

# Use appropriate CA SSL cert to verify RDS identity. Use "AmazonRootCA1.pem" for Aurora Serverless.
# Defaults to "rds-ca-2019-2015-root.pem" to suit normal RDS.
rds_ca_cert = (
    os.environ["RDS_CA_CERT"]
    if "RDS_CA_CERT" in os.environ
    else "/var/task/rds-ca-2019-2015-root.pem"
)


def generate_password():
    valid_chars = string.ascii_letters + string.digits + string.punctuation
    invalid_chars = ["/", "@", '"', "\\", "'"]  # Not allowed in a MySQL password
    pw_chars = "".join([i for i in valid_chars if i not in invalid_chars])
    pw = "".join((random.choice(pw_chars)) for x in range(40))
    logger.debug("Password generated")
    return pw


def update_password_source(password, password_source, password_source_type):
    if password_source_type is "ssm":
        ssm = boto3.client("ssm")
        try:
            ssm.put_parameter(
                Name=password_source,
                Type="SecureString",
                Value=password,
                Overwrite=True,
            )
            logger.debug(f"Password updated in {password_source_type}")
        except Exception as e:
            logger.error(e)
    elif password_source_type is "secretsmanager":
        secretsmanager = boto3.client("secretsmanager")
        try:
            secret_value = {"password": password}
            secretsmanager.put_secret_value(
                SecretId=password_source, SecretString=json.dumps(secret_value)
            )
            logger.debug(f"Password updated in {password_source_type}")
        except Exception as e:
            logger.error(e)
    else:
        raise Exception(f"Unknown password source type: {password_source_type}")


def get_mysql_password(password_source, password_source_type):
    if password_source_type is "ssm":
        ssm = boto3.client("ssm")
        return ssm.get_parameter(Name=password_source, WithDecryption=True)[
            "Parameter"
        ]["Value"]
    elif password_source_type is "secretsmanager":
        secretsmanager = boto3.client("secretsmanager")
        secret_string_json = json.loads(
            secretsmanager.get_secret_value(SecretId=password_source)["SecretString"]
        )
        password = secret_string_json["password"]
        return password
    else:
        raise Exception(f"Unknown password source type: {password_source_type}")


def get_connection(username, password):
    return mysql.connector.connect(
        host=os.environ["RDS_ENDPOINT"],
        user=username,
        password=password,
        database=os.environ["RDS_DATABASE_NAME"],
        ssl_ca=rds_ca_cert,
        ssl_verify_cert=True,
    )


def execute_statement(sql, username, password_source, password_source_type):
    connection = get_connection(
        username, get_mysql_password(password_source, password_source_type)
    )
    logger = logging.getLogger()
    cursor = connection.cursor()
    cursor.execute(sql)
    connection.commit()
    connection.close()


def execute_query(sql, username, password_source, password_source_type):
    connection = get_connection(
        username, get_mysql_password(password_source, password_source_type)
    )
    logger = logging.getLogger()
    cursor = connection.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    connection.commit()
    connection.close()
    return result


def check_user_exists(master_username, username, password_source, password_source_type):
    result = execute_query(
        "SELECT user FROM mysql.user WHERE user = '{}';".format(username),
        master_username,
        password_source,
        password_source_type,
    )
    if len(result) > 0:
        if username in result[0]:
            logger.debug(f"User {username} found in database: {result}")
            return True
        else:
            logger.error(
                f"Unexpected query result while checking if user {username} exists in database: {result}"
            )
    else:
        logger.debug(f"User {username} doesn't exist in database")
        return False


def test_connection(username, password_source, password_source_type):
    mysql_user_password = get_mysql_password(password_source, password_source_type)
    try:
        connection = mysql.connector.connect(
            host=os.environ["RDS_ENDPOINT"],
            user=username,
            password=mysql_user_password,
            database=os.environ["RDS_DATABASE_NAME"],
            ssl_ca=rds_ca_cert,
            ssl_verify_cert=True,
        )
    except Exception as e:
        logger.error(e)
        return False
    else:
        return True


def validate_event(event):
    is_valid = True

    if "mysql_user_username" not in event.keys():
        logger.error(f"Invalid event: 'mysql_user_username' must be set")
        is_valid = False

    # Check that one of these keys is present but not both at the same time
    if ("mysql_user_password_parameter_name" in event.keys()) is (
        "mysql_user_password_secret_name" in event.keys()
    ):
        logger.error(
            f"Invalid event: One and only one of 'mysql_user_password_parameter_name', 'mysql_user_password_secret_name' must be set"
        )
        is_valid = False

    if not is_valid:
        raise ValueError("Invalid event")


def validate_envvars():
    is_valid = True

    if not "RDS_ENDPOINT" in os.environ:
        logger.error(f"Invalid environment variable value: 'RDS_ENDPOINT' must be set")
        is_valid = False

    if not "RDS_DATABASE_NAME" in os.environ:
        logger.error(
            f"Invalid environment variable value: 'RDS_DATABASE_NAME' must be set"
        )
        is_valid = False

    if not "RDS_MASTER_USERNAME" in os.environ:
        logger.error(
            f"Invalid environment variable value: 'RDS_MASTER_USERNAME' must be set"
        )
        is_valid = False

    # Check that one of these vars is present but not both at the same time
    if ("RDS_MASTER_PASSWORD_SECRET_NAME" in os.environ) is (
        "RDS_MASTER_PASSWORD_PARAMETER_NAME" in os.environ
    ):
        logger.error(
            f"Invalid event: One and only one of 'RDS_MASTER_PASSWORD_SECRET_NAME', 'RDS_MASTER_PASSWORD_PARAMETER_NAME' must be set"
        )
        is_valid = False

    if not is_valid:
        raise ValueError("Invalid environment variable value(s)")


def handler(event, context):

    logger.info(f"Event: {event}")

    validate_event(event)
    validate_envvars()

    if "mysql_user_password_secret_name" in event.keys():
        mysql_user_password_source = event["mysql_user_password_secret_name"]
        mysql_user_password_source_type = "secretsmanager"
    else:
        mysql_user_password_source = event["mysql_user_password_parameter_name"]
        mysql_user_password_source_type = "ssm"

    if "RDS_MASTER_PASSWORD_SECRET_NAME" in os.environ:
        mysql_master_password_source = os.environ["RDS_MASTER_PASSWORD_SECRET_NAME"]
        mysql_master_password_source_type = "secretsmanager"
    else:
        mysql_master_password_source = os.environ["RDS_MASTER_PASSWORD_PARAMETER_NAME"]
        mysql_master_password_source_type = "ssm"

    mysql_user_username = event["mysql_user_username"]
    mysql_master_username = os.environ["RDS_MASTER_USERNAME"]
    database = os.environ["RDS_DATABASE_NAME"]

    logger.info(f"Updating {mysql_user_username}")
    pw = generate_password()
    update_password_source(
        pw, mysql_user_password_source, mysql_user_password_source_type
    )
    user_exists = check_user_exists(
        mysql_master_username,
        mysql_user_username,
        mysql_master_password_source,
        mysql_master_password_source_type,
    )
    if user_exists:
        logger.info(
            f"User {mysql_user_username} already exists in MySQL, will update password"
        )

    # In Aurora CREATE USER IF NOT EXISTS does not update password for existing user, hence SET PASSWORD is required
    execute_statement(
        "CREATE USER IF NOT EXISTS '{}'@'%' IDENTIFIED BY '{}';".format(
            mysql_user_username, pw
        ),
        mysql_master_username,
        mysql_master_password_source,
        mysql_master_password_source_type,
    )
    execute_statement(
        "SET PASSWORD FOR '{}'@'%' = PASSWORD('{}');".format(mysql_user_username, pw),
        mysql_master_username,
        mysql_master_password_source,
        mysql_master_password_source_type,
    )
    execute_statement(
        "GRANT ALL ON `{}`.* to '{}'@'%';".format(database, mysql_user_username),
        mysql_master_username,
        mysql_master_password_source,
        mysql_master_password_source_type,
    )

    test_result = test_connection(
        mysql_user_username, mysql_user_password_source, mysql_user_password_source_type
    )
    if test_result:
        logger.info(
            f"Password rotation complete: MySQL user {mysql_user_username} succesfully logged in using password from source {mysql_user_password_source} in {mysql_user_password_source_type}"
        )
    else:
        raise ValueError(
            f"Password rotation failed: MySQL user {mysql_user_username} failed to login using password from source {mysql_user_password_source} in {mysql_user_password_source_type}"
        )
