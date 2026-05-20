variable "name"                   { type = string }
variable "region"                 { type = string }
variable "vpc_id"                 { type = string }
variable "public_subnet_ids"      { type = list(string) }
variable "private_subnet_ids"     { type = list(string) }
variable "tool_results_bucket"    { type = string }
variable "anthropic_api_key"      { type = string  sensitive = true }
variable "redis_primary_endpoint" { type = string }
variable "postgres_url_ssm_arn"   { type = string }

locals {
  redis_url = "redis://${var.redis_primary_endpoint}:6379"
}

# --- ECR ---

resource "aws_ecr_repository" "api" {
  name                 = "${var.name}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_repository" "weather_service" {
  name                 = "${var.name}-weather-service"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_repository" "mcp_documents" {
  name                 = "${var.name}-mcp-documents"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_repository" "mcp_personal_finance" {
  name                 = "${var.name}-mcp-personal-finance"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# --- Secrets ---

resource "aws_ssm_parameter" "anthropic_key" {
  name  = "/${var.name}/anthropic_api_key"
  type  = "SecureString"
  value = var.anthropic_api_key
}

# --- Security groups ---

resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "service" {
  name   = "${var.name}-svc"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- ALB ---

resource "aws_lb" "this" {
  name               = "${var.name}-alb"
  load_balancer_type = "application"
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check { path = "/health" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# --- ECS cluster + IAM ---

resource "aws_ecs_cluster" "this" { name = "${var.name}-cluster" }

resource "aws_iam_role" "task_exec" {
  name = "${var.name}-task-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_exec" {
  role       = aws_iam_role.task_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = aws_iam_role.task_exec.assume_role_policy
}

resource "aws_iam_role_policy" "task_app" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["arn:aws:s3:::${var.tool_results_bucket}/*"]
      },
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          aws_ssm_parameter.anthropic_key.arn,
          var.postgres_url_ssm_arn,
        ]
      },
    ]
  })
}

# --- CloudWatch log groups ---

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${var.name}/api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "mcp_documents" {
  name              = "/${var.name}/mcp-documents"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "mcp_personal_finance" {
  name              = "/${var.name}/mcp-personal-finance"
  retention_in_days = 14
}

# --- ECS task definition ---
# mcp-weather-service and mcp-documents run as sidecars so the api container
# can reach them via localhost (awsvpc shares the network namespace per task).

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  cpu                      = "2048"
  memory                   = "4096"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.task_exec.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:latest"
      essential = true
      portMappings = [{ containerPort = 8000 }]
      environment = [
        { name = "LLM_PROVIDER",         value = "anthropic" },
        { name = "MODEL_NAME",           value = "claude-sonnet-4-6" },
        { name = "SUMMARIZER_MODEL",     value = "claude-haiku-4-5-20251001" },
        { name = "USE_AWS_STORE",        value = "1" },
        { name = "AWS_REGION",           value = var.region },
        { name = "TOOL_RESULTS_BUCKET",  value = var.tool_results_bucket },
        { name = "REDIS_URL",            value = local.redis_url },
        { name = "WEATHER_SERVICE_URL",  value = "http://localhost:8002" },
        { name = "RAG_SERVICE_URL",      value = "http://localhost:8003" },
        { name = "FINANCE_SERVICE_URL",  value = "http://localhost:8004" },
      ]
      secrets = [
        { name = "ANTHROPIC_API_KEY", valueFrom = aws_ssm_parameter.anthropic_key.arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "api"
        }
      }
    },
    {
      name      = "mcp-weather-service"
      image     = "${aws_ecr_repository.weather_service.repository_url}:latest"
      essential = false
      portMappings = [{ containerPort = 8002 }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "weather-service"
        }
      }
    },
    {
      name      = "mcp-documents"
      image     = "${aws_ecr_repository.mcp_documents.repository_url}:latest"
      essential = false
      portMappings = [{ containerPort = 8003 }]
      environment = [
        { name = "REDIS_URL", value = local.redis_url },
      ]
      secrets = [
        { name = "RAG_DB_URL", valueFrom = var.postgres_url_ssm_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.mcp_documents.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "mcp-documents"
        }
      }
    },
    {
      name      = "mcp-personal-finance"
      image     = "${aws_ecr_repository.mcp_personal_finance.repository_url}:latest"
      essential = false
      portMappings = [{ containerPort = 8004 }]
      secrets = [
        { name = "CHAT_APP_URL", valueFrom = var.postgres_url_ssm_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.mcp_personal_finance.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "mcp-personal-finance"
        }
      }
    },
  ])
}

# --- ECS service (private subnets — egress via NAT) ---

resource "aws_ecs_service" "api" {
  name            = "${var.name}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener.http]
}

output "alb_dns_name"                        { value = aws_lb.this.dns_name }
output "ecr_repository_url"                  { value = aws_ecr_repository.api.repository_url }
output "ecr_weather_service_repo_url"        { value = aws_ecr_repository.weather_service.repository_url }
output "ecr_mcp_documents_repo_url"          { value = aws_ecr_repository.mcp_documents.repository_url }
output "ecr_mcp_personal_finance_repo_url"   { value = aws_ecr_repository.mcp_personal_finance.repository_url }
