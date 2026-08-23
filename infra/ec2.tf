# Worker ASG — always at least one t4g.nano instance polling SQS.
# cloud-init downloads worker.tar.gz from S3 on first boot and sets up
# systemd with the secrets passed in via Terraform vars.
data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["137112412989"] # Amazon

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-arm64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_security_group" "worker" {
  name        = "${local.suffix}-worker-sg"
  description = "Egress-only security group for the worker fleet."

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

# Cloud-init — runs once at first boot. Idempotent: the tarball extract
# is guarded so re-runs on instance refresh are cheap.
#
# Secrets come from the Terraform variables and are written to
# /etc/wactl/worker.env, which the systemd unit sources via
# `EnvironmentFile=`. Secrets never appear in user_data (which would
# be readable via the EC2 console) because the systemd unit loads them
# after the instance boots.
data "cloudinit_config" "worker" {
  gzip          = false
  base64_encode = false

  part {
    filename     = "wactl-worker.cfg"
    content_type = "text/cloud-config"

    content = <<-EOT
      #cloud-config
      packages:
        - python3.12
        - tar
        - gzip
        - amazon-ssm-agent

      users:
        - name: wactl
          system: true
          shell: /bin/bash
          home: /opt/wactl

      runcmd:
        - mkdir -p /opt/wactl /var/log/wactl /etc/wactl
        - chown -R wactl:wactl /opt/wactl /var/log/wactl /etc/wactl
        - |
          if [ ! -f /opt/wactl/.venv/bin/python ]; then
            aws s3 cp s3://${aws_s3_bucket.releases.bucket}/worker.tar.gz /tmp/worker.tar.gz
            tar -xzf /tmp/worker.tar.gz -C /opt/wactl
            /opt/wactl/.venv/bin/python -m ensurepip --upgrade || true
          fi
        - |
          cat > /etc/systemd/system/wactl-worker.service <<'UNIT'
          [Unit]
          Description=WACTL worker
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=wactl
          Group=wactl
          WorkingDirectory=/opt/wactl
          EnvironmentFile=-/etc/wactl/worker.env
          ExecStart=/opt/wactl/.venv/bin/python -m worker.main
          Restart=on-failure
          KillSignal=SIGTERM
          TimeoutStopSec=30
          NoNewPrivileges=true
          ProtectSystem=strict
          ProtectHome=true
          PrivateTmp=true
          ReadWritePaths=/var/log/wactl /tmp

          [Install]
          WantedBy=multi-user.target
          UNIT
        - systemctl daemon-reload
        - systemctl enable --now wactl-worker.service
        - chown -R wactl:wactl /var/log/wactl /opt/wactl
    EOT
  }

  part {
    filename     = "wactl-worker.env"
    content_type = "text/cloud-config"

    content = <<-EOT
      #cloud-config
      write_files:
        - path: /etc/wactl/worker.env
          permissions: '0600'
          owner: root:root
          content: |
            WACTL_ENV=${var.env}
            AWS_REGION=${var.region}
            WACTL_JOBS_QUEUE=${aws_sqs_queue.jobs.url}
            WACTL_S3_MEDIA_BUCKET=${aws_s3_bucket.media.bucket}
            WACTL_DYNAMODB_DEDUP_TABLE=${aws_dynamodb_table.dedup.name}
            TELEGRAM_BOT_TOKEN=${var.telegram_bot_token}
            GEMINI_API_KEY=${var.gemini_api_key}
      runcmd:
        - chmod 0600 /etc/wactl/worker.env
        - chown root:root /etc/wactl/worker.env
        - systemctl restart wactl-worker.service || true
    EOT
  }
}

resource "aws_launch_template" "worker" {
  name_prefix   = "${local.suffix}-worker-"
  image_id      = data.aws_ami.al2023_arm64.id
  instance_type = "t4g.nano"
  user_data     = data.cloudinit_config.worker.rendered

  vpc_security_group_ids = [aws_security_group.worker.id]

  iam_instance_profile {
    name = aws_iam_instance_profile.worker.name
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 enforced
    http_put_response_hop_limit = 1
  }

  tag_specifications {
    resource_type = "instance"
    tags          = local.tags
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Always-on ASG, sized for free tier. desired=max=1 to keep things
# trivial; scale out only if you outgrow t4g.nano (unlikely).
resource "aws_autoscaling_group" "worker" {
  name                = "${local.suffix}-worker"
  vpc_zone_identifier = data.aws_subnets.default.ids
  desired_capacity    = 1
  min_size            = 1
  max_size            = 1
  health_check_type   = "EC2"

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${local.suffix}-worker"
    propagate_at_launch = true
  }
}

data "aws_subnets" "default" {
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}
