import argparse
import contextlib
import importlib
import json
import os
import sys
import urllib.request
from typing import Dict, Optional


def make_http_request(method, url, *, data=None, headers=None):
    return urllib.request.urlopen(
        urllib.request.Request(
            method=method,
            url=url,
            data=data,
            headers=headers or {},
        )
    )


@contextlib.contextmanager
def report_error(endpoint: str, request_id: Optional[str] = None):
    try:
        yield
    except BaseException as ex:
        make_http_request(
            method="POST",
            url=f"{endpoint}/invocation/{request_id}/error"
            if request_id
            else f"{endpoint}/init/error",
            data=json.dumps({"type": type(ex).__qualname__, "message": str(ex)}).encode("utf-8"),
        )
        if request_id is None:
            sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("handler")
    return parser.parse_args()


def main(*, environment: Dict[str, str] = os.environ):
    args = get_args()
    endpoint = f"http://{environment['AWS_LAMBDA_RUNTIME_API']}/2018-06-01/runtime"
    with report_error(endpoint):
        module_name, callable_name = args.handler.split(":", 1)
        callable = getattr(importlib.import_module(module_name), callable_name)
    while True:
        invocation = make_http_request("GET", f"{endpoint}/invocation/next")
        request_id = invocation.headers["Lambda-Runtime-Aws-Request-Id"]
        with report_error(endpoint, request_id):
            response = json.dumps(callable(json.loads(invocation.read())))
            make_http_request(
                "POST",
                f"{endpoint}/invocation/{request_id}/response",
                data=response.encode("utf-8"),
            )


if __name__ == "__main__":
    main()
