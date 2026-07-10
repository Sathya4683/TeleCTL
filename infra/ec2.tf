# Worker ASG — always at least one instance polling SQS. cloud-init
# downloads worker.tar.gz from S3 on first boot and sets up systemd.
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

# cloud-config — runs once at first boot. Idempotent — safe to re-run on
# instance refresh because we install only if `/opt/wactl/.venv` is missing.
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
        - git
        - amazon-ssm-agent

      users:
        - name: wactl
          system: true
          shell: /bin/bash
          home: /opt/wactl

      runcmd:
        - mkdir -p /opt/wactl /var/log/wactl
        - chown -R wactl:wactl /opt/wactl /var/log/wactl
        - |
          if [ ! -f /opt/wactl/.venv/bin/python ]; then
            aws s3 cp s3://${aws_s3_bucket.releases.bucket}/worker.tar.gz /tmp/worker.tar.gz
            tar -xzf /tmp/worker.tar.gz -C /opt/wactl
            /opt/wactl/.venv/bin/python -m ensurepip --upgrade || true
          fi
        - |
          cat > /etc/systemd/system/wactl-worker.service <<UNIT
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

          [Install]
          WantedBy=multi-user.target
          UNIT
        - systemctl daemon-reload
        - systemctl enable --now wactl-worker.service
        - chown -R wactl:wactl /var/log/wactl /opt/wactl
    EOT
  }
}

resource "aws_launch_template" "worker" {
  name_prefix   = "${local.suffix}-worker-"
  image_id      = data.aws_ami.al2023_arm64.id
  instance_type = "t4g.small"
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
    name_prefix_enable = true
  }
}

# Stub VPC/ASG — for a real deploy, point `vpc_zone_identifier` at the
# private subnets of an existing VPC (or create one with a module). Kept
# minimal here so the plan is reviewable.
resource "aws_autoscaling_group" "worker" {
  name                = "${local.suffix}-worker"
  vpc_zone_identifier = data.aws_subnets.default.ids
  desired_capacity    = 1
  min_size            = 1
  max_size            = 2
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
