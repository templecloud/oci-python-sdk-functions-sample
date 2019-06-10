# Invoke Oracle Functions using the OCI Python SDK

This example demonstrates how to invoke an Oracle function on Oracle Cloud Infrastructur using the OCI Python SDK. The examples are implemented using `static functions` for easy re-use in starter projects.

Specifically, we:

1. Create a `Vcn`, `Internet Gateway`, `Route`, and single `Subnet` in the `us-phoenix-1` OCI region.

2. Register and configure a new `Application` and `Function` for a pre-created `function image`.

3. Invoke the `Function`.

4. Clean up the OCI resources created in Steps 1 and 2.

> NB: This example does not create the `function image` or the OCI `compartment` the resources are namespace to. This must be performed manually.

---

## Pre-requisites

Before the sample code can be successfully run, we need to create a function image to invoke, and obtain the OCI `compartmentId` we wish to created our resources in.

### Creating a Function Image

The easiest way create and publish a function image is using your favourite text editor and `Fn` open source CLI tool.

1. [Install Fn CLI](https://github.com/fnproject/cli) - Install the `Fn` CLI.

2. [Create and Publish Function](https://github.com/fnproject/fn/blob/master/README.md) - Create and publish a simple 'HelloWorld' function using the `Fn` CLI.


### OCI Compartments

We also need an OCI `Compartment` OCID as a namespace for our resources. Information on how to create a compartment and find a compartment's OCID can be found [here](https://docs.cloud.oracle.com/iaas/Content/Identity/Tasks/managingcompartments.htm?Highlight=compartment).

---

## Running the sample

The associated `Makefile` contains various phony `make` targets for executing the `run-setup`, `run-invoke`, and, `run-teardown` tasks. 

1. __Build__ : Run `make build` to build the sample.

    > NB: Feel free to change unexposed parameters in the sample before compiling!

2. __Export COMPARTMENT_ID or COMPARTMENT_NAME__ : Run `export COMPARTMENT_ID=${your-oci-compartment-id}` to define the compartment to use.

3. __Export OCIR_FN_IMAGE__ : Run `export OCIR_FN_IMAGE=${your-ocir-function-image}` to define the Function image to use.

4. __Export FN_PAYLOAD [optional]__ : Run `export FN_PAYLOAD=${your-function-payload}` to ddefine a payload for your Function.

5. __Create OCI Resources__ : Run `make run-setup` to create all the required OCI resources to invoke a Function: `VCN`, `Internet Gateway`, `Outbound Route`, `Subnet`, `Application`, and `Function`.

    > NB: All resources should be created in your target compartment with a `oci-java-sdk-function-example`. Please look at the `OCI console` to see what has been created.

6. __Invoke OCI Function__ : Run `make run-invoke` to invoke the Function created in the previous step.

7. __Destroy OCI Resources__ : When you have finished, run `make run-teardown` to destroy the resource created in `Step 5`. Please check everything completes with no errors or stack traces. If so, please delete the remaining resources manually using the `OCI console`.

    > NB: Do not try to perform this until after 30 minutes from your last function invocation. Currently, the Function platform expects a grace period before cleaning up resources.

---

## Other Resources

* [Fn Project](https://github.com/fnproject)

* [OCI Docs](https://docs.cloud.oracle.com/iaas/Content/home.htm)

* [Python SDK](https://docs.cloud.oracle.com/iaas/Content/API/SDKDocs/python.htm)

* [Sample code to invoke a Function using the Python SDK](https://github.com/denismakogon/fn-python-sdk-invoke)


