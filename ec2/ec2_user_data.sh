#! /bin/bash

cd /root

aws s3 cp s3://s3-terraform-bucket-lab-alex/profile.zip .
unzip profile.zip

yum install -y httpd

cp amazon-kinesis-data-generator/web/* /var/www.html/ 

systemctl start httpd