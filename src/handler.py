#!/usr/bin/env python3

import requests
import datetime
import boto3
import json
import time
import uuid
import os


# Boto3 clients
dynamo = boto3.client("dynamodb")
sqs = boto3.client("sqs")
s3 = boto3.client("s3")
secrets = boto3.client("secretsmanager")


# Required env vars
environment = os.environ["ENVIRONMENT"]
secret_arn = os.environ["SECRET_ARN"]
state_table = os.environ["STATE_TABLE"]
auth_bucket = os.environ["AUTH_BUCKET"]
queue_url = os.environ["QUEUE_URL"]

# Optional env vars
base_auth_url = os.environ.get("BASE_AUTH_URL", "https://slack.com/oauth/authorize")
base_access_url = os.environ.get("BASE_ACCESS_URL", "https://slack.com/api/oauth.access")
state_ttl_delta = int(os.environ.get("STATE_TTL_DELTA", "300"))
auth_bucket_key = os.environ.get("AUTH_BUCKET_KEY", "teams/{team_id}/auth.json")

# Get secret config
secret = json.loads(secrets.get_secret_value(SecretId=secret_arn)["SecretString"])

client_id = secret["CLIENT_ID"]
client_secret = secret["CLIENT_SECRET"]
scope = secret["SCOPE"]


def build_response(status_code=200, headers=None, body=None):
    response = {
        "isBase64Encoded": False,
        "statusCode": status_code,
    }

    if headers is not None:
        response["headers"] = headers

    if body is not None:
        response["body"] = body

    return response


def build_redirect_response(url):
    headers = {
        "Location": url,
        "Referrer-Policy": "no-referrer",
    }

    return build_response(
        status_code=302,
        headers=headers,
    )


def build_message_response(message, **kwargs):
    if kwargs.get("headers"):
        kwargs["headers"]["Content-Type"] = "application/json"
    else:
        kwargs["headers"] = {"Content-Type": "application/json"}

    return build_response(
        body=json.dumps({"message": message}),
        **kwargs,
    )


def initiate(epoch_seconds):
    state_key = str(uuid.uuid4())
    state_ttl = str(epoch_seconds + state_ttl_delta)

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

    return build_redirect_response(f"{base_auth_url}?client_id={client_id}&scope={scope}&state={state_key}")

def onboard(code, state_key):
    # Verify that the state_key is still within the DynamoDB table
    response = dynamo.get_item(
        TableName=state_table,
        Key={
            "StateKey": {"S": state_key},
        },
        ReturnConsumedCapacity="NONE",
    )

    if "Item" not in response:
        return build_message_response("Onboarding flow has timed out, please authenticate again", status_code=400)

    # Use code to retrieve auth creds
    response = requests.post(
        base_access_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        }
    )

    # Remove our state_key to stop any replays
    # Once the 'post' is sent, the code is considered invalid
    dynamo.delete_item(
        TableName=state_table,
        Key={
            "StateKey": {"S": state_key},
        },
        ReturnValues="NONE",
        ReturnConsumedCapacity="NONE",
        ReturnItemCollectionMetrics="NONE",
    )

    if response.status_code != requests.codes.ok:
        return build_message_response("Provided Slack credentials are invalid")

    output = response.json()

    if not output or not output.get("ok"):
        return build_message_response("Slack response wasn't valid")

    if "bot" not in output:
        return build_message_response("Slack response missing the bot scope")

    # Persist auth tokens to S3
    team_id = output["team_id"]
    team_name = output["team_name"]

    auth_document = {
        "access_token": output["access_token"],
        "bot_user_id": output["bot"]["bot_user_id"],
        "bot_access_token": output["bot"]["bot_access_token"],
    }

    s3.put_object(
        Body=json.dumps(auth_document),
        Bucket=auth_bucket,
        ContentType="application/json",
        Key=auth_bucket_key.format(team_id=team_id),
    )

    # Submit SQS event for game bot(s) to reconfigure
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"team_id": team_id}),
    )


    # Let the user know they're good to go
    return build_message_response(f"Successfully onboarded {team_name} to Emojirades!")


def lambda_handler(event, context):
    path = event["requestContext"]["http"]["path"]

    if path == "/initiate":
        epoch_seconds = event["requestContext"]["timeEpoch"] / 1000

        return initiate(epoch_seconds=epoch_seconds)
    elif path == "/onboard":
        parameters = event.get("queryStringParameters")

        if not parameters:
            return build_message_response("Missing code or state parameters")

        code = parameters.get("code")
        state = parameters.get("state")

        if code is None or state is None:
            return build_message_response("Missing code or state parameters")

        return onboard(code, state)
    else:
        return build_redirect_response("https://emojirades.io")


def cli_handler():
    pass


if __name__ == "__main__":
    cli_handler()
