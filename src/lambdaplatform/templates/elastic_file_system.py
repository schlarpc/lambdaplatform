from troposphere import GetAtt, Output, Parameter, Ref, Select, StackName, Template
from troposphere.ec2 import SecurityGroup
from troposphere.efs import AccessPoint, FileSystem, LifecyclePolicy, MountTarget, PosixUser


def create_template():
    template = Template(Description="EFS filesystem for Lambda usage")

    vpc_id = template.add_parameter(
        Parameter(
            "VpcId",
            Type="String",
        )
    )

    availability_zones = template.add_parameter(
        Parameter(
            "AvailabilityZones",
            Type="CommaDelimitedList",
        )
    )

    subnet_ids = template.add_parameter(
        Parameter(
            "SubnetIds",
            Type="CommaDelimitedList",
        )
    )

    file_system = template.add_resource(
        FileSystem(
            "FileSystem",
            AvailabilityZoneName=Select(0, Ref(availability_zones)),
            LifecyclePolicies=[
                LifecyclePolicy(
                    TransitionToIA="AFTER_14_DAYS",
                )
            ],
        )
    )

    security_group = template.add_resource(
        SecurityGroup(
            "SecurityGroup",
            GroupDescription=StackName,
            VpcId=Ref(vpc_id),
            SecurityGroupIngress=[
                {
                    "CidrIp": "0.0.0.0/0",
                    "IpProtocol": "tcp",
                    "FromPort": "2049",
                    "ToPort": "2049",
                }
            ],
        )
    )

    template.add_resource(
        MountTarget(
            "MountTarget0",
            FileSystemId=Ref(file_system),
            SecurityGroups=[
                Ref(security_group),
            ],
            SubnetId=Select(0, Ref(subnet_ids)),
        )
    )

    access_point = template.add_resource(
        AccessPoint(
            "AccessPoint",
            FileSystemId=Ref(file_system),
            PosixUser=PosixUser(
                Uid=str(0),
                Gid=str(0),
            ),
        )
    )

    template.add_output(
        Output(
            "AccessPointArn",
            Value=GetAtt(access_point, "Arn"),
        )
    )

    return template
