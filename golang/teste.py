import json
import boto3
import logging


cloudwatch_client = boto3.client('cloudwatch')
kinesis_client = boto3.client('kinesis')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def set_alarm_state(alarm_name: str, state: str, reason: str) -> None:
    response = cloudwatch_client.set_alarm_state(
									  AlarmName=alarm_name,
									  StateValue=state,
									  StateReason=reason,
    )
    
    logger.info(dir(response))

def lambda_handler(event, context):
    
    alarm_name = "autoscaling-kinesis-stream-scale-up"
    set_alarm_state(alarm_name, "INSUFFICIENT_DATA", "Metric math and threshold value update")

    # TODO implement
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
