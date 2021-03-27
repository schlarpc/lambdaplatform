import inspect

from awacs import ec2, logs, sts
from awacs.aws import Allow, PolicyDocument, Principal, Statement
from troposphere import Equals, FindInMap, GetAtt, Join, Output, Parameter, Ref, Split, Template
from troposphere.awslambda import Code, Function, ImageConfig
from troposphere.cloudformation import CustomResource
from troposphere.iam import PolicyType, Role
from troposphere.logs import LogGroup

from ..tasks.availability_zones import handler
from . import common


def create_template():
    template = Template(Description="Stable availability zone discovery utility")

    deployment_id = template.add_parameter(
        Parameter(
            "DeploymentId",
            Type="String",
        )
    )

    image_uri = template.add_parameter(
        Parameter(
            "ImageUri",
            Type="String",
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
        )
    )

    function, alias = common.add_versioned_lambda(
        template,
        Ref(deployment_id),
        Function(
            "Function",
            MemorySize=256,
            Timeout=30,
            Role=GetAtt(role, "Arn"),
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
            RetentionInDays=common.LOG_RETENTION_DAYS,
        )
    )

    policy = template.add_resource(
        PolicyType(
            "Policy",
            PolicyName=Ref(role),
            PolicyDocument=PolicyDocument(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[logs.PutLogEvents, logs.CreateLogStream],
                        Resource=[GetAtt(log_group, "Arn")],
                    ),
                    Statement(
                        Effect=Allow,
                        Action=[ec2.DescribeAvailabilityZones],
                        Resource=["*"],
                    ),
                ],
            ),
            Roles=[Ref(role)],
        )
    )

    availability_zones = template.add_resource(
        CustomResource(
            "AvailabilityZones",
            ServiceToken=Ref(alias),
            DeploymentId=Ref(deployment_id),
            DependsOn=[policy],
        )
    )

    template.add_output(
        Output(
            "AvailabilityZones",
            Value=Ref(availability_zones),
        )
    )

    return template


if __name__ == "__main__":
    print(create_template().to_json())
