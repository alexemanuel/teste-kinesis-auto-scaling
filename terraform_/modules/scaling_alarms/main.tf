locals {
  kinesis_period_mins = var.metrics_evaluation_period_secs * 60
}

resource aws_cloudwatch_metric_alarm kinesis_scale_up {
  alarm_name                = "${var.kinesis_stream.name}-scale-up"
  comparison_operator       = "GreaterThanOrEqualToThreshold"
  evaluation_periods        = var.scale_up_evaluation_period
  datapoints_to_alarm       = var.scale_up_datapoints_required
  threshold                 = var.scale_up_threshold
  alarm_description         = "Stream throughput has gone above the scale up threshold"
  insufficient_data_actions = []
  alarm_actions             = var.alarm_actions

  metric_query {
    id         = "s1"
    label      = "ShardCount"
    expression = var.kinesis_stream.shard_count
  }

  metric_query {
    id    = "m1"
    label = "IncomingBytes"
    metric {
      metric_name = "IncomingBytes"
      namespace   = "AWS/Kinesis"
      period      = var.metrics_evaluation_period_secs
      stat        = "Sum"
      dimensions = {
        StreamName = var.kinesis_stream.name
      }
    }
  }

  metric_query {
    id    = "m2"
    label = "IncomingRecords"
    metric {
      metric_name = "IncomingRecords"
      namespace   = "AWS/Kinesis"
      period      = var.metrics_evaluation_period_secs
      stat        = "Sum"
      dimensions = {
        StreamName = var.kinesis_stream.name
      }
    }
  }

  metric_query {
    id         = "e1"
    label      = "FillMissingDataPointsWithZeroForIncomingBytes"
    expression = "FILL(m1,0)"
  }

  metric_query {
    id         = "e2"
    label      = "FillMissingDataPointsWithZeroForIncomingRecords"
    expression = "FILL(m2,0)"
  }

  metric_query {
    id         = "e3"
    label      = "IncomingBytesUsageFactor"
    expression = "e1/(1024*1024*60*${local.kinesis_period_mins}*s1)"
  }

  metric_query {
    id         = "e4"
    label      = "IncomingRecordsUsageFactor"
    expression = "e2/(1000*60*${local.kinesis_period_mins}*s1)"
  }

  metric_query {
    id          = "e5"
    label       = "MaxIncomingUsageFactor"
    expression  = "MAX([e3,e4])" # Take the highest usage factor between bytes/sec and records/sec
    return_data = true
  }

  lifecycle {
    ignore_changes = [
      tags["LastScaledTimestamp"] # A tag that is updated every time Kinesis autoscales the stream
    ]
  }
}

resource aws_cloudwatch_metric_alarm kinesis_scale_down {
  alarm_name                = "${var.kinesis_stream.name}-scale-down"
  comparison_operator       = "LessThanThreshold"
  evaluation_periods        = var.scale_down_evaluation_period                                                                      # Defined in scale.tf
  datapoints_to_alarm       = var.scale_down_datapoints_required                                                                    # Defined in scale.tf
  threshold                 = var.kinesis_stream.shard_count == 1 ? -1 : var.scale_down_threshold        # Defined in scale.tf
  alarm_description         = "Stream throughput has gone below the scale down threshold"
  insufficient_data_actions = []
  alarm_actions             = var.alarm_actions

  metric_query {
    id         = "s1"
    label      = "ShardCount"
    expression = var.kinesis_stream.shard_count
  }

  metric_query {
    id         = "s2"
    label      = "IteratorAgeMinutesToBlockScaledowns"
    expression = var.scale_down_min_iter_age_mins
  }

  metric_query {
    id    = "m1"
    label = "IncomingBytes"
    metric {
      metric_name = "IncomingBytes"
      namespace   = "AWS/Kinesis"
      period      = var.metrics_evaluation_period_secs
      stat        = "Sum"
      dimensions = {
        StreamName = var.kinesis_stream.name
      }
    }
  }

  metric_query {
    id    = "m2"
    label = "IncomingRecords"
    metric {
      metric_name = "IncomingRecords"
      namespace   = "AWS/Kinesis"
      period      = var.metrics_evaluation_period_secs
      stat        = "Sum"
      dimensions = {
        StreamName = var.kinesis_stream.name
      }
    }
  }

  metric_query {
    id    = "m3"
    label = "GetRecords.IteratorAgeMilliseconds"
    metric {
      metric_name = "GetRecords.IteratorAgeMilliseconds"
      namespace   = "AWS/Kinesis"
      period      = var.metrics_evaluation_period_secs
      stat        = "Maximum"
      dimensions = {
        StreamName = var.kinesis_stream.name
      }
    }
  }

  metric_query {
    id         = "e1"
    label      = "FillMissingDataPointsWithZeroForIncomingBytes"
    expression = "FILL(m1,0)"
  }

  metric_query {
    id         = "e2"
    label      = "FillMissingDataPointsWithZeroForIncomingRecords"
    expression = "FILL(m2,0)"
  }

  metric_query {
    id         = "e3"
    label      = "IncomingBytesUsageFactor"
    expression = "e1/(1024*1024*60*${local.kinesis_period_mins}*s1)"
  }

  metric_query {
    id         = "e4"
    label      = "IncomingRecordsUsageFactor"
    expression = "e2/(1000*60*${local.kinesis_period_mins}*s1)"
  }

  metric_query {
    id         = "e5"
    label      = "IteratorAgeAdjustedFactor"
    expression = "(FILL(m3,0)/1000/60)*(${var.scale_down_threshold}/s2)" # We want to block scaledowns when IterAge is > 60 mins, multiply IterAge so 60 mins = <alarmThreshold>
  }

  metric_query {
    id          = "e6"
    label       = "MaxIncomingUsageFactor"
    expression  = "MAX([e3,e4,e5])" # Take the highest usage factor between bytes/sec, records/sec, and adjusted iterator age
    return_data = true
  }

  lifecycle {
    ignore_changes = [
      tags["LastScaledTimestamp"] # A tag that is updated every time Kinesis autoscales the stream
    ]
  }
}
