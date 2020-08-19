# emojirades-auth
OAuth Server for the Emojirades slackbot

## Usage
Works over CLI or through AWS Lambda


```bash
# Running over CLI

```

## Building Lambda
```bash
docker build -t emojirades_onboarding:latest .

# Copy the package out to your system
docker run -v "${PWD}/release:/opt/mount" --rm --entrypoint cp emojirades_onboarding:latest /src/function.zip /opt/mount/

# Copy the package into S3 or similar to run
```


## How it works
Short explaination about slack OAuth process

How we use DynamoDB for the state persistence
How we use SNS for the game bot reconfiguration
