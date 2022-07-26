# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

locals {
  kinesis_stream_name             = "autoscaling-kinesis-stream"
  kinesis_stream_retention_period = 24 # hours. Must use 168 hours (7 days) max for Disaster Recovery
  kinesis_stream_shard_count      = 1 # Starting shard count, autoscaling will right-size this
}

module "auto_scaling_stream1" {
  source                         = "./modules/auto_scaling_stream"
  stream_name                    = local.kinesis_stream_name
  stream_retention_period        = local.kinesis_stream_retention_period 
  stream_shard_count             = local.kinesis_stream_shard_count
  scale_up_evaluation_period     = local.kinesis_scale_up_evaluation_period
  scale_up_datapoints_required   = local.kinesis_scale_up_datapoints_required
  scale_up_threshold             = local.kinesis_scale_up_threshold
  scale_down_evaluation_period   = local.kinesis_scale_down_evaluation_period
  scale_down_datapoints_required = local.kinesis_scale_down_datapoints_required
  scale_down_threshold           = local.kinesis_scale_down_threshold
  scale_down_min_iter_age_mins   = local.kinesis_scale_down_min_iter_age_mins
  alarm_actions                  = [aws_sns_topic.kinesis_scaling_sns_topic.arn]
  metrics_evaluation_period_mins = local.kinesis_period_mins
}