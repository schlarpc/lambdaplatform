import boto3

from . import common


def handler(event):
    with common.cloudformation_custom_resource(event) as resource:
        if event["RequestType"] in {"Create", "Update"}:
            ecr = boto3.client("ecr")
            response = ecr.batch_get_image(
                repositoryName=event["ResourceProperties"]["RepositoryName"],
                imageIds=[
                    {
                        "imageDigest": event["ResourceProperties"]["ImageDigest"],
                    }
                ],
            )
            try:
                ecr.put_image(
                    repositoryName=event["ResourceProperties"]["RepositoryName"],
                    imageTag=event["ResourceProperties"]["ImageTag"],
                    imageManifest=response["images"][0]["imageManifest"],
                )
            except ecr.exceptions.ImageAlreadyExistsException:
                pass
            resource["PhysicalResourceId"] = "@".join(
                (
                    event["ResourceProperties"]["ImageTag"],
                    event["ResourceProperties"]["ImageDigest"],
                )
            )
        # TODO is it worth handling delete?
