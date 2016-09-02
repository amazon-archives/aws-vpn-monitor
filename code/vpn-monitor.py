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

import json
import boto3
import logging
import datetime
from urllib2 import Request
from urllib2 import urlopen

log = logging.getLogger()
log.setLevel(logging.INFO)

log.debug('Loading function')
cw = boto3.client('cloudwatch')


# Save the connection status in the CloudWatch Custom Metric
def putCloudWatchMetric(metricName, value, vgw, cgw, region):
    cw.put_metric_data(
        Namespace='VPNStatus',
        MetricData=[{
            'MetricName': metricName,
            'Value': value,
            'Unit': 'Count',
            'Dimensions': [{
                'Name': 'VGW',
                'Value': vgw
            },
                {
                    'Name': 'CGW',
                    'Value': cgw
                },
                {
                    'Name': 'Region',
                    'Value': region
                }]
        }]
    )


def lambda_handler(event, context):
    # Create connections
    ec2 = boto3.client('ec2')
    AWS_Regions = ec2.describe_regions()['Regions']
    cf = boto3.client('cloudformation')

    # Declare variables
    numConnections = 0
    countDict = {}
    regionDict = {}
    regionsLabelDict = {}
    postDict = {}
    outputs = {}
    TimeNow = datetime.datetime.utcnow().isoformat()
    TimeStamp = str(TimeNow)

    # Read output variables from CloudFormation Template
    stack_name = context.invoked_function_arn.split(':')[6].rsplit('-', 2)[0]
    response = cf.describe_stacks(StackName=stack_name)
    for e in response['Stacks'][0]['Outputs']:
        outputs[e['OutputKey']] = e['OutputValue']
    uuid = outputs['UUID']
    sendData = outputs['AnonymousData']

    # Check VPN connections status in all the regions
    for region in AWS_Regions:
        try:
            ec2 = boto3.client('ec2', region_name=region['RegionName'])
            awsregion = region['RegionName']
            vpns = ec2.describe_vpn_connections()['VpnConnections']
            connections = 0
            for vpn in vpns:
                if vpn['State'] == "available":
                    numConnections += 1
                    connections += 1
                    active_tunnels = 0
                    if vpn['VgwTelemetry'][0]['Status'] == "UP":
                        active_tunnels += 1
                    if vpn['VgwTelemetry'][1]['Status'] == "UP":
                        active_tunnels += 1
                    log.info('{} VPN ID: {}, State: {}, Tunnel0: {}, Tunnel1: {} -- {} active tunnels'.format(region['RegionName'], vpn['VpnConnectionId'],vpn['State'],vpn['VgwTelemetry'][0]['Status'],vpn['VgwTelemetry'][1]['Status'], active_tunnels))
                    putCloudWatchMetric(vpn['VpnConnectionId'], active_tunnels, vpn['VpnGatewayId'], vpn['CustomerGatewayId'], region['RegionName'])
            # Build anonymous data
            if sendData == "Yes":
                countDict['vpn_connections'] = connections
                regionDict[awsregion] = dict(countDict)
        except Exception as e:
            log.error("Exception: "+str(e))
            continue

    # Send anonymous data
    if sendData == "Yes":
        regionsLabelDict['regions'] = regionDict
        postDict['Data'] = regionsLabelDict
        postDict['TimeStamp'] = TimeStamp
        postDict['Solution'] = 'SO0004'
        postDict['UUID'] = uuid

        # API Gateway URL to make HTTP POST call
        url = 'https://metrics.awssolutionsbuilder.com/generic'
        data = json.dumps(postDict)
        headers = {'content-type': 'application/json'}
        req = Request(url, data, headers)
        rsp = urlopen(req)
        content = rsp.read()
        rspcode = rsp.getcode()
        log.debug('Response Code: {}'.format(rspcode))
        log.debug('Response Content: {}'.format(content))
    return numConnections
