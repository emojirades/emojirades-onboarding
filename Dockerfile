FROM python:3.8

RUN apt-get update && apt-get install zip

# Copy in code
WORKDIR /src
COPY requirements.txt .
COPY src code/

# Build dependencies into zip
WORKDIR /src/package
RUN pip3 install --upgrade --no-cache-dir -r ../requirements.txt --target .
RUN zip --quiet -r9 ../function.zip .

# Build source into zip
WORKDIR /src/code
RUN zip -g -r ../function.zip *

WORKDIR /src
CMD ["bash"]
