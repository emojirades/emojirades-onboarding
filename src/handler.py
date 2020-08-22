#!/usr/bin/env python3

import datetime
import boto3
import json
import time
import uuid
import os


# Boto3 clients
dynamo = boto3.client("dynamodb")
sqs = boto3.client("sqs")
secrets = boto3.client("secretsmanager")


# Required env vars
environment = os.environ["ENVIRONMENT"]
secret_arn = os.environ["SECRET_ARN"]
state_table = os.environ["STATE_TABLE"]

# Optional env vars
base_url = os.environ.get("BASE_URL", "https://slack.com/oauth/authorize")
state_ttl_delta = int(os.environ.get("STATE_TTL_DELTA", "300"))

# Get secret config
secret = json.loads(secrets.get_secret_value(SecretId=secret_arn)["SecretString"])

client_id = secret["CLIENT_ID"]
client_secret = secret["CLIENT_SECRET"]
scope = secret["SCOPE"]


def initiate(epoch_seconds):
    state_key = str(uuid.uuid4())
    state_ttl = epoch_seconds + state_ttl_delta

    response = dynamo.put_item(
        TableName=state_table,
        Item={
            "StateKey": {"S": state_key},
            "StateTTL": {"N": state_ttl},
        },
        ReturnValues="NONE",
        ReturnConsumedCapacity="NONE",
        ReturnItemCollectionMetrics="NONE",
    )

    return {
        "isBase64Encoded": False,
        "statusCode": 302,
        "headers": {
            "Location": f"{base_url}?client_id={client_id}&scope={scope}&state={state_key}",
            "Referrer-Policy": "no-referrer",
        }
    }


def onboard(code, state):
    # Get state from DynamoDB
    # Return failure if it doesn't exist

    # Use code to retrieve auth creds
    # Return failure if it's incorrect

    # Save auth.json in S3 if valid creds
    # Submit SQS event for game bots to reconfigure

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": json.dumps({"message": "Nothing has been done"}),
    }


def lambda_handler(event, context):
    path = event["requestContext"]["http"]["path"]

    if path == "/initiate":
        epoch_seconds = event["requestContext"]["timeEpoch"] / 1000

        return initiate(epoch_seconds=epoch_seconds)
    elif path == "/onboard":
        parameters = event.get("queryStringParameters")

        if not parameters:
            return {
                "isBase64Encoded": False,
                "statusCode": 200,
                "body": json.dumps({"message": "Missing code or state"}),
            }

        code = parameters.get("code")
        state = parameters.get("state")

        if code is None or state is None:
            return {
                "isBase64Encoded": False,
                "statusCode": 200,
                "body": json.dumps({"message": "Missing code or state"}),
            }

        return onboard(None, None)
    else:
        return {
            "isBase64Encoded": False,
            "statusCode": 302,
            "headers": {
                "Location": "https://emojirades.io",
            }
        }


def cli_handler():
    pass


if __name__ == "__main__":
    cli_handler()
