from setuptools import setup, find_packages

setup(
    name="mtpsync",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
    ],
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "mtpsync=mtpsync.cli:main",
        ],
    },
)
