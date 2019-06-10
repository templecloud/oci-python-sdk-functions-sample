import logging
import os
import sys

import oci

from oci import config
from oci import core
from oci import functions
from oci import identity
from oci import pagination

from oci.core import models as core_models
from oci.functions import models as fn_models
from oci.identity import models as identity_models

NAME_PREFIX="oci-python-sdk-function-example"

SETUP = "setup"
INVOKE = "invoke"
TEARDOWN = "teardown"

def setup_resources(oci_cfg, compartment_id, name, image: str):
    """
    Setup the minimal OCI resources required to establish an invocable function.

    :param compartment_id: The compartment_id in which to create the resources.
    :type compartment_id: str

    :param name: The name to identify all created resources with.
    :type name: str

    :param image: An accessible OCIR Function image that can be invoked.
    :type image: str
    """
    identity_client = identity.IdentityClient(oci_cfg)
    network_client = core.VirtualNetworkClient(oci_cfg)
    fn_management_client = functions.FunctionsManagementClient(oci_cfg)

    print("setup_resources")

    #  1. A VCN is required to host subnets.
    vcn_display_name = vcn_name(name)
    vcn_cidr_block = "10.0.0.0/16"
    vcn = create_vcn(network_client, compartment_id, vcn_display_name, vcn_cidr_block)

    # 2. An Internet Gateway is required to enable the VCN to talk to the wider world.
    ig_display_name = ig_name(name)
    ig = create_ig(network_client, compartment_id, vcn.id, ig_display_name)

    # 3. We must configure the VCN's traffic to be routed through the Internet Gateway.
    drt_display_name = drt_name(name)
    configure_ig(network_client, compartment_id,  vcn.id, ig.id, drt_display_name)

    # 4. To create subnets we need to place them in a valid 'Availability Domain' for 
    # our 'Region'.
    ad = get_availability_domains(identity_client, compartment_id)[0]
    print("Using AD: ", ad.name)

    # 5. A subnet is required to expose and be able invoke the function.
    # In multiple AD regions, subnets can be created in multiple ADs to provide
    # redundency.
    subnet_display_name = subnet_name(name)
    subnet_cidr_block = "10.0.0.0/24"
    subnet = create_subnet(network_client, 
        compartment_id, vcn.id, subnet_display_name, ad.name, subnet_cidr_block
    )
    
    # 6. Create an Application to host and manage the function(s).
    app_display_name = application_name(name)
    subnet_ids = [subnet.id]
    app = create_application(fn_management_client, compartment_id, app_display_name, subnet_ids)

    # 7. Create a single Function, set its execution image and limits.
    fn_display_name = function_name(name)
    memory_in_mbs = 128
    timeout_in_seconds = 30
    fn = create_function(fn_management_client, 
        app.id, fn_display_name, image, memory_in_mbs, timeout_in_seconds)

def invoke_function(oci_cfg, compartment_id, name, content: str):
    """
    Invoke a Function!

    :param compartment_id: The compartment_id in of the Function.
    :type compartment_id: str

    :param name: The Function name.
    :type name: str

    :param content: The data to send when invoking the Function.
    :type content: str
    """
    fn_management_client = functions.FunctionsManagementClient(oci_cfg)

    print("invoke_function")

    app = get_unique_application_by_name(
        fn_management_client, compartment_id, application_name(name))
    fn = get_unique_function_by_name(
        fn_management_client, app.id, function_name(name))

    # 8. Create an invocation client and invoke the Function!
    invoke_client = functions.FunctionsInvokeClient(
        oci_cfg, service_endpoint=fn.invoke_endpoint)
    resp = invoke_client.invoke_function(fn.id, content)
    print(resp.data.text)


def teardown_resources(oci_cfg, compartment_id, name: str):
    """
    Clean up all Function resources for this example.

    NB: If nay errors occur, please tidy up resources manually using the OCI console.

    :param compartment_id: The compartment_id in which to create the resources.
    :type compartment_id: str

    :param name: The name to identify all created resources with.
    :type name: str
    """
    network_client = core.VirtualNetworkClient(oci_cfg)
    identity_client = identity.IdentityClient(oci_cfg)
    fn_management_client = functions.FunctionsManagementClient(oci_cfg)

    print("teardown_resources")

    vcn = get_unique_vcn_by_name(
        network_client, compartment_id, vcn_name(name))
    ig = get_unique_ig_by_name(
        network_client, compartment_id, vcn.id, ig_name(name))
    rt = get_unique_route_table_by_name(
        network_client, compartment_id, vcn.id, drt_name(name))
    sn = get_unique_subnet_by_name(
        network_client, compartment_id, vcn.id, subnet_name(name))
    app = get_unique_application_by_name(
        fn_management_client, compartment_id, application_name(name))
    fn = get_unique_function_by_name(
        fn_management_client, app.id, function_name(name))

    if fn is not None:
        delete_function(fn_management_client, fn.id)

    if app is not None:
        delete_application(fn_management_client, app.id)

    if sn is not None:
        delete_subnet(network_client, sn.id)

    if rt is not None:
        prepare_route_table_for_delete(network_client, rt.id)  

    if ig is not None:
        delete_ig(network_client, ig.id)
    
    if vcn is not None:
        delete_vcn(network_client, vcn.id)

    return

#  === Identity Helpers ===

def get_compartment_id(oci_cfg, compartment_name: str) -> identity_models.Compartment:
    """
    Get the compartment_id by name for the configured tenancy.

    :param oci_cfg: OCI auth config
    :param compartment_name: OCI tenancy compartment name

    :return: OCI tenancy compartment.
    :rtype: str
    """
    identity_client = identity.IdentityClient(oci_cfg)
    result = pagination.list_call_get_all_results(
        identity_client.list_compartments,
        cfg["tenancy"],
        compartment_id_in_subtree=True,
        access_level="ACCESSIBLE",
    )
    for c in result.data:
        if compartment_name == c.name:
            return c
    raise Exception("Compartment not found.")

def get_availability_domains(identity_client, compartment_id: str) -> [identity_models.AvailabilityDomain]:
    """
    Gets the list of AvailabilityDomain for the specified compartment.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment to check.
    :type compartment_id: str

    :return: The AvailabilityDomains
    :rtype: [identity_models.AvailabilityDomain]
    """
    result = pagination.list_call_get_all_results(
        identity_client.list_availability_domains,
        compartment_id
    )
    return result.data


#  === Vcn Helpers ===

def create_vcn(network_client, compartment_id, display_name, cidr_block) -> core_models.Vcn:
    """
    Creates a Vcn and waits for it to become available to use.

    :param network_client: OCI VirtualNetworkClient client.
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the Vcn.
    :type compartment_id: str

    :param display_name: The display name of the Vcn.
    :type display_name: str

    :param cidr_block: The CIDR range of the Vcn.
    :type cidr_block: str

    :return: The Vcn.
    :rtype: core_models.Vcn
    """
    create_vcn_details = core_models.CreateVcnDetails(compartment_id=compartment_id, display_name=display_name, cidr_block=cidr_block)
    result = network_client.create_vcn(create_vcn_details)
    get_vcn_response = oci.wait_until(
        network_client,
        network_client.get_vcn(result.data.id),
        'lifecycle_state',
        'AVAILABLE'
    )
    print('Created Vcn: {}'.format(result.data.display_name))
    return result.data

def get_unique_vcn_by_name(network_client, compartment_id, display_name) -> core_models.Vcn:
    """
    Find a unique Vcn by name.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the Vcn.
    :type compartment_id: str

    :param display_name: The display name of the Vcn.
    :type display_name: str

    :return: The Vcn
    :rtype: core_models.Vcn
    """
    result = pagination.list_call_get_all_results(
        network_client.list_vcns,
        compartment_id,
        display_name=display_name
    )
    for vcn in result.data:
        if display_name == vcn.display_name:
            return vcn
    raise Exception("Vcn not found")

def delete_vcn(network_client, vcn_id):
    """
    Deletes a Vcn and waits for it to be deleted.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param vcn_id: The Vcn to delete.
    :type vcn_id: str
    """
    network_client.delete_vcn(vcn_id)
    # get_vcn_response = oci.wait_until(
    #     network_client,
    #     network_client.get_vcn(vcn_id),
    #     'lifecycle_state',
    #     'TERMINATED',
    #     succeed_on_not_found=True
    # )
    print('Delete VCN: {}'.format(vcn_id))


#  === OCI Internet Gateway Helpers ===

def create_ig(network_client, compartment_id, vcn_id, display_name) -> core_models.InternetGateway:
    """
    Creates a InternetGateway in a Vcn and waits for it to become available to use.

    :param network_client: OCI VirtualNetworkClient client.
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the Vcn.
    :type compartment_id: str

    :param vcn_id: The OCID of the Vcn which will own the InternetGateway.
    :type vcn_id: str

    :param display_name: The display name of the InternetGateway.
    :type display_name: str

    :return: The InternetGateway.
    :rtype: core_models.InternetGateway
    """
    create_ig_details = core_models.CreateInternetGatewayDetails(
        compartment_id=compartment_id, vcn_id=vcn_id, display_name=display_name, is_enabled=True
    )
    result = network_client.create_internet_gateway(create_ig_details)
    get_vcn_response = oci.wait_until(
        network_client,
        network_client.get_internet_gateway(result.data.id),
        'lifecycle_state',
        'AVAILABLE'
    )
    print('Created Internet Gateway: {}'.format(result.data.display_name))
    return result.data

def get_unique_ig_by_name(network_client, compartment_id, vcn_id, display_name) -> core_models.InternetGateway:
    """
    Find a unique InternetGateway by name.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the Vcn.
    :type compartment_id: str

    :param vcn_id: The OCID of the Vcn which will own the InternetGateway.
    :type vcn_id: str

    :param display_name: The display name of the InternetGateway.
    :type display_name: str

    :return: The InternetGateway
    :rtype: core_models.InternetGateway
    """
    result = pagination.list_call_get_all_results(
        network_client.list_internet_gateways,
        compartment_id,
        vcn_id,
        display_name=display_name
    )
    for ig in result.data:
        if display_name == ig.display_name:
            return ig
    raise Exception("InternetGateway not found")

def delete_ig(network_client, ig_id):
    """
    Deletes an InternetGateway and waits for it to be deleted.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param ig_id: The InternetGateway to delete.
    :type ig_id: str
    """
    network_client.delete_internet_gateway(ig_id)
    # get_ig_response = oci.wait_until(
    #     network_client,
    #     network_client.get_internet_gateway(ig_id),
    #     'lifecycle_state',
    #     'TERMINATED',
    #     succeed_on_not_found=True
    # )
    print('Delete Internet Gateway: {}'.format(ig_id))

def configure_ig(network_client, compartment_id, vcn_id, ig_id, display_name):
    """
    Configures a Vcn's default RoutingTable to add a RouteRule that provides 
    Internet access via the specified InternetGateway.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the Vcn.
    :type compartment_id: str

    :param vcn_id: The OCID of the Vcn which will own the subnet.
    :type vcn_id: str

    :param ig_id: The OCID of the Vcn which will own the subnet.
    :type ig_id: str

    :param display_name: The display name of the RoutingTable to configure.
    :type display_name: str
    """
    # Get the default route table for the Vcn.
    rt = get_unique_route_table_by_name(network_client, compartment_id, vcn_id, display_name)
    # Create a global access routing rule.
    destination_cidr="0.0.0.0/0"
    access = core_models.RouteRule(
        cidr_block=destination_cidr, destination=destination_cidr, destination_type="CIDR_BLOCK",
        network_entity_id=ig_id
    )
    route_rules = rt.route_rules 
    route_rules.append(access)
    # Update the route table with the new access rule.
    update = core_models.UpdateRouteTableDetails(route_rules=route_rules)
    network_client.update_route_table(rt.id, update)
    print('Configured Internet Gateway Default Route Table Rules: {}'.format(display_name)) 


# === OCI RouteTable Helpers ===

def get_unique_route_table_by_name(network_client, compartment_id, vcn_id, display_name) -> core_models.RouteTable:
    """
    Find a unique RouteTable by name.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the RouteTable.
    :type compartment_id: str

    :param vcn_id: The OCID of the Vcn which will own the RouteTable.
    :type vcn_id: str

    :param display_name: The display name of the RouteTable.
    :type display_name: str

    :return: The RouteTable.
    :rtype: core_models.RouteTable
    """
    result = pagination.list_call_get_all_results(
        network_client.list_route_tables,
        compartment_id,
        vcn_id,
        display_name=display_name
    )
    for rt in result.data:
        if display_name == rt.display_name:
            return rt
    raise Exception("RouteTable not found")

def prepare_route_table_for_delete(network_client, rt_id):
    """
    Prepares a DefaultRouteTable for deletion by deleting all RouteRules.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param rt_id: The OCID of the RouteTable to clean.
    :type rt_id: str
    """
    update = core_models.UpdateRouteTableDetails(route_rules=[])
    network_client.update_route_table(rt_id, update)
    print('Cleaned Default Route Table Rules: {}'.format(rt_id))


# === OCI Subnet Helpers ===

def create_subnet(network_client, compartment_id, vcn_id, display_name, ad_name, cidr_block) -> core_models.Subnet:
    """
    Creates a Subnet in a Vcn and waits for the Subnet to become available to use.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the Subnet.
    :type compartment_id: str

    :param vcn_id: The OCID of the VCN which will own the Subnet.
    :type vcn_id: str

    :param display_name: The display name of the Subnet.
    :type display_name: str

    :param ad_name: The availability domain where the Subnet will be created.
    :type ad_name: str

    :param cidr_block: the Subnet CidrBlock allocated from the parent VCN range.
    :type cidr_block: str

    :return: The Subnet
    :rtype: core_models.Subnet
    """
    create_subnet_details = core_models.CreateSubnetDetails(
        compartment_id=compartment_id, vcn_id=vcn_id, availability_domain=ad_name, 
        display_name=display_name, cidr_block=cidr_block
    )
    result = network_client.create_subnet(create_subnet_details)
    get_subnet_response = oci.wait_until(
        network_client,
        network_client.get_subnet(result.data.id),
        'lifecycle_state',
        'AVAILABLE'
    )
    print('Created Subnet: {}'.format(result.data.display_name))
    return result.data

def get_unique_subnet_by_name(network_client, compartment_id, vcn_id, display_name) -> core_models.Subnet:
    """
    Find a unique Subnet by name.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param compartment_id: The OCID of the compartment which owns the VCN.
    :type compartment_id: str

    :param vcn_id: The OCID of the VCN which will own the subnet.
    :type vcn_id: str

    :param display_name: The display name of the subnet.
    :type display_name: str

    :return: The Subnet
    :rtype: core_models.Subnet
    """
    result = pagination.list_call_get_all_results(
        network_client.list_subnets,
        compartment_id,
        vcn_id,
        display_name=display_name
    )
    for subnet in result.data:
        if display_name == subnet.display_name:
            return subnet
    raise Exception("subnet not found")

def delete_subnet(network_client, subnet_id):
    """
    Deletes a subnet and waits for it to be deleted.

    :param network_client: OCI VirtualNetworkClient client
    :type network_client: oci.core.VirtualNetworkClient

    :param subnet_id: The subnet to delete.
    :type subnet_id: str
    """
    network_client.delete_subnet(subnet_id)
    # get_subnet_response = oci.wait_until(
    #     network_client,
    #     network_client.get_subnet(subnet_id),
    #     'lifecycle_state',
    #     'TERMINATED',
    #     succeed_on_not_found=True
    # )
    print('Delete Subnet: {}'.format(subnet_id))

# === Application Helpers ===

def create_application(fn_management_client, compartment_id, display_name, subnet_ids) -> fn_models.Application:
    """
    Creates an Application and waits for the it to become available to use.

    :param fn_management_client: OCI FunctionsManagementClient client
    :type fn_management_client: functions.FunctionsManagementClient

    :param compartment_id: The OCID of the compartment which owns the Application.
    :type compartment_id: str

    :param display_name: The display name of the Application.
    :type display_name: str

    :param subnet_ids: A List of subnets (in different ADs) that will expose the Application functions.
    :type subnet_ids: str

    :return: The Application
    :rtype: fn_models.Application
    """
    create_application_details = fn_models.CreateApplicationDetails(
        compartment_id=compartment_id, display_name=display_name, subnet_ids=subnet_ids
    )
    result = fn_management_client.create_application(create_application_details)
    get_app_response = oci.wait_until(
        fn_management_client,
        fn_management_client.get_application(result.data.id),
        'lifecycle_state',
        'ACTIVE'
    )
    print('Created Application: {}'.format(result.data.display_name))
    return result.data

def get_unique_application_by_name(fn_management_client, compartment_id, display_name) -> fn_models.Application:
    """
    Find a unique Application by name.

    :param fn_management_client: OCI FunctionsManagementClient client
    :type fn_management_client: functions.FunctionsManagementClient

    :param compartment_id: The OCID of the compartment which owns the Application.
    :type compartment_id: str

    :param display_name: The display name of the subnet.
    :type display_name: str

    :return: The Subnet
    :rtype: core_models.Subnet
    """
    result = pagination.list_call_get_all_results(
        fn_management_client.list_applications,
        compartment_id,
        display_name=display_name
    )
    for app in result.data:
        if display_name == app.display_name:
            return app
    raise Exception("Application not found")

def delete_application(fn_management_client, application_id):
    """
    Deletes a Application and waits for it to be deleted.

    :param fn_management_client: OCI FunctionsManagementClient client
    :type fn_management_client: functions.FunctionsManagementClient

    :param application_id: The Application to delete.
    :type application_id: str
    """
    fn_management_client.delete_application(application_id)
    # get_application_response = oci.wait_until(
    #     fn_management_client,
    #     fn_management_client.get_application(application_id),
    #     'lifecycle_state',
    #     'DELETED',
    #     succeed_on_not_found=True
    # )
    print('Delete Application: {}'.format(application_id))

# === Function Helpers ===

def create_function(fn_management_client, 
    application_id, display_name, image, memory_in_m_bs, timeout_in_seconds) -> fn_models.Function:
    """
    Creates a Function and waits for it to become available to use.

    :param fn_management_client: OCI FunctionsManagementClient client.
    :type fn_management_client: functions.FunctionsManagementClient

    :param application_id: The OCID of the Application which owns the Function.
    :type compartment_id: str

    :param display_name: The display name of the Function.
    :type display_name: str

    :param image: An accessible OCIR image implementing the function to be executed.
    :type image: str

    :param memory_in_m_bs: The maximum ammount of memory available (128, 256, 512, 1024) to the function in MB.
    :type image: int

    :param timeout_in_seconds: The maximum ammout of time a function can execute (30 - 120) in seconds.
    :type image: int

    :return: The Function.
    :rtype: fn_models.Function
    """
    create_function_details = fn_models.CreateFunctionDetails(
        application_id=application_id, display_name=display_name, 
        image=image, memory_in_m_bs=memory_in_m_bs, timeout_in_seconds=timeout_in_seconds
    )
    result = fn_management_client.create_function(create_function_details)
    get_fn_response = oci.wait_until(
        fn_management_client,
        fn_management_client.get_function(result.data.id),
        'lifecycle_state',
        'ACTIVE'
    )
    print('Created Function: {}'.format(result.data.display_name))
    return result.data

def get_unique_function_by_name(fn_management_client, application_id, display_name) -> fn_models.Function:
    """
    Find a unique Function by name.

    :param fn_management_client: OCI FunctionsManagementClient client.
    :type fn_management_client: functions.FunctionsManagementClient

    :param application_id: The OCID of the Application which owns the Function.
    :type application_id: str

    :param display_name: The display name of the Function.
    :type display_name: str

    :return: The Function.
    :rtype: core_models.Function
    """
    result = pagination.list_call_get_all_results(
        fn_management_client.list_functions,
        application_id,
        display_name=display_name
    )
    for fn in result.data:
        if display_name == fn.display_name:
            return fn
    raise Exception("Function not found.")

def delete_function(fn_management_client, function_id):
    """
    Deletes a Function and waits for it to be deleted.

    :param fn_management_client: OCI FunctionsManagementClient client
    :type fn_management_client: functions.FunctionsManagementClient

    :param function_id: The Function to delete.
    :type function_id: str
    """
    fn_management_client.delete_function(function_id)
    # get_function_response = oci.wait_until(
    #     fn_management_client,
    #     fn_management_client.get_function(function_id),
    #     'lifecycle_state',
    #     'DELETED',
    #     succeed_on_not_found=True
    # )
    print('Delete Function: {}'.format(function_id))

#  === Utility Helpers ===

def vcn_name(name: str) -> str:
    return name + "-vcn"

def ig_name(name: str) -> str:
    return name + "-ig" 

def drt_name(name: str) -> str:
    return "Default Route Table for " + name + "-vcn"

def subnet_name(name: str) -> str:
    return name + "-subnet"

def application_name(name: str) -> str:
    return name + "-app"  

def function_name(name: str) -> str:
    return name + "-fn"

#  === Main ===

if __name__ == "__main__":

    # All resources will be prefixed with this name.
    name = NAME_PREFIX

    # Load OCI credentials from default location and profile.
    cfg = config.from_file(
        file_location=os.getenv(
            "OCI_CONFIG_PATH", config.DEFAULT_LOCATION),
        profile_name=os.getenv(
            "OCI_CONFIG_PROFILE", config.DEFAULT_PROFILE)
    )
    config.validate_config(cfg)

    # All resources will be created in the specified compartment.
    compartment_name = os.environ.get('COMPARTMENT_NAME')
    if compartment_name is not None:
        compartment_id = get_compartment_id(cfg, compartment_name).id
    else:
        compartment_id = os.environ.get('COMPARTMENT_ID')
    if compartment_id is None:
        print("The COMPARTMENT_ID (or COMPARTMENT_NAME) environment variable must be set.")
        sys.exit(1)

    # We need an accessible image to invoke.
    # e.g. phx.ocir.io/tenancy-name/registry/imagename:version
    image = os.environ.get('OCIR_FN_IMAGE')

    # If the target image require input, it can be defined with CONTENT 
    # environment variable.
    content = os.environ.get('CONTENT')
    if content is None:
        content = ""

    # Handle debug options.
    if int(os.getenv("DEBUG", "0")) > 0:
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
        cfg.update({
            "log_requests": True
        })

    # Attempt to setup the minimal OCI resources for a Function.
    if SETUP in sys.argv:
        if image is None:
            print("The IMAGE environment variable must be set.")
            sys.exit(1)
        setup_resources(cfg, compartment_id, name, image)

    # Invoke a Function.
    if INVOKE in sys.argv:
        invoke_function(cfg, compartment_id, name, content)
    
    # Attempt to clean-up resources.
    if TEARDOWN in sys.argv:
        teardown_resources(cfg, compartment_id, name)
