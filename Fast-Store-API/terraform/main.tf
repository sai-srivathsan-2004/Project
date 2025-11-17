provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "oas_reports" {
  bucket = "faststore-oas-reports-${random_id.bucket_hex.hex}"
  force_destroy = true
  acl = "private"
}

resource "random_id" "bucket_hex" {
  byte_length = 4
}

data "aws_iam_policy_document" "github_oidc" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"]
    }
  }
}

data "aws_caller_identity" "current" {}

# Example role (you will need to configure the provider and replace with actual OIDC provider ARN setup)
resource "aws_iam_role" "github_actions_role" {
  name = "github-actions-s3-upload-role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:Allan-Binga/Fast-Store-API:ref:refs/heads/main"
      }
    }
  }]
}
EOF
}

resource "aws_iam_policy" "s3_put_policy" {
  name = "GitHubActionsS3PutPolicy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject"
      ]
      Effect = "Allow"
      Resource = "${aws_s3_bucket.oas_reports.arn}/*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach" {
  role = aws_iam_role.github_actions_role.name
  policy_arn = aws_iam_policy.s3_put_policy.arn
}
