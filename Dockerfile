FROM python:3.13

RUN apt-get update && apt-get install zip

# Build dependencies into zip
WORKDIR /src/package
COPY requirements.txt .
RUN pip3 install --upgrade --no-cache-dir -r requirements.txt --target . && rm requirements.txt
RUN zip --quiet -r9 ../function.zip .

# Build source into zip
WORKDIR /src/code
COPY src .
RUN zip --quiet -g -r ../function.zip *

WORKDIR /src
CMD ["bash"]
