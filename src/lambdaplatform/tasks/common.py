import contextlib
import json
import urllib.request


@contextlib.contextmanager
def cloudformation_custom_resource(event):
    resource = {
        "Status": "SUCCESS",
        "LogicalResourceId": event["LogicalResourceId"],
        "RequestId": event["RequestId"],
        "StackId": event["StackId"],
        "PhysicalResourceId": event.get("PhysicalResourceId"),
    }
    try:
        yield resource
    except Exception as ex:
        resource.update(
            {
                "Status": "FAILED",
                "Reason": f"{type(ex).__name__}: {str(ex)}",
            }
        )
    payload = json.dumps(resource)
    urllib.request.urlopen(
        urllib.request.Request(
            method="PUT",
            url=event["ResponseURL"],
            data=payload.encode("utf-8"),
            headers={"Content-Type": ""},
        )
    )
    return resource
