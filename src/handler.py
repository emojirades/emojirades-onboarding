#!/usr/bin/env python3

import boto3
import uuid
import os


base_url = os.environ.get("BASE_URL", "https://slack.com/oauth/authorize")
client_id = os.environ["CLIENT_ID"]
scope = os.environ["SCOPE"]


dynamo = boto3.client("dynamodb")
sqs = boto3.client("sqs")


def setup():
    state = uuid.uuid4()
    # Persist state to DynamoDB with 10 min TTL

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
