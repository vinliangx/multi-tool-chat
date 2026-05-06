variable "name" { type = string }

resource "aws_s3_bucket" "tool_results" {
  bucket        = "${var.name}-tool-results"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "tool_results" {
  bucket                  = aws_s3_bucket.tool_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "tool_results_bucket_name" { value = aws_s3_bucket.tool_results.bucket }
output "tool_results_bucket_arn"  { value = aws_s3_bucket.tool_results.arn }
