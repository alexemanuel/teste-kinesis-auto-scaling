import json
import os
from datetime import datetime
from typing import Sequence, Dict
import logging
import boto3
import botocore


def parse_alarm_name_and_tags(alarm_name: str, alarm_tags: Sequence[Dict[str, str]]) -> Sequence[str]:
	"""parseAlarmNameAndTags figures out the scale action and the names for the scale-up and scale-down alarms based on the alarm name that triggered this lambda
	   It returns both the alarm names and the scaling action of the current alarm
	   Parameters:
	   listTags: The tag list response from the CloudWatch ListTagsForResource API
	   currentAlarmName: The name of the alarm that triggered the invocation"""

	last_scaled_timestamp = ""
	scale_down_suffix = "-scale-down"
	scale_up_suffix = "-scale-up"

	if scale_down_suffix in alarm_name:
		alarm_action = "Down"
		scale_down_alarm_name = alarm_name
		scale_up_alarm_name = alarm_name.replace(scale_down_suffix, scale_up_suffix)

	elif scale_up_suffix in alarm_name:
		alarm_action = "Up"
		scale_up_alarm_name = alarm_name
		scale_down_alarm_name = alarm_name.replace(scale_up_suffix, scale_down_suffix)

	for tag in alarm_tags["Tags"]:
		if tag["Key"] == "LastScaledTimestamp":
			last_scaled_timestamp = tag["Value"]

	return  scale_up_alarm_name, scale_down_alarm_name, alarm_action, last_scaled_timestamp


def get_stream_name(alarm_information: Dict[str, str]) -> str:
	"""GetStreamName retrieves the stream name from the SNS Message.
	   Structure of the SNS Message can be seen here: https://github.com/aws/aws-lambda-go/blob/master/events/sns.go
	   SNS JSON that this function parses to retrieve the stream name: {"AlarmName": "Kinesis_Auto_Scale_Up_Alarm","AlarmDescription": "Alarm to scale up Kinesis stream","AWSAccountId": "111111111111","NewStateValue": "ALARM","NewStateReason": "Threshold Crossed: 1 out of the last 1 datapoints [0.43262672424316406 (23/04/20 21:16:00)] was greater than or equal to the threshold (0.4) (minimum 1 datapoint for OK -> ALARM transition).","StateChangeTime": "2020-04-23T21:17:44.775+0000","Region": "US East (Ohio)","AlarmArn": "arn:aws:cloudwatch:us-east-2:111111111111:alarm:Kinesis_Auto_Scale_Up_Alarm","OldStateValue": "OK","Trigger": {"Period": 60,"EvaluationPeriods": 1,"ComparisonOperator": "GreaterThanOrEqualToThreshold","Threshold": 0.4,"TreatMissingData": "- TreatMissingData:                    ignore","EvaluateLowSampleCountPercentile": "","Metrics": [{"Id": "m1","Label": "IncomingBytes","MetricStat": {"Metric": {"Dimensions": [{"value": "auto-scaling-demo-stream","name": "StreamName"}],"MetricName": "IncomingBytes","Namespace": "AWS/Kinesis"},"Period": 60,"Stat": "Sum"},"ReturnData": false},{"Id": "m2","Label": "IncomingRecords","MetricStat": {"Metric": {"Dimensions": [{"value": "auto-scaling-demo-stream","name": "StreamName"}],"MetricName": "IncomingRecords","Namespace": "AWS/Kinesis"},"Period": 60,"Stat": "Sum"},"ReturnData": false},{"Expression": "FILL(m1,0)","Id": "e1","Label": "FillMissingDataPointsWithZeroForIncomingBytes","ReturnData": false},{"Expression": "FILL(m2,0)","Id": "e2","Label": "FillMissingDataPointsWithZeroForIncomingRecords","ReturnData": false},{"Expression": "e1/(1024*1024*60*1)","Id": "e3","Label": "IncomingBytesUsageFactor","ReturnData": false},{"Expression": "e2/(1000*60*1)","Id": "e4","Label": "IncomingRecordsUsageFactor","ReturnData": false},{"Expression": "MAX([e3,e4])","Id": "e5","Label": "ScalingTrigger","ReturnData": true}]}
	   It returns the stream name
	   Parameters:
	   alarmInformation: The message property from the SNSEntity object."""

	stream_name = ""

	for metric in alarm_information["Trigger"]["Metrics"]:
		if metric.get("MetricStat") is not None:
			if metric["Id"] in ("m1", "m2"):
				stream_name = metric["MetricStat"]["Metric"]["Dimensions"][0]["value"]
				break 

	return stream_name


def calculate_new_shard_count(scale_action: str, down_threshold: float, current_shard_count: int) -> Sequence[int]:
	"""CalculateNewShardCount computes the new shard count based on the current shards and the scaling action
	It returns the new shard count and the scaling down threshold
	Parameters:
	scaleAction: The scaling action. Possible values are Up and Down
	downThreshold: The current scaling down threshold. This will be set to -1.0 if the new shard count turns out to be 1
	currentShardCount: The current open shards in the Kinesis stream"""

	if scale_action == "Up":
		target_shard_count = current_shard_count * 2

	if scale_action == "Down":
		target_shard_count = int(current_shard_count / 2)

		if target_shard_count < 1:
			target_shard_count = 1
			down_threshold = -1

	return target_shard_count, down_threshold


def set_alarm_state(alarm_name: str, state: str, reason: str):
	"""SetAlarmState updates the state of the alarm.
	   The state is set to OK in case of any unexpected errors (except Kinesis ResourceInUseException error).
	   The state is set to INSUFFICIENT_DATA after the stream scales successfully.
	   It returns the response and error from the CloudWatch SetAlarmState API.
	   Parameters:
	   alarmName: Name of the alarm
	   state: Target state of the alarm
	   reason: String for the reason of the state transition"""

	response = cloudwatch_client.set_alarm_state(
		AlarmName=alarm_name,
		StateValue=state,
		StateReason=reason
	)
	return response


def get_alarm_arn(scale_up_alarm: str, scale_down_alarm: str) -> Sequence[str]:
	"""GetAlarmArn retrieves the arn of the alarm given the alarm name.
	It returns the scale-up alarm arn, scale-down alarm arn and the error from the CloudWatch DescribeAlarms API
	Parameters:
	scaleUpAlarmName: Alarm name
	scaleDownAlarmName: Alarm name"""

	scale_down_alarm_arn = ""
	scale_up_alarm_arn = ""

	describe_alarms_response = cloudwatch_client.describe_alarms(
		AlarmNames=[scale_up_alarm, scale_down_alarm]
	)

	for alarm in describe_alarms_response["MetricAlarms"]:

		if alarm["AlarmName"] == scale_up_alarm:
			scale_up_alarm_arn = alarm["AlarmArn"]

		elif alarm["AlarmName"] == scale_down_alarm:
			scale_down_alarm_arn = alarm["AlarmArn"]

	return scale_up_alarm_arn, scale_down_alarm_arn


def tag_alarm(
	alarm_arn: str, 
	scale_action: str, 
	complimentary_alarm: str, 
	action_value: str, 
	alarm_value: str,
	last_scaled_timestamp: str) -> None:

	"""TagAlarm tags the alarms with two tags, keys being ScaleAction and ComplimentaryAlarm.
	   It returns the response and error for the CloudWatch TagResource API
	   Parameters:
	   alarmArn: ARN of the alarm
	   scaleAction: Tag key. Valid value: ScaleAction
	   complimentaryAlarm: Tag key. Valid value: ComplimentaryAlarm
	   actionValue: Scale action that the alarm is used for. Valid values: Up or Down
	   alarmName: The name of the alarm that is complimentary to the alarm being tagged. Valid value: Name of the alarm"""

	response = cloudwatch_client.tag_resource(
		ResourceARN=alarm_arn,
		Tags=[
			{
				'Key': scale_action, 
				'Value': action_value 
			},
			{
				'Key': complimentary_alarm, 
				'Value': alarm_value, 
			},
			{
				'Key': 'LastScaledTimestamp',
				'Value': last_scaled_timestamp 
			},
		]
	)    


def update_alarm(
	alarm_name: str, 
	evaluation_period: int, 
	datapoint_required: int, 
	threshold: float,
	compartison_operation: str,
	stream_name: str,
	alarm_actions: Sequence[str],
	new_shard_count: int,
	is_scale_down: bool,
	scale_down_min_iter_age_mins: int,
	period_mins) -> None:

	"""UpdateAlarm updates the cloudwatch alarm with an updated shardCount values (parameter newShardCount).
	   All other metric math definitions remain the same.
	   It returns the output and error from the CloudWatch PutMetricAlarm API.
	   Parameters:
	   alarmName: Name of the alarm
	   evaluationPeriod: Period after which the data for the alarm will be evaluated
	   datapointsRequired: Number of datapoints required in the evaluationPeriod to trigger the alarm
	   threshold: The threshold at which the alarm will trigger the actions
	   comparisonOperator: Operator to compare with the threshold
	   streamName: Name of the stream for which the alarm is being updated
	   alarmActions: The list of SNS topics the alarm should send message to when in ALARM state
	   newShardCount: The new shard count of the Kinesis Data Stream
	   isScaledown: true if the alarm is for scale down, false if for scale up
	   scaleDownMinIterAgeMins: used for scaleDown only metrics"""

	metrics = []

	# Add m1
	metrics.append(
		{
			"Id": "m1",
			"Label": "IncomingBytes",
			"ReturnData": False,
			"MetricStat": {
				"Metric": {
					"Namespace": "AWS/Kinesis",
					"MetricName": "IncomingBytes",
					"Dimensions": [{
						"Name": "StreamName",
						"Value": stream_name,
					}],
				},
				"Period": 60 * period_mins,
				"Stat": "Sum",
			}
		}
	)

	# Add m2
	metrics.append(
		{
			"Id": "m2",
			"Label": "IncomingRecords",
			"ReturnData": False,
			"MetricStat": {
				"Metric": {
					"Namespace": "AWS/Kinesis",
					"MetricName": "IncomingRecords",
					"Dimensions": [{
						"Name": "StreamName",
						"Value": stream_name,
					}],
				},
				"Period": 60 * period_mins,
				"Stat": "Sum",
			}
		}
	)

	# Add m3	
	if is_scale_down:
		metrics.append(
			{
				"Id": "m3",
				"Label": "",
				"ReturnData": False,
				"MetricStat": {
					"Metric": {
						"Namespace": "AWS/Kinesis",
						"MetricName": "GetRecords.IteratorAgeMilliseconds",
						"Dimensions": [{
							"Name": "StreamName",
							"Value": stream_name,
						}],
					},
					"Period": 60 * period_mins,
					"Stat": "Maximum",
				}
			}
		)

	# Add e1, e2, e3, e4
	metrics.extend([
		{
			"Id": "e1",
			"Expression": "FILL(m1,0)",
			"Label": "FillMissingDataPointsWithZeroForIncomingBytes",
			"ReturnData": False,
		},
		{
			"Id": "e2",
			"Expression": "FILL(m2,0)",
			"Label": "FillMissingDataPointsWithZeroForIncomingRecords",
			"ReturnData": False,
		},
		{
			"Id": "e3",
			"Expression": f"e1/(1024*1024*60*{period_mins}*s1)",
			"Label": "IncomingBytesUsageFactor",
			"ReturnData": False,
		},
		{
			"Id": "e4",
			"Expression": f"e2/(1000*60*{period_mins}*s1)",
			"Label": "IncomingRecordsUsageFactor",
			"ReturnData": False,
		},
	])

	if is_scale_down:
		metrics.append({
			"Id": "e5",
			"Expression": f"(FILL(m3,0)/1000/60)*({threshold}/s2)",
			"Label": "IteratorAgeAdjustedFactor",
			"ReturnData": False,
		})

	# Add e6
	if is_scale_down:
		metrics.append(
			{
				"Id": "e6",
				"Expression": "MAX([e3,e4,e5])",
				"Label": "MaxIncomingUsageFactor",
				"ReturnData": True,
			},
		)
	else:
		metrics.append(
			{
				"Id": "e6",
				"Expression": "MAX([e3,e4])",
				"Label": "MaxIncomingUsageFactor",
				"ReturnData": True,
			},
		)

	# Add s1	
	metrics.append(
		{
			"Id": "s1",
			"Expression": str(new_shard_count),
			"Label": "ShardCount",
			"ReturnData": False,
		},
	)

	# Add s2
	metrics.append(
		{
			"Id": "s2",
			"Expression": str(scale_down_min_iter_age_mins),
			"Label": "IteratorAgeMinutesToBlockScaleDowns",
			"ReturnData": False,
		},
	)

	cloudwatch_client.put_metric_alarm(
		AlarmName=alarm_name,
		AlarmDescription="Alarm to scale Kinesis stream",
		ActionsEnabled=True,
		AlarmActions=alarm_actions,
		EvaluationPeriods=evaluation_period,
		DatapointsToAlarm=datapoint_required,
		Threshold=threshold,
		ComparisonOperator=compartison_operation,
		TreatMissingData="ignore",
		Metrics=metrics
	)


def error_handler(message: str):
	"""ErrorHandler is a generic error handler.
	   The function logs the error and sends a message to the pagerduty sns topic (except for ResourceInUseException Kinesis API).
	   The alarm state is set to OK for the alarm to retry the scaling attempt
	   Parameters:
	   err: Error returned from the APIs
	   message: The message giving more information about the error. Message will be logged and also published to sns topic
	   currentAlarmName: Alarm name for which state has to set to OK explicitly"""

	logger.error(message)	
	set_alarm_state(alarm_name, "OK", message)


def lambda_handler(event, context):
	"""This lambda will be triggered by Scale-Up and Scale-Down cloudwatch alarms through an SNS topic.
 	   Parse SNS Message to retrieve the Alarm Information along with alarm name that triggered this Lambda.
	   List tags for the alarm  to figure out the scale-up and scale-down alarm names and scaling action for this invocation.
	   List tags for stream, validate scaling attempt and update the stream with new shard count.
	   Update Kinesis tag with timestamp.
	   Update alarm metrics with new shard count.
	   Update alarm states to INSUFFICIENT_DATA.
	   Update Alarm Tags."""

	period_mins = int(os.environ["SCALE_PERIOD_MINS"])

	evaluation_period_scale_up = int(os.environ["SCALE_UP_EVALUATION_PERIOD"])
	datapoints_required_scale_up = int(os.environ["SCALE_UP_DATAPOINTS_REQUIRED"])
	up_threshold = float(os.environ["SCALE_UP_THRESHOLD"])

	evaluation_period_scale_down = int(os.environ["SCALE_DOWN_EVALUATION_PERIOD"])
	datapoints_required_scale_down = int(os.environ["SCALE_DOWN_DATAPOINTS_REQUIRED"])
	down_threshold = float(os.environ["SCALE_DOWN_THRESHOLD"])
	scale_down_min_iter_age_mins = int(os.environ["SCALE_DOWN_MIN_ITER_AGE_MINS"])

	sns_record = event["Records"][0]["Sns"]
	message = sns_record["Message"]

	alarm_actions = [sns_record["TopicArn"]]
	alarm_information = json.loads(message)
	alarm_name = alarm_information["AlarmName"]
	alarm_arn = alarm_information["AlarmArn"]
	alarm_tags = cloudwatch_client.list_tags_for_resource(ResourceARN=alarm_arn)

	scale_up_alarm_name, scale_down_alarm_name, alarm_action, last_scaled_timestamp = parse_alarm_name_and_tags(alarm_name, alarm_tags)

	stream_name = get_stream_name(alarm_information)
	stream_sumary = kinesis_client.describe_stream_summary(StreamName=stream_name)
	current_shard_count = stream_sumary["StreamDescriptionSummary"]["OpenShardCount"]

	new_shard_count, down_threshold = calculate_new_shard_count(alarm_action, down_threshold, current_shard_count)

	try:
		response = kinesis_client.update_shard_count(
			StreamName=stream_name,
			TargetShardCount=new_shard_count,
			ScalingType="UNIFORM_SCALING"
		)
	except botocore.exceptions.ClientError as error:
		error_message = f"Falha durante a atualização do número de shards. Erro: {error.response}"
		error_handler(error_message)
		return

	alarm_last_scaled_timestamp = datetime.now().isoformat()

	# Update Scale Up Alarm
	update_alarm(
		scale_up_alarm_name,
		evaluation_period_scale_up,
		datapoints_required_scale_up,
		up_threshold,
		'GreaterThanOrEqualToThreshold',
		stream_name,
		alarm_actions, 
		new_shard_count,
		False,
		0,
		period_mins
	)

	set_alarm_state(
		scale_up_alarm_name, 
		"INSUFFICIENT_DATA", 
		"Valores das Métricas e Treshold atualizados"
	)

	# Update Scale Down Alarm
	update_alarm(
		scale_down_alarm_name,
		evaluation_period_scale_down,
		datapoints_required_scale_down,
		down_threshold,
		'LessThanOrEqualToThreshold',
		stream_name,
		alarm_actions,
		new_shard_count,
		True,
		scale_down_min_iter_age_mins,
		period_mins
	)

	set_alarm_state(
		scale_down_alarm_name, 
		"INSUFFICIENT_DATA", 
		"Valores das Métricas e Treshold atualizados"
	)

	# Tag Scale Up Alarm 
	tag_alarm(
		scale_up_alarm_arn, 
		"ScaleAction", 
		"ComplimentaryAlarm", 
		"Up", 
		scale_down_alarm_name,
		last_scaled_timestamp
	)

	# Tag Scale Down Alarm 
	tag_alarm(
		scale_down_alarm_arn, 
		"ScaleAction", 
		"ComplimentaryAlarm", 
		"Down", 
		scale_up_alarm_name,
		last_scaled_timestamp
	)


cloudwatch_client = boto3.client('cloudwatch')
kinesis_client = boto3.client('kinesis')

logger = logging.getLogger()
logger.setLevel(logging.INFO)