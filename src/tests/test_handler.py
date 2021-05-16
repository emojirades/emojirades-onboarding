import os
import json
import time
import uuid
import boto3
import requests

from moto import mock_dynamodb2, mock_sqs, mock_s3, mock_secretsmanager
from unittest.mock import patch

environment = "dev"
region = "ap-southeast-2"
account_id = "123456789012"
shard_count = 1

state_table = f"emo-{environment}-onboarding"
secret_name = f"emo-{environment}-onboarding"
bucket_name = f"emojirades-{environment}"
queue_prefix = f"emo-{environment}-onboarding-service-"
alert_queue = f"emo-{environment}-onboarding-service-alerts"

slack_config = {
    "CLIENT_ID": 123,
    "CLIENT_SECRET": "abc",
    "SCOPE": "bot",
}

environment_config = {
    "ENVIRONMENT": environment,
    "SECRET_NAME": secret_name,
    "STATE_TABLE": state_table,
    "CONFIG_BUCKET": bucket_name,
    "QUEUE_PREFIX": queue_prefix,
    "SHARD_LIMIT": "5",
    "ALERT_QUEUE_URL": f"https://sqs.{region}.amazonaws.com/{account_id}/{alert_queue}",
    "AWS_DEFAULT_REGION": region,
}


def setup_environment(state_key=None, state_ttl=None):
    os.environ.update(environment_config)

    dynamo = boto3.client("dynamodb")
    dynamo.create_table(
        TableName=state_table,
        AttributeDefinitions=[
            {
                "AttributeName": "StateKey",
                "AttributeType": "S",
            },
        ],
        KeySchema=[
            {
                "AttributeName": "StateKey",
                "KeyType": "HASH",
            },
        ],
    )
    dynamo.update_time_to_live(
        TableName=state_table,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "StateTTL"},
    )

    if state_key is not None and state_ttl is not None:
        dynamo.put_item(
            TableName=state_table,
            Item={
                "StateKey": {"S": state_key},
                "StateTTL": {"N": state_ttl},
            },
        )

    secrets = boto3.client("secretsmanager")
    secrets.create_secret(Name=secret_name, SecretString=json.dumps(slack_config))

    s3 = boto3.client("s3")
    s3.create_bucket(
        Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": region}
    )

    sqs = boto3.client("sqs")

    for shard_id in range(0, shard_count):
        sqs.create_queue(QueueName=f"{queue_prefix}{shard_id}")

    sqs.create_queue(QueueName=alert_queue)


@mock_dynamodb2
@mock_sqs
@mock_s3
@mock_secretsmanager
def test_initiate():
    setup_environment()

    epoch_seconds = int(time.time())

    import handler

    response = handler.initiate(epoch_seconds)

    # Get the state item handler created
    dynamo = boto3.client("dynamodb")
    items = dynamo.scan(TableName=state_table).get("Items", [])
    assert len(items) == 1

    state = items[0]
    state_key = state["StateKey"]["S"]

    # Assert the handler response is valid
    assert not response["isBase64Encoded"]
    assert response["statusCode"] == 302
    assert (
        response["headers"]["Location"]
        == f"https://slack.com/oauth/authorize?client_id={slack_config['CLIENT_ID']}&scope={slack_config['SCOPE']}&state={state_key}"
    )
    assert response["headers"]["Referrer-Policy"] == "no-referrer"


@mock_dynamodb2
@mock_sqs
@mock_s3
@mock_secretsmanager
def test_onboard():
    state_key = str(uuid.uuid4())
    epoch_seconds = int(time.time())
    state_ttl = str(epoch_seconds + 60)

    allocated_shard = 0

    setup_environment(state_key=state_key, state_ttl=state_ttl)

    code = "abc123"

    slack_data = {
        "ok": True,
        "team_id": "ABC123",
        "team_name": "Team ABC123",
        "access_token": "xoxo-abab123-12345678910",
        "bot": {
            "bot_user_id": "B001122",
            "bot_access_token": "xoxb-abab123-12345678910",
        },
    }

    class FakeSlackResponse:
        status_code = requests.codes.ok

        @staticmethod
        def json():
            return slack_data

    import handler

    with patch("handler.requests.post") as patched:
        patched.return_value = FakeSlackResponse()
        response = handler.onboard(code, state_key)

    # Validate the response
    assert not response["isBase64Encoded"]
    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    assert (
        response["body"]
        == f'{{"message": "Successfully onboarded {slack_data["team_name"]} to Emojirades!"}}'
    )

    # Validate team was allocated to the correct shard
    s3 = boto3.client("s3")
    response = s3.get_object(
        Bucket=bucket_name,
        Key=f"workspaces/shards/{allocated_shard}/{slack_data['team_id']}.json",
    )
    body = json.load(response["Body"])

    assert body["workspace_id"] == slack_data["team_id"]
    assert (
        body["score_file"]
        == f"s3://{bucket_name}/workspaces/directory/{slack_data['team_id']}/score.json"
    )
    assert (
        body["state_file"]
        == f"s3://{bucket_name}/workspaces/directory/{slack_data['team_id']}/state.json"
    )
    assert (
        body["auth_file"]
        == f"s3://{bucket_name}/workspaces/directory/{slack_data['team_id']}/auth.json"
    )

    # Validate the auth.json file was created
    response = s3.get_object(
        Bucket=bucket_name,
        Key=f"workspaces/directory/{slack_data['team_id']}/auth.json",
    )
    body = json.load(response["Body"])

    assert body["access_token"] == slack_data["access_token"]
    assert body["bot_user_id"] == slack_data["bot"]["bot_user_id"]
    assert body["bot_access_token"] == slack_data["bot"]["bot_access_token"]

    # Validate the SQS message
    sqs = boto3.client("sqs")

    response = sqs.get_queue_url(
        QueueName=f"{environment_config['QUEUE_PREFIX']}{allocated_shard}"
    )

    response = sqs.receive_message(QueueUrl=response["QueueUrl"], MaxNumberOfMessages=1)

    messages = response.get("Messages", [])

    assert len(messages) == 1
    message = messages[0]

    body = json.loads(message["Body"])
    assert body["workspace_id"] == slack_data["team_id"]
