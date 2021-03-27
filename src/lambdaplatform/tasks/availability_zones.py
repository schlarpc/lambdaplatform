import boto3

from . import common


def handler(event):
    with common.cloudformation_custom_resource(event) as resource:
        if event["RequestType"] in {"Create", "Update"}:
            previous_zone_names = []
            if event.get("PhysicalResourceId"):
                previous_zone_names = event["PhysicalResourceId"].split(",")
            current_zone_names = sorted(
                zone["ZoneName"]
                for zone in boto3.client("ec2").describe_availability_zones(
                    Filters=[
                        {
                            "Name": "zone-type",
                            "Values": ["availability-zone"],
                        },
                        {
                            "Name": "opt-in-status",
                            "Values": ["opted-in", "opt-in-not-required"],
                        },
                    ],
                )["AvailabilityZones"]
            )
            stable_zone_names = previous_zone_names + [
                zone_name
                for zone_name in current_zone_names
                if zone_name in set(current_zone_names) - set(previous_zone_names)
            ]
            if not stable_zone_names:
                raise ValueError("No availability zones found")
            resource["PhysicalResourceId"] = ",".join(stable_zone_names)
