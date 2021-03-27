import functools
import hashlib

from troposphere import Equals, GetAtt, If, Join, Not, Ref, Select, Split
from troposphere.awslambda import Alias, Environment, Version

template_registry = {}


def template_to_json(template):
    return template.to_json(indent=None, sort_keys=True, separators=(",", ":"))


def hash_template(template):
    return hashlib.sha256(template_to_json(template).encode("utf-8")).hexdigest()


def get_template_s3_url(artifact_bucket, template, *, _registry=template_registry):
    sha256 = hash_template(template)
    filename = f"{sha256}.json"
    _registry[filename] = template_to_json(template).encode("utf-8")
    return Join(
        "/",
        ["https://s3.amazonaws.com", artifact_bucket, filename],
    )


def add_double_sided_condition(template, condition_name_base, conditional):
    template.add_condition(
        f"{condition_name_base}True",
        conditional,
    )

    template.add_condition(f"{condition_name_base}False", Not(conditional))

    return f"{condition_name_base}True", f"{condition_name_base}False"


def add_versioned_lambda(
    template,
    deployment_id,
    function,
):
    environment = function.properties.setdefault("Environment", Environment(Variables={}))
    environment.Variables["X__DO_NOT_USE__DEPLOYMENT_ID"] = deployment_id

    function = template.add_resource(function)

    (is_odd_deployment, is_even_deployment) = add_double_sided_condition(
        template,
        f"{function.title}DeploymentIdParityOdd",
        Equals(determine_parity(deployment_id), "ODD"),
    )

    version_a = template.add_resource(
        Version(
            f"{function.title}VersionA",
            FunctionName=GetAtt(function, "Arn"),
            Condition=is_odd_deployment,
        )
    )

    version_b = template.add_resource(
        Version(
            f"{function.title}VersionB",
            FunctionName=GetAtt(function, "Arn"),
            Condition=is_even_deployment,
        )
    )

    version_number = If(
        is_odd_deployment,
        GetAtt(version_a, "Version"),
        GetAtt(version_b, "Version"),
    )

    alias = template.add_resource(
        Alias(
            f"{function.title}Alias",
            FunctionName=GetAtt(function, "Arn"),
            FunctionVersion=version_number,
            Name="latest",
        )
    )

    return function, alias


def determine_parity(s):
    return Select(1, Split("[1]", Join("", [s, "ODD[1]EVEN"])))


LOG_RETENTION_DAYS = 7
