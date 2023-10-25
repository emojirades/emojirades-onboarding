from setuptools import setup, find_packages
from os import path

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="Emojirades Onboarding",
    version="0.1.0",
    description="Emojirades Onboarding",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/emojirades/emojirades-onboarding",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="slack slackbot emojirades plusplus game",
    packages=find_packages(),
    install_requires=[
        "requests",
    ],
    python_requires="~=3.10",  # Minimum supported version
    extras_require={
        "test": ["boto3", "pytest", "black"],
    },
    author="The Emojirades Team",
    author_email="support@emojirades.io",
)
