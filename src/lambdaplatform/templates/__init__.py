import argparse
import itertools
import json
import pathlib

from troposphere import (
    AccountId,
    Equals,
    GetAtt,
    Join,
    Not,
    Output,
    Parameter,
    Partition,
    Ref,
    Region,
    StackName,
    Template,
    URLSuffix,
)
from troposphere.cloudformation import Stack
from troposphere.ecr import LifecyclePolicy, Repository
from troposphere.s3 import (
    AbortIncompleteMultipartUpload,
    Bucket,
    BucketEncryption,
    LifecycleConfiguration,
    LifecycleRule,
    PublicAccessBlockConfiguration,
    ServerSideEncryptionByDefault,
    ServerSideEncryptionRule,
)

from . import (
    availability_zones,
    common,
    deployment_id,
    elastic_file_system,
    image_tagger,
    lambda_eip_allocator,
    lambda_function,
    vpc,
)


def create_primary_template():
    template = Template(Description="Root stack for VERY STRONG Lambda function")

    image_digest = template.add_parameter(Parameter("ImageDigest", Type="String", Default=""))

    is_image_digest_defined = "IsImageDigestDefined"
    template.add_condition(is_image_digest_defined, Not(Equals(Ref(image_digest), "")))

    artifact_repository = template.add_resource(
        Repository(
            "ArtifactRepository",
            ImageTagMutability="MUTABLE",
            LifecyclePolicy=LifecyclePolicy(
                LifecyclePolicyText=json.dumps(
                    {
                        "rules": [
                            {
                                "rulePriority": 1,
                                "selection": {
                                    "tagStatus": "untagged",
                                    "countType": "imageCountMoreThan",
                                    "countNumber": 3,
                                },
                                "action": {
                                    "type": "expire",
                                },
                            }
                        ]
                    },
                    indent=None,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        )
    )

    artifact_repository_url = Join(
        "/",
        [
            Join(
                ".",
                [
                    AccountId,
                    "dkr",
                    "ecr",
                    Region,
                    URLSuffix,
                ],
            ),
            Ref(artifact_repository),
        ],
    )
    image_uri = Join("@", [artifact_repository_url, Ref(image_digest)])

    artifact_bucket = template.add_resource(
        Bucket(
            "ArtifactBucket",
            BucketEncryption=BucketEncryption(
                ServerSideEncryptionConfiguration=[
                    ServerSideEncryptionRule(
                        BucketKeyEnabled=True,
                        ServerSideEncryptionByDefault=ServerSideEncryptionByDefault(
                            SSEAlgorithm="aws:kms",
                            KMSMasterKeyID=Join(
                                ":", ["arn", Partition, "kms", Region, AccountId, "alias/aws/s3"]
                            ),
                        ),
                    )
                ],
            ),
            LifecycleConfiguration=LifecycleConfiguration(
                Rules=[
                    LifecycleRule(
                        AbortIncompleteMultipartUpload=AbortIncompleteMultipartUpload(
                            DaysAfterInitiation=3,
                        ),
                        Status="Enabled",
                    ),
                ],
            ),
            PublicAccessBlockConfiguration=PublicAccessBlockConfiguration(
                BlockPublicAcls=True,
                BlockPublicPolicy=True,
                IgnorePublicAcls=True,
                RestrictPublicBuckets=True,
            ),
        )
    )

    deployment_id_stack = template.add_resource(
        Stack(
            "DeploymentId",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), deployment_id.create_template()
            ),
            Parameters={
                "ArtifactBucket": Ref(artifact_bucket),
            },
            Condition=is_image_digest_defined,
        )
    )

    availability_zones_stack = template.add_resource(
        Stack(
            "AvailabilityZones",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), availability_zones.create_template()
            ),
            Parameters={
                "DeploymentId": GetAtt(deployment_id_stack, "Outputs.Value"),
                "ImageUri": image_uri,
            },
            Condition=is_image_digest_defined,
        )
    )

    vpc_stack = template.add_resource(
        Stack(
            "Vpc",
            TemplateURL=common.get_template_s3_url(Ref(artifact_bucket), vpc.create_template()),
            Parameters={
                "AvailabilityZones": GetAtt(availability_zones_stack, "Outputs.AvailabilityZones"),
            },
            Condition=is_image_digest_defined,
        )
    )

    lambda_eip_allocator_stack = template.add_resource(
        Stack(
            "LambdaEipAllocator",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), lambda_eip_allocator.create_template()
            ),
            Parameters={
                "DeploymentId": GetAtt(deployment_id_stack, "Outputs.Value"),
                "VpcId": GetAtt(vpc_stack, "Outputs.VpcId"),
                "ImageUri": image_uri,
            },
            Condition=is_image_digest_defined,
        )
    )

    elastic_file_system_stack = template.add_resource(
        Stack(
            "ElasticFileSystem",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), elastic_file_system.create_template()
            ),
            Parameters={
                "VpcId": GetAtt(vpc_stack, "Outputs.VpcId"),
                "SubnetIds": GetAtt(vpc_stack, "Outputs.SubnetIds"),
                "AvailabilityZones": GetAtt(availability_zones_stack, "Outputs.AvailabilityZones"),
            },
            Condition=is_image_digest_defined,
        )
    )

    lambda_function_stack = template.add_resource(
        Stack(
            "LambdaFunction",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), lambda_function.create_template()
            ),
            Parameters={
                "DeploymentId": GetAtt(deployment_id_stack, "Outputs.Value"),
                "VpcId": GetAtt(vpc_stack, "Outputs.VpcId"),
                "SubnetIds": GetAtt(vpc_stack, "Outputs.SubnetIds"),
                "FileSystemAccessPointArn": GetAtt(
                    elastic_file_system_stack, "Outputs.AccessPointArn"
                ),
                "ImageUri": image_uri,
            },
            DependsOn=[lambda_eip_allocator_stack],
            Condition=is_image_digest_defined,
        )
    )

    image_tagger_stack = template.add_resource(
        Stack(
            "ImageTagger",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), image_tagger.create_template()
            ),
            Parameters={
                "DeploymentId": GetAtt(deployment_id_stack, "Outputs.Value"),
                "ArtifactRepository": Ref(artifact_repository),
                "DesiredImageTag": "current-cloudformation",
                "ImageDigest": Ref(image_digest),
                "ImageUri": image_uri,
            },
            DependsOn=list(template.resources),
            Condition=is_image_digest_defined,
        )
    )

    template.add_output(
        Output(
            "ArtifactBucket",
            Value=Ref(artifact_bucket),
        )
    )

    template.add_output(
        Output(
            "ArtifactRepositoryUrl",
            Value=artifact_repository_url,
        )
    )

    return template


def get_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path(".") / "templates")
    return parser.parse_args(argv)


def main():
    args = get_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    primary_template = [
        (
            "primary.json",
            common.template_to_json(create_primary_template()).encode("utf-8"),
        )
    ]
    for filename, content in itertools.chain(primary_template, common.template_registry.items()):
        with (args.output_dir / filename).open("wb") as f:
            f.write(content)
