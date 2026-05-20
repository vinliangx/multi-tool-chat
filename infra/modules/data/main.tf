variable "name"               { type = string }
variable "vpc_id"             { type = string }
variable "vpc_cidr"           { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_password"        { type = string  sensitive = true }

# --- S3 ---

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

# --- ElastiCache Redis ---

resource "aws_security_group" "redis" {
  name   = "${var.name}-redis"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name}-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.name}-redis"
  description                = "Redis for ${var.name}"
  node_type                  = "cache.t3.micro"
  num_cache_clusters         = 1
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false
  automatic_failover_enabled = false
}

# --- RDS PostgreSQL (pgvector-ready) ---

resource "aws_security_group" "postgres" {
  name   = "${var.name}-postgres"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.name}-postgres"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.name}-postgres"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "appdb"
  username               = "appuser"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  skip_final_snapshot    = true
  storage_encrypted      = true
}

resource "aws_ssm_parameter" "postgres_url" {
  name  = "/${var.name}/postgres_url"
  type  = "SecureString"
  value = "postgresql://appuser:${var.db_password}@${aws_db_instance.postgres.address}:5432/appdb"
}

# Separate password param so Keycloak can receive KC_DB_PASSWORD via ECS secrets injection.
resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.name}/db_password"
  type  = "SecureString"
  value = var.db_password
}

output "tool_results_bucket_name" { value = aws_s3_bucket.tool_results.bucket }
output "tool_results_bucket_arn"  { value = aws_s3_bucket.tool_results.arn }
output "redis_primary_endpoint"   { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "postgres_url_ssm_arn"     { value = aws_ssm_parameter.postgres_url.arn }
output "rds_address"              { value = aws_db_instance.postgres.address }
output "db_password_ssm_arn"      { value = aws_ssm_parameter.db_password.arn }
