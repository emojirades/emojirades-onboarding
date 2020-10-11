import os
import json
import boto3

from moto import mock_dynamodb2, mock_sqs, mock_s3, mock_secretsmanager
from unittest.mock import Mock, patch

slack_config = {
    "CLIENT_ID": 123,
    "CLIENT_SECRET": "abc",
    "SCOPE": "bot",
}


@mock_dynamodb2
@mock_sqs
@mock_s3
@mock_secretsmanager
def test_initiate():
    # Setup
    os.environ["ENVIRONMENT"] = "dev"
    os.environ["SECRET_NAME"] = "emo-dev-onboarding"
    os.environ["STATE_TABLE"] = "emo-dev-onboarding"
    os.environ["AUTH_BUCKET"] = "emojirades"
    os.environ["QUEUE_URL"] = "https://sqs.ap-southeast-2.amazonaws.com/12345678910/emo-dev-onboarding-service"
    os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-2"

    dynamo = boto3.client("dynamodb")
    dynamo.create_table(
        TableName="emo-dev-onboarding",
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

    secrets = boto3.client("secretsmanager")
    secrets.create_secret(
        Name="emo-dev-onboarding",
        SecretString=json.dumps(slack_config),
    )

    # Run the handler
    import handler
    response = handler.initiate(1602392178)

    # Get the state item handler created
    items = dynamo.scan(TableName="emo-dev-onboarding").get("Items", [])
    assert len(items) == 1

    state = items[0]
    state_key = state["StateKey"]["S"]

    # Assert the handler response is valid
    assert not response["isBase64Encoded"]
    assert response["statusCode"] == 302
    assert response["headers"]["Location"] == f"https://slack.com/oauth/authorize?client_id={slack_config['CLIENT_ID']}&scope={slack_config['SCOPE']}&state={state_key}"
    assert response["headers"]["Referrer-Policy"] == "no-referrer"

@mock_dynamodb2
@mock_sqs
@mock_s3
@mock_secretsmanager
@patch('handler.onboard.requests.post')
def test_onboard():
    pass
