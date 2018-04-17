# Notice:
EBS Snapshot Scheduler has been superseded by [AWS Ops Automator](https://aws.amazon.com/answers/infrastructure-management/ops-automator/).

In 2016, the EBS Snapshot Scheduler was launched to help AWS customers automatically create snapshots of their Amazon Elastic Block Store (Amazon EBS) volumes on a defined schedule. In 2017, AWS launched [AWS Ops Automator](https://aws.amazon.com/answers/infrastructure-management/ops-automator/), a new and improved solution that enables customers to schedule EBS and Amazon Redshift snapshots, and automate other operational tasks. We encourage customers to migrate to AWS Ops Automator for future updates and new features.
Legacy templates, scripts, and documentation for EBS Snapshot Scheduler are available in this repo for reference.

# ebs-snapshot-scheduler

The [EBS Snapshot Scheduler](https://aws.amazon.com/answers/infrastructure-management/ebs-snapshot-scheduler/) is a simple AWS solution that allows you to automatically take point-in-time snapshots (crash-consistent) of your EBS volumes. 
Please see the link for details.

Source code for the AWS solution "EBS Snapshot Scheduler". 

## Cloudformation templates

- cform/ebs-snapshot-scheduler.template

## Lambda source code

- code/ebs-snapshot-scheduler.py
- code/pytz

***

Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://aws.amazon.com/asl/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and limitations under the License.
