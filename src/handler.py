#!/usr/bin/env python3

import datetime
import boto3
import time
import uuid
import os


dynamo = boto3.client("dynamodb")
sqs = boto3.client("sqs")


# Required env vars
environment = os.environ["ENVIRONMENT"]
client_id = os.environ["CLIENT_ID"]
client_secret = os.environ["CLIENT_SECRET"]
scope = os.environ["SCOPE"]
state_table = os.environ["STATE_TABLE"]

# Optional env vars
base_url = os.environ.get("BASE_URL", "https://slack.com/oauth/authorize")
state_ttl_delta = int(os.environ.get("STATE_TTL_DELTA", "300"))




def initiate():
    state_key = str(uuid.uuid4())
    state_ttl = datetime.datetime.now().timestamp() + state_ttl_delta

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
        "action": "redirect",
        "url": f"{base_url}?client_id={client_id}&scope={scope}&state={state}",
    }

def onboard(code, state):
    # Get state from DynamoDB
    # Return failure if it doesn't exist

    # Use code to retrieve auth creds
    # Return failure if it's incorrect

    # Save auth.json in S3 if valid creds
    # Submit SQS event for game bots to reconfigure
    pass

def lambda_handler(event, context):
    pass

def cli_handler():
    pass

if __name__ == "__main__":
    cli_handler()
