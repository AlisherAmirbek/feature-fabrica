from setuptools import find_packages, setup

from feature_fabrica import __version__

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="feature_fabrica",
    version=__version__,
    packages=find_packages(),
    url="https://github.com/cowana-ai/feature-fabrica",
    include_package_data=True,
    description="Open-source Python library designed to improve engineering practices and transparency in feature engineering.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Chingis Oinar",
    author_email="chingisoinar@gmail.com",
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    license="MIT",
)
