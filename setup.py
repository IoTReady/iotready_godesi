from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in iotready_godesi/__init__.py
from iotready_godesi import __version__ as version

setup(
	name="iotready_godesi",
	version=version,
	description="IoTReady Custom App For Go Desi",
	author="IoTReady",
	author_email="hello@iotready.co",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
