variable "kinesis_stream" {
    description = ""
    type = object({
        name        = string
        shard_count = number
    }) 
}

variable "scale_up_evaluation_period" {
    description = ""
    type        = number
}

variable "scale_up_datapoints_required" {
    description = ""
    type        = number
}

variable "scale_up_threshold" {
    description = ""
    type        = number
}

variable "scale_down_evaluation_period" {
    description = ""
    type        = number
}

variable "scale_down_datapoints_required" {
    description = ""
    type        = number
}

variable "scale_down_threshold" {
    description = ""
    type        = number
}

variable "scale_down_min_iter_age_mins" {
    description = ""
    type        = number
}

variable "metrics_evaluation_period_secs" {
    description = ""
    type        = number
}

variable "alarm_actions" {
    description = ""
    type        = list(string) 
}