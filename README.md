# lambdaplatform

This is an experimental nixpkgs-based opinionated software stack for AWS Lambda.
Its aims are reproducible builds, simple deployment, no fixed billing costs,
and offering as many features as possible for application development.

It offers the following features:
* Self-bootstrapping, single command deployment via CloudFormation
* Container image based Python 3.x runtime with support for arbitrary nixpkgs dependencies
* Simultaneous VPC and internet access without expensive NAT instances or gateways
* Shared NFS mount via Elastic File System, can be useful for things like sqlite
* Automatic expiration of unused container images

Future possible features include:
* More cleanly separated application code from platform code
* Web serving via some combination of CloudFront, API Gateway, S3 Object Lambda (for streaming responses)
* Deferred execution via SQS delay queues or DynamoDB TTLs
* Scatter-gather execution across Lambda functions
* Runtime controllable memory allocation for invoked Lambda functions
* Automatic expiration of other unused deployment artifacts
* Multi-AZ support
* Deploying to existing VPCs
* Opinionated/structured logging

## Usage

`nix-build` then `result/deploy --stack-name lambdaplatform`
