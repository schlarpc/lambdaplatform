import functools
import hashlib
import pathlib

from awacs import cloudformation, sns, ssm, sts
from awacs.aws import Allow, PolicyDocument, Principal, Statement
from troposphere import (
    AccountId,
    Equals,
    GetAtt,
    If,
    Join,
    Output,
    Parameter,
    Partition,
    Ref,
    Region,
    Select,
    Split,
    StackId,
    StackName,
    Template,
    URLSuffix,
)
from troposphere.cloudformation import DeploymentTargets, OperationPreferences
from troposphere.cloudformation import Parameter as StackSetParameter
from troposphere.cloudformation import (
    Stack,
    StackInstances,
    StackSet,
    WaitCondition,
    WaitConditionHandle,
)
from troposphere.iam import Policy, PolicyType, Role
from troposphere.ssm import Parameter as SSMParameter

from . import common


def create_stack_set_template():
    template = Template(Description="SSM parameter Ouroboros creation utility")

    parameter_name = template.add_parameter(
        Parameter(
            "ParameterName",
            Type="String",
        )
    )

    parameter_value = template.add_parameter(
        Parameter(
            "ParameterValue",
            Type="String",
            AllowedPattern=".+",
        )
    )

    retain_parameter = template.add_parameter(
        Parameter(
            "RetainParameter",
            Type="String",
            AllowedValues=["true", "false"],
        )
    )

    should_retain_parameter = "ShouldRetainParameter"
    template.add_condition(should_retain_parameter, Equals(Ref(retain_parameter), "true"))

    should_delete_parameter = "ShouldDeleteParameter"
    template.add_condition(should_delete_parameter, Equals(Ref(retain_parameter), "false"))

    for mode in ("Retain", "Delete"):
        condition = should_retain_parameter if mode == "Retain" else should_delete_parameter
        parameter = template.add_resource(
            SSMParameter(
                f"Parameter{mode}",
                Name=Ref(parameter_name),
                Value=Ref(parameter_value),
                Type="String",
                DeletionPolicy=mode,
                Condition=condition,
            )
        )

        wait_condition_handle = template.add_resource(
            WaitConditionHandle(
                f"WaitConditionHandle{mode}",
                Condition=condition,
            )
        )

        template.add_resource(
            WaitCondition(
                f"WaitCondition{mode}",
                Handle=Ref(wait_condition_handle),
                Count=1,
                Timeout=1,
                DependsOn=[parameter],
                Condition=condition,
            )
        )

    return template


def simplify_value(s):
    construct = Join("[1]", Split("[0][1]", s))
    for i in range(32):
        lo = 2 ** i
        hi = 2 ** (i + 1)
        construct = Join(f"[{hi}]", Split(f"[{lo}][{lo}]", construct))
    return construct


def increment_value(s):
    return simplify_value(Join("", [s, "[1]"]))


def create_child_stack_template():
    template = Template(
        Description="Auto-incrementing SSM parameter utility",
    )

    parameter_value = template.add_parameter(
        Parameter(
            "ParameterValue",
            Type="AWS::SSM::Parameter::Value<String>",
        )
    )

    wait_condition_handle = template.add_resource(
        WaitConditionHandle(
            "WaitConditionHandle",
        )
    )

    template.add_output(
        Output(
            "CurrentValue",
            Value=Ref(parameter_value),
        )
    )

    template.add_output(
        Output(
            "NextValue",
            Value=increment_value(Ref(parameter_value)),
        )
    )

    return template


def create_template():
    template = Template(Description="Deployment ID generator")

    artifact_bucket = template.add_parameter(
        Parameter(
            "ArtifactBucket",
            Type="String",
        )
    )

    parameter_name = Join("-", [StackName, Select(2, Split("/", StackId)), "State"])

    stack_set_administration_role = template.add_resource(
        Role(
            "StackSetAdministrationRole",
            AssumeRolePolicyDocument=PolicyDocument(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[sts.AssumeRole],
                        Principal=Principal("Service", "cloudformation.amazonaws.com"),
                    ),
                ],
            ),
        )
    )

    stack_set_execution_role = template.add_resource(
        Role(
            "StackSetExecutionRole",
            AssumeRolePolicyDocument=PolicyDocument(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[sts.AssumeRole],
                        Principal=Principal("AWS", GetAtt(stack_set_administration_role, "Arn")),
                    ),
                ],
            ),
            Policies=[
                Policy(
                    PolicyName="StackSetManagement",
                    PolicyDocument=PolicyDocument(
                        Version="2012-10-17",
                        Statement=[
                            Statement(
                                Effect=Allow,
                                Action=[cloudformation.DescribeStacks],
                                Resource=["*"],
                            ),
                            Statement(
                                Effect=Allow,
                                Action=[
                                    cloudformation.CreateStack,
                                    cloudformation.DeleteStack,
                                    cloudformation.UpdateStack,
                                ],
                                Resource=[
                                    Join(
                                        ":",
                                        [
                                            "arn",
                                            Partition,
                                            "cloudformation",
                                            "*",
                                            AccountId,
                                            Join(
                                                "/",
                                                [
                                                    "stack",
                                                    Join(
                                                        "-",
                                                        ["StackSet", StackName, "*"],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    )
                                ],
                            ),
                            Statement(
                                Effect=Allow,
                                Action=[sns.Publish],
                                NotResource=[
                                    Join(
                                        ":",
                                        ["arn", Partition, "sns", "*", AccountId, "*"],
                                    )
                                ],
                            ),
                        ],
                    ),
                ),
                Policy(
                    PolicyName="SSMPermissions",
                    PolicyDocument=PolicyDocument(
                        Version="2012-10-17",
                        Statement=[
                            # TODO scope down
                            Statement(
                                Effect=Allow,
                                Action=[ssm.Action("*")],
                                Resource=["*"],
                            ),
                        ],
                    ),
                ),
            ],
        )
    )

    stack_set_administration_role_policy = template.add_resource(
        PolicyType(
            "StackSetAdministrationRolePolicy",
            PolicyName="AssumeExecutionRole",
            PolicyDocument=PolicyDocument(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[sts.AssumeRole],
                        Resource=[GetAtt(stack_set_execution_role, "Arn")],
                    )
                ],
            ),
            Roles=[Ref(stack_set_administration_role)],
        )
    )

    common_stack_set_properties = dict(
        AdministrationRoleARN=GetAtt(stack_set_administration_role, "Arn"),
        ExecutionRoleName=Ref(stack_set_execution_role),
        OperationPreferences=OperationPreferences(
            FailureTolerancePercentage=100,
            MaxConcurrentPercentage=100,
        ),
        PermissionModel="SELF_MANAGED",
        StackInstancesGroup=[
            StackInstances(
                DeploymentTargets=DeploymentTargets(
                    Accounts=[AccountId],
                ),
                Regions=[Region],
            )
        ],
        TemplateURL=common.get_template_s3_url(Ref(artifact_bucket), create_stack_set_template()),
    )

    stack_set_retain = template.add_resource(
        StackSet(
            "StackSetRetain",
            StackSetName=Join("-", [StackName, "StackSetRetain"]),
            Parameters=[
                StackSetParameter(
                    ParameterKey="ParameterName",
                    ParameterValue=parameter_name,
                ),
                StackSetParameter(
                    ParameterKey="ParameterValue",
                    ParameterValue="[0]",
                ),
                StackSetParameter(
                    ParameterKey="RetainParameter",
                    ParameterValue="true",
                ),
            ],
            DependsOn=[stack_set_administration_role_policy],
            **common_stack_set_properties,
        )
    )

    stack = template.add_resource(
        Stack(
            "Stack",
            TemplateURL=common.get_template_s3_url(
                Ref(artifact_bucket), create_child_stack_template()
            ),
            Parameters={
                "ParameterValue": parameter_name,
            },
            DependsOn=[stack_set_retain],
        )
    )

    stack_set_delete = template.add_resource(
        StackSet(
            "StackSetDelete",
            StackSetName=Join("-", [StackName, "StackSetDelete"]),
            Parameters=[
                StackSetParameter(
                    ParameterKey="ParameterName",
                    ParameterValue=parameter_name,
                ),
                StackSetParameter(
                    ParameterKey="ParameterValue",
                    ParameterValue="[0]",
                ),
                StackSetParameter(
                    ParameterKey="RetainParameter",
                    ParameterValue="false",
                ),
            ],
            DependsOn=[stack],
            **common_stack_set_properties,
        )
    )

    parameter = template.add_resource(
        SSMParameter(
            "Parameter",
            Name=parameter_name,
            Type="String",
            Value=GetAtt(stack, "Outputs.NextValue"),
            DependsOn=[stack_set_delete],
        )
    )

    template.add_output(
        Output(
            "Value",
            Value=GetAtt(stack, "Outputs.NextValue"),
        )
    )

    return template
