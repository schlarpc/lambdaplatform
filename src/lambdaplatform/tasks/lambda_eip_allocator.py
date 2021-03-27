import boto3


def handler(event):
    ec2 = boto3.client("ec2")

    if event["detail"]["eventName"] == "CreateNetworkInterface":
        interface_id = event["detail"]["responseElements"]["networkInterface"]["networkInterfaceId"]
        response = ec2.allocate_address(
            Domain="vpc",
            TagSpecifications=[
                {
                    "ResourceType": "elastic-ip",
                    "Tags": [
                        {
                            "Key": "lambda-eip:interface-id",
                            "Value": interface_id,
                        },
                        {
                            "Key": "Name",
                            "Value": "lambda-eip",
                        },
                    ],
                },
            ],
        )
        ec2.associate_address(
            AllocationId=response["AllocationId"],
            NetworkInterfaceId=interface_id,
            AllowReassociation=False,
        )

    elif event["detail"]["eventName"] == "DeleteNetworkInterface":
        interface_id = event["detail"]["requestParameters"]["networkInterfaceId"]
        response = ec2.describe_addresses(
            Filters=[
                {
                    "Name": "tag:lambda-eip:interface-id",
                    "Values": [interface_id],
                }
            ],
        )
        for address in response["Addresses"]:
            ec2.release_address(AllocationId=address["AllocationId"])
