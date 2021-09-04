#!/usr/bin/env python3

from collections import defaultdict
from functools import lru_cache

import requests
import datetime
import boto3
import json
import time
import uuid
import os
import re


# Required env vars
environment = os.environ["ENVIRONMENT"]
secret_name = os.environ["SECRET_NAME"]
state_table = os.environ["STATE_TABLE"]
config_bucket = os.environ["CONFIG_BUCKET"]
queue_prefix = os.environ["QUEUE_PREFIX"]
shard_limit = int(os.environ["SHARD_LIMIT"])
alert_queue_url = os.environ["ALERT_QUEUE_URL"]

# Optional env vars
base_auth_url = os.environ.get("BASE_AUTH_URL", "https://slack.com/oauth/authorize")
base_access_url = os.environ.get(
    "BASE_ACCESS_URL", "https://slack.com/api/oauth.access"
)
state_ttl_delta = int(os.environ.get("STATE_TTL_DELTA", "300"))

shards_dir = os.environ.get("SHARDS_DIR", "workspaces/shards")
shards_dir_format = re.compile(fr"{re.escape(shards_dir)}\/(?P<shard>[0-9]+)\/.+")

auth_file_key = os.environ.get(
    "AUTH_BUCKET_KEY", "workspaces/directory/{workspace_id}/auth.json"
)


@lru_cache()
def get_slack_config(slack_secret_name):
    secrets = boto3.client("secretsmanager")
    secret = json.loads(
        secrets.get_secret_value(SecretId=slack_secret_name)["SecretString"]
    )

    return {
        "client_id": secret["CLIENT_ID"],
        "client_secret": secret["CLIENT_SECRET"],
        "scope": secret["SCOPE"],
    }


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
    dynamo = boto3.client("dynamodb")

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

    slack_config = get_slack_config(secret_name)

    return build_redirect_response(
        "{base_auth_url}?client_id={client_id}&scope={scope}&state={state_key}".format(
            base_auth_url=base_auth_url,
            state_key=state_key,
            **slack_config,
        )
    )


def onboard(code, state_key, epoch_seconds):
    dynamo = boto3.client("dynamodb")
    sqs = boto3.client("sqs")
    s3 = boto3.client("s3")

    # Verify that the state_key is still within the DynamoDB table
    response = dynamo.get_item(
        TableName=state_table,
        Key={
            "StateKey": {"S": state_key},
        },
        ReturnConsumedCapacity="NONE",
    )

    if "Item" not in response:
        return build_message_response(
            "Onboarding flow has timed out, please authenticate again",
            status_code=400,
        )

    # Verify that the item's TTL has not expired
    ttl = float(response["Item"]["StateTTL"]["N"])

    if epoch_seconds > ttl:
        return build_message_response(
            "Onboarding flow has timed out, please authenticate again",
            status_code=400,
        )

    slack_config = get_slack_config(secret_name)

    # Use code to retrieve auth creds
    response = requests.post(
        base_access_url,
        data={
            "client_id": slack_config["client_id"],
            "client_secret": slack_config["client_secret"],
            "code": code,
        },
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
        return build_message_response(
            "Provided Slack credentials are invalid", status_code=500
        )

    output = response.json()

    if not output or not output.get("ok"):
        return build_message_response("Slack response wasn't valid", status_code=500)

    if "bot" not in output:
        return build_message_response(
            "Slack response missing the bot scope", status_code=500
        )

    workspace_id = output["team_id"]
    team_name = output["team_name"]

    # Allocate a shard
    # Loop through each shard
    paginator = s3.get_paginator("list_objects_v2")

    response_iterator = paginator.paginate(
        Bucket=config_bucket,
        Prefix=shards_dir,
    )

    shard_counter = defaultdict(int)

    for i, response in enumerate(response_iterator):
        if "Contents" not in response:
            if i == 0:
                shard_counter[0] = 0

            break

        for content in response["Contents"]:
            result = re.match(shards_dir_format, content["Key"])

            if not result:
                continue

            shard = result.groupdict()["shard"]
            shard_counter[shard] += 1

    for shard, load in shard_counter.items():
        if load < shard_limit:
            allocated_shard = shard
            break
    else:
        sqs.send_message(
            QueueUrl=alert_queue_url,
            MessageBody=json.dumps({"message": "Shards are currently oversubscribed"}),
        )

        return build_message_response(
            "Emojirades is currently oversubscribed, please try again later, sorry!"
        )

    workspace_auth_file_key = auth_file_key.format(workspace_id=workspace_id)

    # Allocate this workspace to the shard
    workspace_config = {
        "workspace_id": workspace_id,
        "auth_uri": f"s3://{config_bucket}/{workspace_auth_file_key}",
    }

    s3.put_object(
        Body=json.dumps(workspace_config),
        Bucket=config_bucket,
        ContentType="application/json",
        Key=f"{shards_dir}/{allocated_shard}/{workspace_id}.json",
    )

    # Persist auth tokens to S3
    auth_document = {
        "access_token": output["access_token"],
        "bot_user_id": output["bot"]["bot_user_id"],
        "bot_access_token": output["bot"]["bot_access_token"],
    }

    s3.put_object(
        Body=json.dumps(auth_document),
        Bucket=config_bucket,
        ContentType="application/json",
        Key=auth_file_key.format(workspace_id=workspace_id),
    )

    # Submit SQS event for game bot(s) to reconfigure
    response = sqs.get_queue_url(QueueName=f"{queue_prefix}{allocated_shard}")

    sqs.send_message(
        QueueUrl=response["QueueUrl"],
        MessageBody=json.dumps({"workspace_id": workspace_id}),
    )

    # Let the user know they're good to go
    return build_message_response(f"Successfully onboarded {team_name} to Emojirades!")


def lambda_handler(event, context):
    path = event["requestContext"]["http"]["path"]
    epoch_seconds = event["requestContext"]["timeEpoch"] / 1000

    if path == "/initiate":
        return initiate(epoch_seconds=epoch_seconds)
    elif path == "/onboard":
        parameters = event.get("queryStringParameters")

        if not parameters:
            return build_message_response("Missing code or state parameters")

        code = parameters.get("code")
        state = parameters.get("state")

        if code is None or state is None:
            return build_message_response("Missing code or state parameters")

        return onboard(code, state, epoch_seconds)
    else:
        return build_redirect_response("https://emojirades.io")


def cli_handler():
    pass


if __name__ == "__main__":
    cli_handler()
