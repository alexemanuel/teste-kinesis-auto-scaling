output "scale_up_cloudwatch_alarm_arn" {
    value = aws_cloudwatch_metric_alarm.kinesis_scale_up.arn
    description = ""
}

output "scale_down_cloudwatch_alarm_arn" {
    value = aws_cloudwatch_metric_alarm.kinesis_scale_down.arn
    description = ""
}