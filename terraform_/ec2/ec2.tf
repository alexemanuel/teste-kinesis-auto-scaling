
# Create a bucket
resource "aws_s3_bucket" "b1" {
  bucket = "s3-terraform-bucket-lab-alex"
  acl    = "public-read"   # or can be "public-read"
  tags = {
    Name        = "My bucket"
    Environment = "Dev"

  }
}

# Upload an object
resource "aws_s3_bucket_object" "object" {
  bucket = aws_s3_bucket.b1.id
  key    = "profile.zip"
  acl    = "public-read"  # or can be "public-read"
  source = "../../amazon-kinesis-data-generator.zip"
  etag = filemd5("../../amazon-kinesis-data-generator.zip")

}

resource "aws_iam_role" "example" {
  name = "example7"

  # assume_role_policy is omitted for brevity in this example. Refer to the
  # documentation for aws_iam_role for a complete example.
  assume_role_policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": "sts:AssumeRole",
            "Principal": {
               "Service": "ec2.amazonaws.com"
            },
            "Effect": "Allow"
        }
    ]
}
EOF
}

resource "aws_iam_role_policy" "example" {
  name   = "example7"
  role   = aws_iam_role.example.name
  policy = jsonencode({
    "Statement" = [{
      "Action" = "*",
      "Effect" = "Allow",
      "Resource" = "*",
    }],
  })
}


resource "aws_iam_instance_profile" "example" {
  # Because this expression refers to the role, Terraform can infer
  # automatically that the role must be created first.
  role = aws_iam_role.example.name
}


resource "aws_instance" "web" {
  ami           = "ami-0cff7528ff583bf9a" 
  instance_type = "t3.micro"
  user_data_base64 = filebase64("./ec2_user_data.sh")
  iam_instance_profile = aws_iam_instance_profile.example.name

  tags = {
    Name = "teste123"
  }
  depends_on = [aws_s3_bucket_object.object]

}