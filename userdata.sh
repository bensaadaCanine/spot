#!/bin/bash
sudo yum update -y
sudo amazon-linux-extras install nginx1 -y
sudo nginx
sudo chmod 2775 /usr/share/nginx/html
sudo bash -c 'echo CONGRATS! NGINX Runs On This Server BY BEN SAADA > /usr/share/nginx/html/index.html'