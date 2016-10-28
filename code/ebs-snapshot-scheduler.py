######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import boto3
import datetime
import json
from urllib2 import Request
from urllib2 import urlopen
import pytz

dynamodb = boto3.resource('dynamodb')
ec2_client = boto3.client('ec2')
cf_client = boto3.client('cloudformation')


def backup_instance(ec2, instance_obj, retention_days, history_table, aws_region):
    new_snapshot_list = []
    for volume in instance_obj.volumes.all():
        current_time = datetime.datetime.utcnow()

        current_time_str = current_time.strftime(
            "%h %d,%H:%M")
        description = """Created by EBSSnapshotScheduler from %s(%s) at %s UTC""" % (
            volume.id, instance_obj.instance_id, current_time_str)

        # Calculate purge time on the basis of retention_days setting.
        # If AutoSnapshotDeletion is yes, retention_days value will be integer, otherwise, it will be NA
        if is_int(retention_days):
            purge_time = current_time + datetime.timedelta(days=retention_days)
        else:
            purge_time = retention_days

        # schedule snapshot creation.
        try:
            snapshot = ec2.create_snapshot(
                VolumeId=volume.id, Description=description)

            snapshot_entry = {
                'snapshot_id': snapshot.id,
                'region': aws_region,
                'instance_id': instance_obj.instance_id,
                'volume_id': volume.id,
                'size': volume.size,
                'purge_time': str(purge_time),
                'start_time': str(current_time)
            }

            response = history_table.put_item(Item=snapshot_entry)
            new_snapshot_list.append(snapshot.id)
        except Exception as e:
            print e
            continue
    return new_snapshot_list


def parse_date(dt_string):
    return datetime.datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S.%f')

def purge_history(ec2, snapshots, history_table, aws_region):
    history = history_table.scan()
    purge_list = []
    delete_snapshot_list = []
    delete_history_snapshot_list = []

    for entry in history['Items']:
        if entry['purge_time'] != "NA" and entry['region'] == aws_region:
            check_time = parse_date(entry['purge_time'])
            current_time = datetime.datetime.utcnow()

            time_flag = check_time <= current_time
            snapshot_id = entry['snapshot_id']

            if time_flag:
                history_table.delete_item(Key={'snapshot_id': snapshot_id})
                purge_list.append(snapshot_id)

            # Covers the case if the snapshot was deleted manually.
            if snapshot_id not in snapshots:
                response = history_table.delete_item(Key={'snapshot_id': snapshot_id})
                if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                    delete_history_snapshot_list.append(snapshot_id)
    items_deleted = len(purge_list) + len(delete_history_snapshot_list)

    if items_deleted > 0:
        print "History table updated: items deleted:", items_deleted
    if len(delete_history_snapshot_list) > 0:
        print "History table updated:", len(
            delete_history_snapshot_list), "snapshot(s) does not exist. It was probably deleted manually or by another tool. Snapshot ID List:", delete_history_snapshot_list

    if len(purge_list) > 0:
        snaps = ec2.snapshots.filter(SnapshotIds=purge_list)
        for snap in snaps:
            try:
                response = snap.delete()
                if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                    delete_snapshot_list.append(snap.id)
            except Exception as e:
                print e
                continue
    if len(delete_snapshot_list) > 0:
        print "List of snapshots to be deleted:", delete_snapshot_list
    return len(delete_snapshot_list)


def is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

# Catching typos in case
def standardize_tz(tz):
    try:
        if tz.upper() in ('GMT', 'UTC'):
            tz = tz.upper()
            return tz.upper()
        elif '/' in tz.upper():
            tz_split = tz.split("/")
            if tz_split[0].upper() in "US":
                tz_split[0] = tz_split[0].upper()
                tz_split[1] = tz_split[1].title()
            else:
                tz_split[0] = tz_split[0].title()
                tz_split[1] = tz_split[1].title()
            tz = '/'.join(tz_split)
            return tz
        else:
            print "Time Zone is not in the standard format. Please check the implementation guide. Bad Time Zone:", tz
    except Exception as e:
        print e
        pass

def parse_tag_values(tag, default1, default2, default_snapshot_time):
    global snapshot_time, retention_days, time_zone, days_active
    ptag = tag.split(";")

    if len(ptag) >= 1:
        if ptag[0].lower() in (default1, default2):
            snapshot_time = default_snapshot_time
        else:
            snapshot_time = ptag[0]

            # If length is 2, possible values can be start_time;retention_days or start_time;time_zone.
            # If second value is integer, it's retention days, otherwise it's timezone.
    if len(ptag) == 2:
        if is_int(ptag[1]):
            retention_days = int(ptag[1])
        else:
            time_zone = ptag[1]
            # If length is 3, possible values can be start_time;retention_days;timezone
            #                                     or start_time;time_zone;days_active
            # If second value is integer, it's retention_days, otherwise it's time_zone.
    if len(ptag) == 3:
        if is_int(ptag[1]):
            retention_days = int(ptag[1])
            time_zone = ptag[2]
        else:
            time_zone = ptag[1]
            days_active = ptag[2].lower()

            # If length greater than 3, only possible value can be start_time;retention_days;timezone;days_active.
    if len(ptag) > 3:
        retention_days = int(ptag[1])
        time_zone = ptag[2]
        days_active = ptag[3].lower()
        # Standardize Time Zone case (Case Sensitive)
    time_zone = standardize_tz(time_zone)

# Tag all the snapshots
def tag_snapshots(ec2, snapshot_list):
    global custom_tag_name
    try:
        ec2.create_tags(
            Resources=snapshot_list,
            Tags=[
                {
                    'Key': custom_tag_name,
                    'Value': 'auto_delete'
                },
            ]
        )
        print "Tags successfully created for", len(snapshot_list), "snapshots."
    except Exception as e:
        print e
        pass

def lambda_handler(event, context):

    # Reading output items from the CF stack
    outputs = {}
    stack_name = context.invoked_function_arn.split(':')[6].rsplit('-', 2)[0]
    response = cf_client.describe_stacks(StackName=stack_name)
    for e in response['Stacks'][0]['Outputs']:
        outputs[e['OutputKey']] = e['OutputValue']
    policy_table_name = outputs['PolicyDDBTableName']
    history_table_name = outputs['HistoryDDBTableName']
    uuid = outputs['UUID']
    policy_table = dynamodb.Table(policy_table_name)
    history_table = dynamodb.Table(history_table_name)


    aws_regions = ec2_client.describe_regions()['Regions']

    response = policy_table.get_item(
        Key={
            'SolutionName': 'EbsSnapshotScheduler'
        }
    )
    item = response['Item']
    global snapshot_time, retention_days, time_zone, days_active, custom_tag_name

    # Reading Default Values from DynamoDB
    custom_tag_name = str(item['CustomTagName'])
    custom_tag_length = len(custom_tag_name)
    default_snapshot_time = str(item['DefaultSnapshotTime'])
    default_retention_days = int(item['DefaultRetentionDays'])
    auto_snapshot_deletion = str(item['AutoSnapshotDeletion']).lower()
    default_time_zone = str(item['DefaultTimeZone'])
    default_days_active = str(item['DefaultDaysActive']).lower()
    send_data = str(item['SendAnonymousData']).lower()
    time_iso = datetime.datetime.utcnow().isoformat()
    time_stamp = str(time_iso)
    utc_time = datetime.datetime.utcnow()
    #time_delta must be changed before updating the CWE schedule for Lambda
    time_delta = datetime.timedelta(minutes=4)
    # Declare Dicts
    region_dict = {}
    all_region_dict = {}
    regions_label_dict = {}
    post_dict = {}

    if auto_snapshot_deletion == "yes":
        print "Auto Snapshot Deletion: Enabled"
    else:
        print "Auto Snapshot Deletion: Disabled"

    for region in aws_regions:
        try:

            print "\nExecuting for region %s" % (region['RegionName'])

            # Create connection to the EC2 using Boto3 resources interface
            ec2 = boto3.client('ec2', region_name=region['RegionName'])
            ec2_resource = boto3.resource('ec2', region_name=region['RegionName'])
            aws_region = region['RegionName']

            # Declare Lists
            snapshot_list = []
            agg_snapshot_list = []
            snapshots = []

            # Filter Instances for Scheduler Tag
            instances = ec2_resource.instances.all()

            for i in instances:
                if i.tags != None:
                    for t in i.tags:
                        if t['Key'][:custom_tag_length] == custom_tag_name:
                            tag = t['Value']

                            # Split out Tag & Set Variables to default
                            default1 = 'default'
                            default2 = 'true'
                            snapshot_time = default_snapshot_time
                            retention_days = default_retention_days
                            time_zone = default_time_zone
                            days_active = default_days_active

                            # First value will always be defaults or start_time.
                            parse_tag_values(tag, default1, default2, default_snapshot_time)

                            tz = pytz.timezone(time_zone)
                            now = utc_time.replace(tzinfo=pytz.utc).astimezone(tz).strftime("%H%M")
                            now_max = utc_time.replace(tzinfo=pytz.utc).astimezone(tz) - time_delta
                            now_max = now_max.strftime("%H%M")
                            now_day = utc_time.replace(tzinfo=pytz.utc).astimezone(tz).strftime("%a").lower()
                            active_day = False

                            # Days Interpreter
                            if days_active == "all":
                                active_day = True
                            elif days_active == "weekdays":
                                weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
                                if now_day in weekdays:
                                    active_day = True
                            else:
                                days_active = days_active.split(",")
                                for d in days_active:
                                    if d.lower() == now_day:
                                        active_day = True

                            # Append to start list
                            if snapshot_time >= str(now_max) and snapshot_time <= str(now) and \
                                            active_day is True:
                                snapshot_list.append(i.instance_id)
            deleted_snapshot_count = 0

            if auto_snapshot_deletion == "yes":
                # Purge snapshots that are scheduled for deletion and snapshots that were manually deleted by users.
                for snap in ec2_resource.snapshots.filter(OwnerIds=['self']):
                    snapshots.append(snap.id)
                deleted_snapshot_count = purge_history(ec2, snapshots, history_table, aws_region)
                if deleted_snapshot_count > 0:
                    print "Number of snapshots deleted successfully:", deleted_snapshot_count
                    deleted_snapshot_count = 0
            else:
                retention_days = "NA"

            # Execute Snapshot Commands
            if snapshot_list:
                print "Taking snapshot of all the volumes for", len(snapshot_list), "instance(s)", snapshot_list
                for instance in ec2_resource.instances.filter(InstanceIds=snapshot_list):
                    new_snapshots = backup_instance(ec2_resource, instance, retention_days, history_table, aws_region)
                    return_snapshot_list = new_snapshots
                    agg_snapshot_list.extend(return_snapshot_list)
                print "Number of new snapshots created:", len(agg_snapshot_list)
                tag_snapshots(ec2, agg_snapshot_list)
            else:
                print "No new snapshots taken."

            # Build payload for each region
            if send_data == "yes":
                del_dict = {}
                new_dict = {}
                current_dict = {}
                all_status_dict = {}
                version = {}

                del_dict['snapshots_deleted'] = deleted_snapshot_count
                new_dict['snapshots_created'] = len(agg_snapshot_list)
                current_dict['snapshots_existing'] = len(snapshots)
                all_status_dict.update(current_dict)
                all_status_dict.update(new_dict)
                all_status_dict.update(del_dict)
                region_dict[aws_region] = all_status_dict
                all_region_dict.update(region_dict)

        except Exception as e:
            print e
            continue

            # Build payload for the account
    if send_data == "yes":
        regions_label_dict['regions'] = all_region_dict
        post_dict['Data'] = regions_label_dict
        post_dict['Data'].update({'Version': '1'})
        post_dict['TimeStamp'] = time_stamp
        post_dict['Solution'] = 'SO0007'
        post_dict['UUID'] = uuid
        # API Gateway URL to make HTTP POST call
        url = 'https://metrics.awssolutionsbuilder.com/generic'
        data = json.dumps(post_dict)
        headers = {'content-type': 'application/json'}
        req = Request(url, data, headers)
        rsp = urlopen(req)
        content = rsp.read()
        rsp_code = rsp.getcode()
        print ('Response Code: {}'.format(rsp_code))
