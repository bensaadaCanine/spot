# Prerequisites:

An AWS Account/IAM Role configured on this machine with EC2,CloudWatch Permissions.
Also, Please prepare a KeyPair.

# Purpose:

This script creates an AutoScale Group of EC2 instances with NGINX running on them.
In case of CPU metric crosses 80 percent - It will create a new instance to balance
spread the load and will assign it to the same ELB so the user won't feel anything.
Minimum instances - 1. Maximum instances - 5.
Cooldown is set for 600sec because it takes a lot of time for the NGINX servers to be installed and run.

Served as an home assignment to "Spot".
