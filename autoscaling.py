import boto3
import sys


# Define key name
KEY_NAME = "main-key"


# Trying to fetch the default VPC,Subnet and AZ
def fetch_vpc_subnet_az_id(client):
    try:
        print("Fetching Default VPC,Subnet And AZ...")
        response = client.describe_vpcs()
        vpc_id = ""

        for vpc in response["Vpcs"]:
            if vpc["IsDefault"]:
                vpc_id = vpc["VpcId"]
                break

        response = client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
        subnet_id = response["Subnets"][0]["SubnetId"]
        az = response["Subnets"][0]["AvailabilityZone"]
        return vpc_id, subnet_id, az
    except:
        # If this operation fails - there is no point to move further
        print("Something Went Wrong. Please Check AWS Account For Further Information. Aborting...")
        sys.exit(0)


# Creating new security Group
def create_ec2_security_group(client):

    sg_name = "asg-sg-bensaada"
    print("Creating the Security Group {} : STARTED ".format(sg_name))
    try:
        vpc_id, subnet_id, az = fetch_vpc_subnet_az_id(client)
        response = client.create_security_group(
            GroupName=sg_name,
            Description="SG for the homeassignment by Ben Saada",
            VpcId=vpc_id
        )
        sg_id = response["GroupId"]
        sg_config = client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    # SSH Everywhere
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
                {
                    # HTTP Everywhere
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )
        print("Creating the Security Group {} : COMPLETED - Security Group ID: {} ".format(sg_name, sg_id))
        return sg_id, sg_name

    except Exception as e:
        if str(e).__contains__("already exists"):
            response = client.describe_security_groups(
                GroupNames=[sg_name])
            sg_id = response["SecurityGroups"][0]["GroupId"]
            print("Security Group {} already exists with Security Group ID: {} ".format(
                sg_name, sg_id))
            return sg_id, sg_name


# Creating Launch Template With a UserData to create EC2 instance with NGINX on it.
def create_ec2_launch_template():
    ec2_client = boto3.client('ec2')

    print("Creating the Launch Template : STARTED ")

    # Reading the User Data in Base64 format
    with open("userdata_base64.txt") as file:
        USERDATA_B64_STR = file.read()

    template_name = 'bensaada-launch-template'
    try:
        sg_id, sg_name = create_ec2_security_group(ec2_client)
        response = ec2_client.create_launch_template(
            LaunchTemplateName=template_name,
            LaunchTemplateData={
                'ImageId': 'ami-089c6f2e3866f0f14',  # Basic Linux machine
                'InstanceType': "t2.micro",
                'KeyName': KEY_NAME,
                'UserData': USERDATA_B64_STR,
                'SecurityGroupIds': [sg_id]
            }
        )
        template_id = response['LaunchTemplate']['LaunchTemplateId']
        print("Creating the Launch Template : COMPLETED : TemplateName:{} ,TemplateID:{}".format(
            template_name, template_id))
        return template_id, template_name, sg_id
    except:
        response = ec2_client.describe_launch_templates(
            LaunchTemplateNames=[
                template_name,
            ]
        )
        template_id = response['LaunchTemplates'][0]['LaunchTemplateId']
        print("Launch Template {} already exists.".format(
            template_name))
        return template_id, template_name, sg_id


# Create ELB
def create_elb(az, sg_id):

    client = boto3.client('elb')
    elb_name = "bensaada-elb"

    try:
        response = client.create_load_balancer(
            LoadBalancerName=elb_name,
            Listeners=[
                {
                    'Protocol': 'HTTP',
                    'LoadBalancerPort': 80,
                    'InstanceProtocol': 'HTTP',
                    'InstancePort': 80,
                },
            ],
            AvailabilityZones=[
                az,
            ],
            SecurityGroups=[
                sg_id,
            ],

        )
        print("DNS Name : {}".format(response['DNSName']))
        return elb_name
    except:

        print("{} ELB Aready exists.".format(elb_name))
        return elb_name


# Creating the scaling policy
def scaling_policy(groupName):
    autoscaling = boto3.client('autoscaling')
    cloudwatch = boto3.client('cloudwatch')

    # Create policy for ASG
    try:
        print("Creating policy for {} AutoScaling Group".format(groupName))
        response = autoscaling.put_scaling_policy(
            AutoScalingGroupName=groupName,
            PolicyName='cpu-scale-out-policy',
            AdjustmentType='ChangeInCapacity',
            ScalingAdjustment=1,
            Cooldown=600,
        )
        policyARN = response['PolicyARN']
    except Exception as e:
        print("POLICY WAS NOT CREATED DUE TO THE FOLLOWING ERROR:")
        print(e)

    # Create CloudWatch Alarm within the policy
    try:
        cloudwatch.put_metric_alarm(
            AlarmName='Web_Server_CPU_Utilization',
            AlarmDescription='Alarm when server CPU exceeds 79%',
            ActionsEnabled=True,
            AlarmActions=[
                # In ALARM Status, we will apply the policy below
                policyARN,
            ],
            MetricName='CPUUtilization',
            Namespace='AWS/EC2',
            ComparisonOperator='GreaterThanOrEqualToThreshold',
            EvaluationPeriods=1,
            Statistic='Average',
            Dimensions=[
                {
                    'Name': 'AutoScalingGroupName',
                    'Value': groupName
                },
            ],
            Period=60,
            Threshold=80.0,
            Unit='Percent',
            TreatMissingData='notBreaching',  # Avoiding 'INSUFFICENT_DATA' status
        )
    except Exception as e:
        print("CLOUDWATCH ALARM WAS NOT CREATED DUE TO THE FOLLOWING ERROR:")
        print(e)


# Create the autoscaling Group - MAIN FUNCTION
def create_ec2_auto_scaling_group():
    try:
        print("---- Started the creation of Auto Scaling Group using Launch Template ----")

        # First of all - We will create out Launch Template(Security Group also included...)
        launch_template_id, launch_template_name, sg_id = create_ec2_launch_template()
        # Then, We'll fetch our VPC,Subnet and AZ for creating AutoScale Group
        vpc_id, subnet_id, az = fetch_vpc_subnet_az_id(
            client=boto3.client('ec2'))
        # Creating the ELB
        elb_name = create_elb(az, sg_id)

        # After we have all of the above - we can procceed to creating our autoscaling group
        client = boto3.client('autoscaling')
        response = client.create_auto_scaling_group(
            AutoScalingGroupName='bensaada_homeassignment',
            LaunchTemplate={
                'LaunchTemplateId': launch_template_id,
            },
            MinSize=1,
            MaxSize=5,
            DesiredCapacity=1,
            AvailabilityZones=[
                az,
            ],
            LoadBalancerNames=[
                elb_name,
            ],
        )

        # Creating the policy for our autoscaling group
        scaling_policy('bensaada_homeassignment')

        # Checking that everything is good :)
        if str(response["ResponseMetadata"]["HTTPStatusCode"]) == "200":
            print(
                "---- Creation of Auto Scaling Group using Launch Templates : COMPLETED ----")
        else:
            print(
                "---- Creation of Auto Scaling Group using Launch Templates : FAILED ----")
    except Exception as e:
        if str(e).__contains__("(AlreadyExists)"):
            print("---- AUTOSCALE GROUP ALREADY EXISTS! ----")


create_ec2_auto_scaling_group()
