import argparse
import base64
import json
import os
import pathlib
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

import boto3


def env_default(name, *, prefix=__package__.upper(), environment=os.environ):
    env_key = f"{prefix}_{name}"
    if env_key in environment:
        return {"required": False, "default": environment[env_key]}
    return {"required": True}


def get_args():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--region", help="AWS region to use")
    parser.add_argument("--profile", help="Use a specific profile from your AWS configuration file")
    parser.add_argument(
        "--template-path",
        help="Directory of hash-addressed CloudFormation templates",
        type=pathlib.Path,
        **env_default("TEMPLATE_PATH"),
    )
    parser.add_argument(
        "--primary-template-path",
        help="Path to CloudFormation template used for root stack",
        type=pathlib.Path,
        **env_default("PRIMARY_TEMPLATE_PATH"),
    )
    parser.add_argument(
        "--image-generator",
        help="Executable that outputs a container image tarball on stdout",
        type=pathlib.Path,
        **env_default("IMAGE_GENERATOR"),
    )
    return parser.parse_args()


def create_session(region: Optional[str], profile: Optional[str]) -> boto3.Session:
    session_kwargs = {}
    if region is not None:
        session_kwargs["region_name"] = region
    if profile is not None:
        session_kwargs["profile_name"] = profile
    return boto3.Session(**session_kwargs)


def stack_exists(cloudformation, stack_name: str) -> bool:
    try:
        response = cloudformation.describe_stacks(StackName=stack_name)
        return bool(response["Stacks"])
    except cloudformation.exceptions.ClientError as ex:
        return False


def get_stack_outputs(cloudformation, stack_name: str) -> Dict[str, str]:
    try:
        response = cloudformation.describe_stacks(StackName=stack_name)
        for stack in response["Stacks"]:
            return {output["OutputKey"]: output["OutputValue"] for output in stack["Outputs"]}
    except cloudformation.exceptions.ClientError as ex:
        pass
    raise Exception(f"Stack {stack_name!r} not found")


def get_ecr_credentials(ecr) -> Tuple[str, str]:
    response = ecr.get_authorization_token()
    for auth_data in response["authorizationData"]:
        return base64.b64decode(auth_data["authorizationToken"]).decode("utf-8").split(":", 1)
    raise Exception("Credentials not found")


def run_subprocess(args):
    return subprocess.run(args, stdout=subprocess.PIPE, encoding="utf-8", check=True)


def main():
    args = get_args()
    session = create_session(args.region, args.profile)

    cloudformation = session.client("cloudformation")
    if not stack_exists(cloudformation, args.stack_name):
        print("Creating CloudFormation stack to bootstrap")
        with args.primary_template_path.open("r") as f:
            response = cloudformation.create_stack(
                StackName=args.stack_name,
                TemplateBody=f.read(),
                Capabilities=["CAPABILITY_IAM"],
                OnFailure="DELETE",
            )
        print("Waiting for stack creation to complete")
        cloudformation.get_waiter("stack_create_complete").wait(StackName=response["StackId"])
    outputs = get_stack_outputs(cloudformation, args.stack_name)

    s3 = session.resource("s3")
    bucket = s3.Bucket(outputs["ArtifactBucket"])
    print(f"Uploading templates to s3://{bucket.name}")
    for path_entry in args.template_path.glob("**/*"):
        if path_entry.is_file():
            with path_entry.open("rb") as f:
                key = str(path_entry.relative_to(args.template_path))
                print("*", key)
                bucket.Object(key).upload_fileobj(f)

    ecr = session.client("ecr")
    with tempfile.TemporaryDirectory(prefix=f"{__package__}.") as temp_dir:
        temp_path = pathlib.Path(temp_dir)

        print("Generating container image")
        image_path = (temp_path / "image.tar").resolve()
        with image_path.open("wb") as f:
            subprocess.run([args.image_generator], stdout=f, stderr=subprocess.PIPE, check=True)

        print("Packing container image")
        canonical_image_path = (temp_path / "canonical-image").resolve()
        run_subprocess(
            [
                "skopeo",
                "copy",
                f"docker-archive:{image_path}",
                f"dir:{canonical_image_path}",
                "--insecure-policy",
                "--dest-compress",
            ]
        )

        process = run_subprocess(
            [
                "skopeo",
                "inspect",
                f"dir:{canonical_image_path}",
            ]
        )
        image_digest = json.loads(process.stdout)["Digest"]

        print(f"Uploading container image to docker://{outputs['ArtifactRepositoryUrl']}")
        print("*", image_digest)
        username, password = get_ecr_credentials(ecr)
        run_subprocess(
            [
                "skopeo",
                "copy",
                f"dir:{canonical_image_path}",
                f"docker://{outputs['ArtifactRepositoryUrl']}:latest",
                "--insecure-policy",
                "--dest-creds",
                f"{username}:{password}",
            ]
        )

    print("Updating CloudFormation stack")
    s3_artifact_path = args.primary_template_path.relative_to(args.template_path)
    response = cloudformation.update_stack(
        StackName=args.stack_name,
        TemplateURL=f"https://{outputs['ArtifactBucket']}.s3.amazonaws.com/{s3_artifact_path}",
        Parameters=[
            {
                "ParameterKey": "ImageDigest",
                "ParameterValue": image_digest,
            }
        ],
        Capabilities=["CAPABILITY_IAM"],
    )
    print("Waiting for stack update to complete")
    cloudformation.get_waiter("stack_update_complete").wait(StackName=response["StackId"])


if __name__ == "__main__":
    main()
