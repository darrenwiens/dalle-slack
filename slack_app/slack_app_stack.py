import os
from aws_cdk import (
    core,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_iam as iam,
)

APP_NAME = os.environ["APP_NAME"]

class SlackAppStack(core.Stack):
    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        openai_layer = lambda_.LayerVersion(
            self,
            "openai_layer",
            code=lambda_.Code.from_asset(
                path="resources",
                bundling={
                    "image": lambda_.Runtime.PYTHON_3_8.bundling_docker_image,
                    "command": [
                        "bash",
                        "-c",
                        f"pip install openai==0.25.0 -t {core.AssetStaging.BUNDLING_OUTPUT_DIR}/python",
                    ],
                },
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
        )

        numpy_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "numpy_layer",
            layer_version_arn="arn:aws:lambda:us-west-2:770693421928:layer:Klayers-p39-numpy:9"
        )

        worker_handler = lambda_.Function(
            self,
            f"worker-lambda-handler-{APP_NAME}",
            function_name=f"slack-worker-lambda-{APP_NAME}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("resources"),
            handler="worker_handler.lambda_handler",
            environment=dict(
                SLACK_BEARER_TOKEN=os.environ["SLACK_BEARER_TOKEN"],
                OPENAI_API_KEY=os.environ["OPENAI_API_KEY"],
            ),
            layers=[
                openai_layer, numpy_layer
            ],
            timeout=core.Duration.seconds(30)
        )

        main_handler = lambda_.Function(
            self,
            f"main-lambda-handler-{APP_NAME}",
            function_name=f"slack-main-lambda-{APP_NAME}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("resources"),
            handler="main_handler.lambda_handler",
            environment=dict(
                WORKER_ARN=worker_handler.function_arn,
            ),
        )

        main_handler.add_to_role_policy(
            statement=iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[worker_handler.function_arn],
            )
        )

        api = apigateway.RestApi(
            self,
            f"slack-app-api-{APP_NAME}",
            rest_api_name=f"Slack App API Service - {APP_NAME}",
            description=f"This service serves accepts Slack slash command requests and responds with modals/messages for the {APP_NAME} app.",
            default_cors_preflight_options={"allow_origins": ["*"]},
        )

        post_slack_integration = apigateway.LambdaIntegration(
            main_handler,
            request_templates={"application/json": '{ "statusCode": "200" }'},
        )

        api.root.add_method("POST", post_slack_integration)
