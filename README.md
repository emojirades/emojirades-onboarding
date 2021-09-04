# emojirades-onboarding
Emojirades Slack Bot onboarding service, manages the OAuth flow with Slack to obtain workspace secrets.

## Usage
Works over CLI or through AWS Lambda


```bash
# Running over CLI

# Runnings tests
cd src; pytest
```

## Building Lambda
```bash
docker build -t emojirades_onboarding:latest .

# Copy the package out to your system
docker run -v "${PWD}/release:/opt/mount" --rm --entrypoint cp emojirades_onboarding:latest /src/function.zip /opt/mount/onboarding-service-$(date +%Y-%m-%d).zip

# Copy the package into S3 or similar to run
aws s3 cp release/onboarding-service-$(date +%Y-%m-%d).zip s3://bucket/path/to/function.zip
```


## How it works
Short explaination about slack OAuth process

How we use DynamoDB for the state persistence
How we use SNS for the game bot reconfiguration
