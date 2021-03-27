from troposphere import (
    Cidr,
    GetAtt,
    Output,
    Parameter,
    Ref,
    Select,
    Split,
    StackName,
    Tags,
    Template,
)
from troposphere.ec2 import (
    VPC,
    DHCPOptions,
    InternetGateway,
    Route,
    RouteTable,
    Subnet,
    SubnetRouteTableAssociation,
    VPCDHCPOptionsAssociation,
    VPCGatewayAttachment,
)


def create_template():
    template = Template(Description="Simple public VPC")

    availability_zones = template.add_parameter(
        Parameter(
            "AvailabilityZones",
            Type="String",
        )
    )

    vpc = template.add_resource(
        VPC(
            "Vpc",
            CidrBlock="10.10.0.0/16",
            EnableDnsHostnames=False,
            EnableDnsSupport=True,
            Tags=Tags(Name=StackName),
        )
    )

    dhcp_options = template.add_resource(
        DHCPOptions(
            "DhcpOptions",
            NtpServers=["169.254.169.123"],
            DomainNameServers=["AmazonProvidedDNS"],
            Tags=Tags(Name=StackName),
        )
    )

    template.add_resource(
        VPCDHCPOptionsAssociation(
            "VpcDhcpOptionsAssociation",
            VpcId=Ref(vpc),
            DhcpOptionsId=Ref(dhcp_options),
        )
    )

    internet_gateway = template.add_resource(
        InternetGateway(
            "InternetGateway",
            Tags=Tags(Name=StackName),
        )
    )

    vpc_gateway_attachment = template.add_resource(
        VPCGatewayAttachment(
            "VpcGatewayAttachment",
            VpcId=Ref(vpc),
            InternetGatewayId=Ref(internet_gateway),
        )
    )

    subnet = template.add_resource(
        Subnet(
            "Subnet0",
            MapPublicIpOnLaunch=True,
            VpcId=Ref(vpc),
            CidrBlock=Select(0, Cidr(GetAtt(vpc, "CidrBlock"), 8, 8)),
            AvailabilityZone=Select(0, Split(",", Ref(availability_zones))),
            Tags=Tags(Name=StackName),
        )
    )

    route_table = template.add_resource(
        RouteTable(
            "RouteTable0",
            VpcId=Ref(vpc),
            Tags=Tags(Name=StackName),
        )
    )

    internet_route = template.add_resource(
        Route(
            "InternetRoute0",
            DestinationCidrBlock="0.0.0.0/0",
            GatewayId=Ref(internet_gateway),
            RouteTableId=Ref(route_table),
            DependsOn=[vpc_gateway_attachment],
        )
    )

    template.add_resource(
        SubnetRouteTableAssociation(
            "SubnetRouteTableAssocation0",
            RouteTableId=Ref(route_table),
            SubnetId=Ref(subnet),
        )
    )

    template.add_output(
        Output(
            "VpcId",
            Value=Ref(vpc),
        )
    )

    template.add_output(
        Output(
            "SubnetIds",
            Value=Ref(subnet),
        )
    )

    return template
