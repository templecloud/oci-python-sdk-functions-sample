#!/bin/bash

# A simple helper script to install the specified version of the oci-python-sdk.

SDK_VERSION=oci-python-sdk-2.2.11+preview.1.819

echo "Creating venv '.venv'"
python3 -m venv .venv
source .venv/bin/activate

echo "Installing ${SDK_VERSION}"
curl https://artifactory.oci.oraclecorp.com/opc-public-sdk-dev-pypi-local/${SDK_VERSION}.zip -o ${SDK_VERSION}.zip
unzip ${SDK_VERSION}.zip -d ${SDK_VERSION}
pushd ${SDK_VERSION}/oci-python-sdk
pip install *.whl
# clean up
popd
rm ${SDK_VERSION}.zip
rm -Rf ${SDK_VERSION}

echo "Done."