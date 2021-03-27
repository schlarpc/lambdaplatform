import inspect

from awacs import ec2, logs, sts
from awacs.aws import Allow, PolicyDocument, Principal, Statement
from troposphere import (
    Condition,
    Equals,
    GetAtt,
    If,
    Join,
    Output,
    Parameter,
    Ref,
    StackName,
    Template,
)
from troposphere.awslambda import (
    Alias,
    Code,
    Environment,
    FileSystemConfig,
    Function,
    ImageConfig,
    Version,
    VPCConfig,
)
from troposphere.ec2 import SecurityGroup
from troposphere.iam import Policy, PolicyType, Role
from troposphere.logs import LogGroup

from ..tasks.lambda_function import handler
from . import common


def create_template():
    template = Template(Description="User-defined code")

    deployment_id = template.add_parameter(
        Parameter(
            "DeploymentId",
            Type="String",
        )
    )

    vpc_id = template.add_parameter(
        Parameter(
            "VpcId",
            Type="String",
        )
    )

    subnet_ids = template.add_parameter(
        Parameter(
            "SubnetIds",
            Type="CommaDelimitedList",
        )
    )

    file_system_access_point_arn = template.add_parameter(
        Parameter(
            "FileSystemAccessPointArn",
            Type="String",
        )
    )

    image_uri = template.add_parameter(
        Parameter(
            "ImageUri",
            Type="String",
        )
    )

    security_group = template.add_resource(
        SecurityGroup(
            "SecurityGroup",
            GroupDescription=StackName,
            VpcId=Ref(vpc_id),
        )
    )

    role = template.add_resource(
        Role(
            "Role",
            AssumeRolePolicyDocument=PolicyDocument(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[sts.AssumeRole],
                        Principal=Principal("Service", "lambda.amazonaws.com"),
                    ),
                ],
            ),
            Policies=[
                Policy(
                    PolicyName="vpc-access",
                    PolicyDocument=PolicyDocument(
                        Version="2012-10-17",
                        Statement=[
                            Statement(
                                Effect=Allow,
                                Action=[
                                    ec2.CreateNetworkInterface,
                                    ec2.DescribeNetworkInterfaces,
                                    ec2.DeleteNetworkInterface,
                                    ec2.AssignPrivateIpAddresses,
                                    ec2.UnassignPrivateIpAddresses,
                                ],
                                Resource=["*"],
                            ),
                        ],
                    ),
                ),
            ],
        )
    )

    function, alias = common.add_versioned_lambda(
        template,
        Ref(deployment_id),
        Function(
            "Function",
            MemorySize=256,
            Role=GetAtt(role, "Arn"),
            VpcConfig=VPCConfig(
                SecurityGroupIds=[Ref(security_group)],
                SubnetIds=Ref(subnet_ids),
            ),
            FileSystemConfigs=[
                FileSystemConfig(
                    Arn=Ref(file_system_access_point_arn),
                    LocalMountPath="/mnt/storage",
                ),
            ],
            PackageType="Image",
            Code=Code(
                ImageUri=Ref(image_uri),
            ),
            ImageConfig=ImageConfig(
                Command=[
                    Join(":", (handler.__module__, handler.__name__)),
                ],
            ),
        ),
    )

    log_group = template.add_resource(
        LogGroup(
            "LogGroup",
            LogGroupName=Join("/", ["/aws/lambda", Ref(function)]),
            RetentionInDays=7,
        )
    )

    policy = template.add_resource(
        PolicyType(
            "Policy",
            PolicyName=Ref(function),
            PolicyDocument=PolicyDocument(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Resource=GetAtt(log_group, "Arn"),
                        Action=[logs.CreateLogStream, logs.PutLogEvents],
                    ),
                ],
            ),
            Roles=[Ref(role)],
        )
    )

    template.add_output(
        Output(
            "FunctionAliasArn",
            Value=Ref(alias),
        )
    )

    return template
