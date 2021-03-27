import inspect

from awacs import ec2, logs, sts
from awacs.aws import Allow, PolicyDocument, Principal, Statement
from troposphere import (
    AccountId,
    Equals,
    FindInMap,
    GetAtt,
    Join,
    Output,
    Parameter,
    Partition,
    Ref,
    Region,
    Split,
    Template,
)
from troposphere.awslambda import Code, Function, ImageConfig, Permission
from troposphere.events import Rule, Target
from troposphere.iam import PolicyType, Role
from troposphere.logs import LogGroup

from ..tasks.lambda_eip_allocator import handler
from . import common


def create_template():
    template = Template(Description="Lambda VPC interface IP allocator utility")

    vpc_id = template.add_parameter(Parameter("VpcId", Type="String"))

    image_uri = template.add_parameter(
        Parameter(
            "ImageUri",
            Type="String",
        )
    )

    deployment_id = template.add_parameter(
        Parameter(
            "DeploymentId",
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
            "FunctionLogs",
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
                    # TODO scope down
                    Statement(
                        Effect=Allow,
                        Action=[
                            ec2.AllocateAddress,
                            ec2.ReleaseAddress,
                            ec2.AssociateAddress,
                            ec2.CreateTags,
                        ],
                        Resource=[Join(":", ["arn", Partition, "ec2", Region, AccountId, "*"])],
                    ),
                    Statement(
                        Effect=Allow,
                        Action=[
                            ec2.DescribeAddresses,
                        ],
                        Resource=["*"],
                    ),
                ],
            ),
            Roles=[Ref(role)],
        )
    )

    rule_create = template.add_resource(
        Rule(
            "RuleCreate",
            EventPattern={
                "source": ["aws.ec2"],
                "detail-type": ["AWS API Call via CloudTrail"],
                "detail": {
                    "eventSource": ["ec2.amazonaws.com"],
                    "eventName": ["CreateNetworkInterface"],
                    "responseElements": {
                        "networkInterface": {
                            "vpcId": [Ref(vpc_id)],
                            "description": [{"prefix": "AWS Lambda VPC ENI"}],
                        },
                    },
                    "errorCode": [{"exists": False}],
                },
            },
            Targets=[
                Target(
                    Id="default",
                    Arn=Ref(alias),
                ),
            ],
            DependsOn=[policy],
        )
    )

    template.add_resource(
        Permission(
            "PermissionCreate",
            Principal="events.amazonaws.com",
            Action="lambda:InvokeFunction",
            FunctionName=Ref(alias),
            SourceArn=GetAtt(rule_create, "Arn"),
        )
    )

    rule_delete = template.add_resource(
        Rule(
            "RuleDelete",
            EventPattern={
                "source": ["aws.ec2"],
                "detail-type": ["AWS API Call via CloudTrail"],
                "detail": {
                    "eventSource": ["ec2.amazonaws.com"],
                    "eventName": ["DeleteNetworkInterface"],
                    "errorCode": [{"exists": False}],
                },
            },
            Targets=[
                Target(
                    Id="default",
                    Arn=Ref(alias),
                ),
            ],
            DependsOn=[policy],
        )
    )

    template.add_resource(
        Permission(
            "PermissionDelete",
            Principal="events.amazonaws.com",
            Action="lambda:InvokeFunction",
            FunctionName=Ref(alias),
            SourceArn=GetAtt(rule_delete, "Arn"),
        )
    )

    return template
