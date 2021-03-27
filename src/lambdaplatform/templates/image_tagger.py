import inspect

from awacs import ecr, logs, sts
from awacs.aws import Allow, PolicyDocument, Principal, Statement
from troposphere import Equals, FindInMap, GetAtt, Join, Output, Parameter, Ref, Split, Template
from troposphere.awslambda import Code, Function, ImageConfig
from troposphere.cloudformation import CustomResource
from troposphere.iam import PolicyType, Role
from troposphere.logs import LogGroup

from ..tasks.image_tagger import handler
from . import common


def create_template():
    template = Template(Description="ECR image tagger utility")

    deployment_id = template.add_parameter(
        Parameter(
            "DeploymentId",
            Type="String",
        )
    )

    artifact_repository = template.add_parameter(
        Parameter(
            "ArtifactRepository",
            Type="String",
        )
    )

    image_digest = template.add_parameter(
        Parameter(
            "ImageDigest",
            Type="String",
        )
    )

    desired_image_tag = template.add_parameter(
        Parameter(
            "DesiredImageTag",
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
                        Action=[ecr.BatchGetImage, ecr.PutImage],
                        # TODO scope down
                        Resource=["*"],
                    ),
                ],
            ),
            Roles=[Ref(role)],
        )
    )

    template.add_resource(
        CustomResource(
            "ImageTag",
            ServiceToken=Ref(alias),
            DeploymentId=Ref(deployment_id),
            RepositoryName=Ref(artifact_repository),
            ImageDigest=Ref(image_digest),
            ImageTag=Ref(desired_image_tag),
            DependsOn=[policy],
        )
    )

    return template
